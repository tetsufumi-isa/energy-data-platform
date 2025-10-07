"""
電力データBigQuery投入システム

実行方法:
    python -m src.data_processing.power_bigquery_loader              # デフォルト: 過去5日分
    python -m src.data_processing.power_bigquery_loader --days 7     # 過去7日分
"""

import argparse
import csv
import json
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from google.cloud import bigquery

class PowerBigQueryLoader:
    """電力データをBigQueryに投入するクラス"""

    def __init__(self, project_id="energy-env", raw_data_dir=None):
        """
        初期化

        Args:
            project_id (str): GCPプロジェクトID
            raw_data_dir (str): 生データ(CSV)格納ディレクトリ
        """
        self.project_id = project_id
        self.dataset_id = "prod_energy_data"
        self.table_id = "energy_data_hourly"

        # 生データディレクトリ設定
        energy_env_path = os.getenv('ENERGY_ENV_PATH')
        if energy_env_path is None:
            raise ValueError("ENERGY_ENV_PATH環境変数が設定されていません")

        if raw_data_dir is None:
            self.raw_data_dir = Path(energy_env_path) / 'data' / 'raw'
        else:
            self.raw_data_dir = Path(raw_data_dir)

        # ログディレクトリ設定
        self.log_dir = Path(energy_env_path) / 'logs' / 'power_bq_loader'
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # BigQueryクライアントの初期化
        self.bq_client = bigquery.Client(project=project_id)

        # BQログテーブル設定
        self.bq_log_table_id = f"{self.project_id}.{self.dataset_id}.process_execution_log"

        print(f"PowerBigQueryLoader初期化完了: {project_id}, 生データディレクトリ: {self.raw_data_dir}")

    def parse_csv_to_rows(self, csv_file_path):
        """
        CSVファイルを解析してBQインサート用の行データに変換

        Args:
            csv_file_path (Path): CSVファイルパス

        Returns:
            list: BQインサート用の辞書のリスト
        """
        rows = []

        with open(csv_file_path, 'r', encoding='shift_jis') as f:
            reader = csv.DictReader(f)

            for csv_row in reader:
                # CSVの典型的な列名: DATE, TIME, 実績値（万kW）, 供給力（万kW）
                # 列名のバリエーションに対応
                date_str = csv_row.get('DATE') or csv_row.get('日付')
                time_str = csv_row.get('TIME') or csv_row.get('時刻')
                actual_power_str = csv_row.get('実績値（万kW）') or csv_row.get('実績値')
                supply_capacity_str = csv_row.get('供給力（万kW）') or csv_row.get('供給力')

                if not all([date_str, time_str, actual_power_str]):
                    # 必須項目が欠けている行はスキップ
                    continue

                # 日付・時刻パース
                try:
                    # DATE: YYYYMMDD形式想定
                    if len(date_str) == 8:
                        date_obj = datetime.strptime(date_str, '%Y%m%d')
                    else:
                        # YYYY-MM-DD形式の場合
                        date_obj = datetime.strptime(date_str, '%Y-%m-%d')

                    date_formatted = date_obj.strftime('%Y-%m-%d')

                    # TIME: HH:MM形式想定
                    hour_str = time_str.split(':')[0].zfill(2)

                except (ValueError, IndexError) as e:
                    print(f"日付・時刻パースエラー: {date_str}, {time_str} - {e}")
                    continue

                # 実績値パース
                try:
                    actual_power = int(float(actual_power_str))
                except (ValueError, TypeError):
                    print(f"実績値パースエラー: {actual_power_str}")
                    continue

                # 供給力パース（オプション）
                supply_capacity = None
                if supply_capacity_str:
                    try:
                        supply_capacity = int(float(supply_capacity_str))
                    except (ValueError, TypeError):
                        pass

                row = {
                    'date': date_formatted,
                    'hour': hour_str,
                    'actual_power': actual_power,
                    'supply_capacity': supply_capacity,
                    'created_at': datetime.now().isoformat()
                }
                rows.append(row)

        print(f"CSVファイル解析完了: {csv_file_path.name}, {len(rows)}行")
        return rows

    def delete_duplicate_data(self, rows):
        """
        既存データを削除（インサート予定データと同じ日付範囲の既存データを削除）

        Args:
            rows (list): インサート予定のデータ行
        """
        if not rows:
            print("削除対象データなし")
            return

        # インサート予定データから日付範囲を取得
        dates = [row['date'] for row in rows]
        min_date = min(dates)
        max_date = max(dates)

        delete_query = f"""
        DELETE FROM `{self.project_id}.{self.dataset_id}.{self.table_id}`
        WHERE date >= '{min_date}'
          AND date <= '{max_date}'
        """

        job = self.bq_client.query(delete_query)
        result = job.result()

        print(f"既存データ削除完了: {job.num_dml_affected_rows}行削除（期間: {min_date}～{max_date}）")

    def move_processed_files(self, csv_files):
        """
        処理済みCSVファイルをアーカイブディレクトリに移動

        Args:
            csv_files (list): 処理済みCSVファイルのパスリスト
        """
        moved_count = 0
        for csv_file in csv_files:
            try:
                archive_dir = csv_file.parent / 'archive'
                archive_dir.mkdir(exist_ok=True)

                archive_path = archive_dir / csv_file.name
                csv_file.rename(archive_path)
                moved_count += 1
                print(f"処理済みファイル移動: {csv_file.name} → archive/")
            except Exception as e:
                print(f"ファイル移動失敗 {csv_file.name}: {e}")

        print(f"処理済みファイル {moved_count}個をarchive/に移動")

    def get_required_months(self, days=5):
        """
        指定日数分の日付から必要な月のセットを取得

        Args:
            days (int): 昨日から遡る日数（デフォルト: 5）

        Returns:
            set: 必要な月の文字列セット (例: {'202504', '202505'})
        """
        yesterday = datetime.today() - timedelta(days=1)
        dates = [yesterday - timedelta(days=i) for i in range(days + 1)]
        months = {date.strftime('%Y%m') for date in dates}

        print(f"過去{days}日分に必要な月: {sorted(months)}")
        return months

    def _write_log(self, log_data):
        """
        ログをローカルファイルとBigQueryに記録

        Args:
            log_data (dict): ログデータ
        """
        # ローカルファイルに記録
        log_date = log_data.get('date', datetime.now().strftime('%Y-%m-%d'))
        log_file = self.log_dir / f"{log_date}_power_bq_load_execution.jsonl"

        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_data, ensure_ascii=False) + '\n')
        except Exception as e:
            print(f"ログファイル書き込み失敗: {e}")

        # BigQueryに記録
        try:
            self.bq_client.insert_rows_json(self.bq_log_table_id, [log_data])
        except Exception as e:
            # BQエラーをローカルログにも記録
            error_log = {
                'timestamp': datetime.now().isoformat(),
                'error_type': 'BQ_INSERT_FAILED',
                'error_message': str(e),
                'original_log_data': log_data
            }
            error_log_file = self.log_dir / f"{log_date}_bq_errors.jsonl"
            try:
                with open(error_log_file, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(error_log, ensure_ascii=False) + '\n')
            except Exception as file_error:
                print(f"エラーログファイル書き込み失敗: {file_error}")

            print(f"BigQuery書き込み失敗（ファイルには保存済み・エラーログ記録済み）: {e}")

    def load_power_data(self, days=5):
        """
        電力データをBigQueryに投入するメイン処理（複数日対応）

        Args:
            days (int): 昨日から遡る日数（デフォルト: 5）

        Returns:
            dict: 処理結果
        """
        # 実行ID・開始時刻記録
        execution_id = str(uuid.uuid4())
        started_at = datetime.now()
        yesterday = datetime.now() - timedelta(days=1)
        target_date_str = yesterday.strftime('%Y-%m-%d')

        print(f"電力データBQ投入開始: 過去{days}日分, execution_id={execution_id}")

        try:
            # 1. 該当する月を特定
            months = self.get_required_months(days)

            # 2. 各月のCSVファイルを取得
            all_csv_files = []
            for month in sorted(months):
                month_dir = self.raw_data_dir / month
                if not month_dir.exists():
                    print(f"月ディレクトリが存在しません: {month_dir}")
                    continue

                # *_power_usage.csv パターンのファイルを取得
                csv_files = list(month_dir.glob("*_power_usage.csv"))
                all_csv_files.extend(csv_files)
                print(f"{month}: {len(csv_files)}個のCSVファイルを検出")

            if not all_csv_files:
                raise FileNotFoundError(f"処理対象のCSVファイルが見つかりません（過去{days}日分の月: {sorted(months)}）")

            print(f"処理対象: 合計{len(all_csv_files)}個のCSVファイル")

            # 3. 全CSVファイルを処理
            all_rows = []
            processed_files = []

            for csv_file in all_csv_files:
                try:
                    rows = self.parse_csv_to_rows(csv_file)
                    if rows:
                        all_rows.extend(rows)
                        processed_files.append(csv_file)
                except Exception as e:
                    print(f"CSVファイル処理エラー（スキップ）: {csv_file.name} - {e}")
                    continue

            if not all_rows:
                raise ValueError(f"全CSVファイルから有効なデータ行が取得できませんでした")

            print(f"全CSVから取得した行数: {len(all_rows)}行")

            # 4. 重複データ削除
            self.delete_duplicate_data(all_rows)

            # 5. データ投入
            table_ref = f"{self.project_id}.{self.dataset_id}.{self.table_id}"
            errors = self.bq_client.insert_rows_json(table_ref, all_rows)
            if errors:
                raise Exception(f"BQインサートエラー: {errors}")

            rows_inserted = len(all_rows)
            print(f"電力データインサート完了: {rows_inserted}行")

            # 6. 成功時のみファイル移動
            self.move_processed_files(processed_files)

            print(f"電力データBQ投入完了: {len(processed_files)}ファイル, {rows_inserted}行")

            # 成功ログ記録
            completed_at = datetime.now()
            duration_seconds = int((completed_at - started_at).total_seconds())

            log_data = {
                "execution_id": execution_id,
                "date": target_date_str,
                "process_type": "POWER_BQ_LOAD",
                "status": "SUCCESS",
                "error_message": None,
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
                "duration_seconds": duration_seconds,
                "records_processed": rows_inserted,
                "file_size_mb": None,
                "additional_info": {
                    "days": days,
                    "months_processed": sorted(list(months)),
                    "files_processed": len(processed_files)
                }
            }
            self._write_log(log_data)

            return {
                'status': 'success',
                'message': f'{len(processed_files)}ファイルの投入成功',
                'files_processed': len(processed_files),
                'rows_inserted': rows_inserted
            }

        except Exception as e:
            print(f"電力データBQ投入失敗: {e}")

            # 失敗ログ記録
            completed_at = datetime.now()
            duration_seconds = int((completed_at - started_at).total_seconds())

            log_data = {
                "execution_id": execution_id,
                "date": target_date_str,
                "process_type": "POWER_BQ_LOAD",
                "status": "FAILED",
                "error_message": str(e),
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
                "duration_seconds": duration_seconds,
                "records_processed": None,
                "file_size_mb": None,
                "additional_info": {
                    "days": days
                }
            }
            self._write_log(log_data)

            return {
                'status': 'failed',
                'message': f'投入失敗: {str(e)}',
                'files_processed': 0,
                'rows_inserted': 0
            }


def print_load_results(results):
    """投入結果を表示"""
    print(f"\n{'='*60}")
    print("電力データBigQuery投入結果")
    print('='*60)

    status_mark = '成功' if results['status'] == 'success' else '失敗'

    print(f"\n処理結果: {status_mark}")
    print(f"メッセージ: {results['message']}")
    print(f"処理ファイル数: {results['files_processed']}")
    print(f"投入レコード数: {results['rows_inserted']}")
    print('='*60)


def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(description='電力データBigQuery投入システム')
    parser.add_argument('--days', type=int, default=5,
                       help='昨日から遡る日数（デフォルト: 5）')
    parser.add_argument('--project-id', type=str, default='energy-env',
                       help='GCPプロジェクトID')
    parser.add_argument('--raw-data-dir', type=str, default=None,
                       help='生データ(CSV)格納ディレクトリ')

    args = parser.parse_args()

    print("電力データBigQuery投入システム開始")
    print(f"プロジェクト: {args.project_id}")
    print(f"対象範囲: 過去{args.days}日分")

    # 投入処理実行
    loader = PowerBigQueryLoader(args.project_id, args.raw_data_dir)
    results = loader.load_power_data(args.days)

    # 結果表示
    print_load_results(results)

    print("処理完了")


if __name__ == "__main__":
    main()
