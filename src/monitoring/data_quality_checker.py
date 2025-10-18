"""
データ品質監視システム

実行方法:
    python -m src.monitoring.data_quality_checker              # デフォルト: 直近7日チェック
    python -m src.monitoring.data_quality_checker --days 14    # 直近14日チェック
"""

import argparse
import json
import os
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from google.cloud import bigquery


class DataQualityChecker:
    """データ品質チェックを実施するクラス"""

    def __init__(self, project_id="energy-env"):
        """
        初期化

        Args:
            project_id (str): GCPプロジェクトID
        """
        self.project_id = project_id
        self.dataset_id = "prod_energy_data"
        self.quality_table_id = "data_quality_checks"

        # ログディレクトリ設定
        energy_env_path = os.getenv('ENERGY_ENV_PATH')
        if energy_env_path is None:
            raise ValueError("ENERGY_ENV_PATH環境変数が設定されていません")

        self.log_dir = Path(energy_env_path) / 'logs' / 'data_quality_checker'
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # BigQueryクライアントの初期化
        self.bq_client = bigquery.Client(project=project_id)

        # BQログテーブル設定
        self.bq_log_table_id = f"{self.project_id}.{self.dataset_id}.process_execution_log"

        print(f"DataQualityChecker初期化完了: {project_id}")

    def _write_log(self, log_data):
        """
        ログをローカルファイルとBigQueryに記録

        Args:
            log_data (dict): ログデータ
        """
        # ローカルファイルに記録（実行日の日付を使用）
        log_date = datetime.now().strftime('%Y-%m-%d')
        log_file = self.log_dir / f"{log_date}_quality_check_execution.jsonl"

        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_data, ensure_ascii=False) + '\n')
        except Exception as e:
            print(f"ログファイル書き込み失敗: {e}")

        # BigQueryに記録
        try:
            errors = self.bq_client.insert_rows_json(self.bq_log_table_id, [log_data])
            if errors:
                raise Exception(f"BigQueryインサートエラー: {errors}")
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

    def _save_check_results(self, check_results):
        """
        チェック結果をローカルファイルとBigQueryに保存

        Args:
            check_results (list): チェック結果のリスト
        """
        if not check_results:
            raise ValueError("チェック結果が空です。チェック処理が正常に実行されていません")

        # ローカルファイルに保存（実行日の日付を使用）
        execution_date = datetime.now().strftime('%Y-%m-%d')
        result_file = self.log_dir / f"{execution_date}_quality_check_results.jsonl"

        try:
            with open(result_file, 'w', encoding='utf-8') as f:
                for result in check_results:
                    f.write(json.dumps(result, ensure_ascii=False) + '\n')
            print(f"品質チェック結果ローカル保存完了: {result_file}")
        except Exception as e:
            print(f"品質チェック結果ローカル保存失敗: {e}")

        # BigQueryに保存
        table_ref = f"{self.project_id}.{self.dataset_id}.{self.quality_table_id}"

        try:
            errors = self.bq_client.insert_rows_json(table_ref, check_results)
            if errors:
                raise Exception(f"BQインサートエラー: {errors}")
            print(f"品質チェック結果BQ保存完了: {len(check_results)}件")
        except Exception as e:
            print(f"品質チェック結果BQ保存失敗: {e}")
            raise

    def check_power_data(self, days=7):
        """
        電力データの品質チェック

        Args:
            days (int): チェック対象日数（直近N日）

        Returns:
            list: チェック結果のリスト
        """
        check_date = datetime.now().date()
        check_timestamp = datetime.now()
        period_end = datetime.now().date() - timedelta(days=1)  # 昨日まで
        period_start = period_end - timedelta(days=days-1)

        check_results = []
        print(f"電力データチェック開始: {period_start} ～ {period_end}")

        # 1. レコード欠損チェック（期待: 24時間 × N日 = 24*N レコード）
        try:
            expected_records = 24 * days
            query_missing = f"""
            SELECT COUNT(*) as actual_count
            FROM `{self.project_id}.{self.dataset_id}.energy_data_hourly`
            WHERE date >= '{period_start}'
              AND date <= '{period_end}'
            """
            result = self.bq_client.query(query_missing).result()
            actual_count = list(result)[0]['actual_count']
            missing_count = expected_records - actual_count

            status = 'OK' if missing_count == 0 else ('WARNING' if missing_count < 24 else 'ERROR')
            check_results.append({
                'check_date': str(check_date),
                'check_timestamp': check_timestamp.isoformat(),
                'data_type': 'power',
                'check_type': 'missing',
                'check_target': '全体',
                'issue_count': missing_count,
                'issue_detail': f'期待レコード数: {expected_records}, 実際: {actual_count}, 欠損: {missing_count}',
                'check_period_start': str(period_start),
                'check_period_end': str(period_end),
                'status': status
            })
            print(f"レコード欠損チェック: {status} (欠損{missing_count}件)")
        except Exception as e:
            raise Exception(f"電力データ: レコード欠損チェッククエリ実行失敗 - {str(e)}")

        # 2. NULL値チェック - actual_power
        try:
            query_null_power = f"""
            SELECT COUNT(*) as null_count
            FROM `{self.project_id}.{self.dataset_id}.energy_data_hourly`
            WHERE date >= '{period_start}'
              AND date <= '{period_end}'
              AND actual_power IS NULL
            """
            result = self.bq_client.query(query_null_power).result()
            null_count = list(result)[0]['null_count']

            status = 'OK' if null_count == 0 else ('WARNING' if null_count < 10 else 'ERROR')
            check_results.append({
                'check_date': str(check_date),
                'check_timestamp': check_timestamp.isoformat(),
                'data_type': 'power',
                'check_type': 'null',
                'check_target': 'actual_power',
                'issue_count': null_count,
                'issue_detail': f'actual_powerがNULLのレコード: {null_count}件',
                'check_period_start': str(period_start),
                'check_period_end': str(period_end),
                'status': status
            })
            print(f"  NULL値チェック(actual_power): {status} (NULL {null_count}件)")
        except Exception as e:
            raise Exception(f"電力データ: actual_power NULL値チェッククエリ実行失敗 - {str(e)}")

        # 3. NULL値チェック - supply_capacity
        try:
            query_null_capacity = f"""
            SELECT COUNT(*) as null_count
            FROM `{self.project_id}.{self.dataset_id}.energy_data_hourly`
            WHERE date >= '{period_start}'
              AND date <= '{period_end}'
              AND supply_capacity IS NULL
            """
            result = self.bq_client.query(query_null_capacity).result()
            null_count = list(result)[0]['null_count']

            status = 'OK' if null_count == 0 else ('WARNING' if null_count < 10 else 'ERROR')
            check_results.append({
                'check_date': str(check_date),
                'check_timestamp': check_timestamp.isoformat(),
                'data_type': 'power',
                'check_type': 'null',
                'check_target': 'supply_capacity',
                'issue_count': null_count,
                'issue_detail': f'supply_capacityがNULLのレコード: {null_count}件',
                'check_period_start': str(period_start),
                'check_period_end': str(period_end),
                'status': status
            })
            print(f"  NULL値チェック(supply_capacity): {status} (NULL {null_count}件)")
        except Exception as e:
            raise Exception(f"電力データ: supply_capacity NULL値チェッククエリ実行失敗 - {str(e)}")

        # 4. 異常値チェック - actual_power（1500～10000の範囲外）
        try:
            query_outlier_power = f"""
            SELECT COUNT(*) as outlier_count
            FROM `{self.project_id}.{self.dataset_id}.energy_data_hourly`
            WHERE date >= '{period_start}'
              AND date <= '{period_end}'
              AND (actual_power < 1500 OR actual_power > 10000)
            """
            result = self.bq_client.query(query_outlier_power).result()
            outlier_count = list(result)[0]['outlier_count']

            status = 'OK' if outlier_count == 0 else ('WARNING' if outlier_count < 5 else 'ERROR')
            check_results.append({
                'check_date': str(check_date),
                'check_timestamp': check_timestamp.isoformat(),
                'data_type': 'power',
                'check_type': 'outlier',
                'check_target': 'actual_power',
                'issue_count': outlier_count,
                'issue_detail': f'actual_powerが異常範囲（<1500 or >10000）: {outlier_count}件',
                'check_period_start': str(period_start),
                'check_period_end': str(period_end),
                'status': status
            })
            print(f"  異常値チェック(actual_power): {status} (異常{outlier_count}件)")
        except Exception as e:
            raise Exception(f"電力データ: actual_power 異常値チェッククエリ実行失敗 - {str(e)}")

        # 5. 異常値チェック - supply_capacity（1500～10000の範囲外 or actual_powerより小さい）
        try:
            query_outlier_capacity = f"""
            SELECT COUNT(*) as outlier_count
            FROM `{self.project_id}.{self.dataset_id}.energy_data_hourly`
            WHERE date >= '{period_start}'
              AND date <= '{period_end}'
              AND (supply_capacity < 1500 OR supply_capacity > 10000 OR supply_capacity < actual_power)
            """
            result = self.bq_client.query(query_outlier_capacity).result()
            outlier_count = list(result)[0]['outlier_count']

            status = 'OK' if outlier_count == 0 else ('WARNING' if outlier_count < 5 else 'ERROR')
            check_results.append({
                'check_date': str(check_date),
                'check_timestamp': check_timestamp.isoformat(),
                'data_type': 'power',
                'check_type': 'outlier',
                'check_target': 'supply_capacity',
                'issue_count': outlier_count,
                'issue_detail': f'supply_capacityが異常範囲（<1500 or >10000 or <actual_power）: {outlier_count}件',
                'check_period_start': str(period_start),
                'check_period_end': str(period_end),
                'status': status
            })
            print(f"  異常値チェック(supply_capacity): {status} (異常{outlier_count}件)")
        except Exception as e:
            raise Exception(f"電力データ: supply_capacity 異常値チェッククエリ実行失敗 - {str(e)}")

        print(f"電力データチェック完了: {len(check_results)}項目")
        return check_results

    def check_weather_data(self, days=7):
        """
        天気データの品質チェック

        Args:
            days (int): チェック対象日数（過去N日 + 今日から14日先予測）

        Returns:
            list: チェック結果のリスト
        """
        check_date = datetime.now().date()
        check_timestamp = datetime.now()
        # 過去N日（昨日まで）+ 今日から14日間の予測 = N + 14日分
        period_start = datetime.now().date() - timedelta(days=days)
        period_end = datetime.now().date() + timedelta(days=13)  # 今日+13日後（14日間）

        check_results = []
        print(f"天気データチェック開始: {period_start} ～ {period_end}")

        # 天気データは千葉県のみチェック
        # 1. レコード欠損チェック（期待: 24時間 × (過去N日 + 今日 + 未来13日) = 24 × (N + 14) レコード）
        try:
            total_days = days + 14  # 過去N日 + 今日 + 未来13日 = N + 14日分
            expected_records = 24 * total_days
            query_missing = f"""
            SELECT COUNT(*) as actual_count
            FROM `{self.project_id}.{self.dataset_id}.weather_data`
            WHERE date >= '{period_start}'
              AND date <= '{period_end}'
              AND prefecture = '千葉県'
            """
            result = self.bq_client.query(query_missing).result()
            actual_count = list(result)[0]['actual_count']
            missing_count = expected_records - actual_count

            status = 'OK' if missing_count == 0 else ('WARNING' if missing_count < 24 else 'ERROR')
            check_results.append({
                'check_date': str(check_date),
                'check_timestamp': check_timestamp.isoformat(),
                'data_type': 'weather',
                'check_type': 'missing',
                'check_target': '全体',
                'issue_count': missing_count,
                'issue_detail': f'期待レコード数: {expected_records}, 実際: {actual_count}, 欠損: {missing_count}',
                'check_period_start': str(period_start),
                'check_period_end': str(period_end),
                'status': status
            })
            print(f"  レコード欠損チェック: {status} (欠損{missing_count}件)")
        except Exception as e:
            raise Exception(f"天気データ: レコード欠損チェッククエリ実行失敗 - {str(e)}")

        # 2. NULL値チェック - temperature_2m
        try:
            query_null_temp = f"""
            SELECT COUNT(*) as null_count
            FROM `{self.project_id}.{self.dataset_id}.weather_data`
            WHERE date >= '{period_start}'
              AND date <= '{period_end}'
              AND prefecture = '千葉県'
              AND temperature_2m IS NULL
            """
            result = self.bq_client.query(query_null_temp).result()
            null_count = list(result)[0]['null_count']

            status = 'OK' if null_count == 0 else ('WARNING' if null_count < 10 else 'ERROR')
            check_results.append({
                'check_date': str(check_date),
                'check_timestamp': check_timestamp.isoformat(),
                'data_type': 'weather',
                'check_type': 'null',
                'check_target': 'temperature_2m',
                'issue_count': null_count,
                'issue_detail': f'temperature_2mがNULLのレコード: {null_count}件',
                'check_period_start': str(period_start),
                'check_period_end': str(period_end),
                'status': status
            })
            print(f"  NULL値チェック(temperature_2m): {status} (NULL {null_count}件)")
        except Exception as e:
            raise Exception(f"天気データ: temperature_2m NULL値チェッククエリ実行失敗 - {str(e)}")

        # 3. NULL値チェック - relative_humidity_2m
        try:
            query_null_humidity = f"""
            SELECT COUNT(*) as null_count
            FROM `{self.project_id}.{self.dataset_id}.weather_data`
            WHERE date >= '{period_start}'
              AND date <= '{period_end}'
              AND prefecture = '千葉県'
              AND relative_humidity_2m IS NULL
            """
            result = self.bq_client.query(query_null_humidity).result()
            null_count = list(result)[0]['null_count']

            status = 'OK' if null_count == 0 else ('WARNING' if null_count < 10 else 'ERROR')
            check_results.append({
                'check_date': str(check_date),
                'check_timestamp': check_timestamp.isoformat(),
                'data_type': 'weather',
                'check_type': 'null',
                'check_target': 'relative_humidity_2m',
                'issue_count': null_count,
                'issue_detail': f'relative_humidity_2mがNULLのレコード: {null_count}件',
                'check_period_start': str(period_start),
                'check_period_end': str(period_end),
                'status': status
            })
            print(f"  NULL値チェック(relative_humidity_2m): {status} (NULL {null_count}件)")
        except Exception as e:
            raise Exception(f"天気データ: relative_humidity_2m NULL値チェッククエリ実行失敗 - {str(e)}")

        # 4. 異常値チェック - temperature_2m（-10～50℃範囲外）
        try:
            query_outlier_temp = f"""
            SELECT COUNT(*) as outlier_count
            FROM `{self.project_id}.{self.dataset_id}.weather_data`
            WHERE date >= '{period_start}'
              AND date <= '{period_end}'
              AND prefecture = '千葉県'
              AND (temperature_2m < -10 OR temperature_2m > 50)
            """
            result = self.bq_client.query(query_outlier_temp).result()
            outlier_count = list(result)[0]['outlier_count']

            status = 'OK' if outlier_count == 0 else ('WARNING' if outlier_count < 5 else 'ERROR')
            check_results.append({
                'check_date': str(check_date),
                'check_timestamp': check_timestamp.isoformat(),
                'data_type': 'weather',
                'check_type': 'outlier',
                'check_target': 'temperature_2m',
                'issue_count': outlier_count,
                'issue_detail': f'temperature_2mが異常範囲（<-10 or >50）: {outlier_count}件',
                'check_period_start': str(period_start),
                'check_period_end': str(period_end),
                'status': status
            })
            print(f"  異常値チェック(temperature_2m): {status} (異常{outlier_count}件)")
        except Exception as e:
            raise Exception(f"天気データ: temperature_2m 異常値チェッククエリ実行失敗 - {str(e)}")

        # 5. 異常値チェック - relative_humidity_2m（0～100%範囲外）
        try:
            query_outlier_humidity = f"""
            SELECT COUNT(*) as outlier_count
            FROM `{self.project_id}.{self.dataset_id}.weather_data`
            WHERE date >= '{period_start}'
              AND date <= '{period_end}'
              AND prefecture = '千葉県'
              AND (relative_humidity_2m < 0 OR relative_humidity_2m > 100)
            """
            result = self.bq_client.query(query_outlier_humidity).result()
            outlier_count = list(result)[0]['outlier_count']

            status = 'OK' if outlier_count == 0 else ('WARNING' if outlier_count < 5 else 'ERROR')
            check_results.append({
                'check_date': str(check_date),
                'check_timestamp': check_timestamp.isoformat(),
                'data_type': 'weather',
                'check_type': 'outlier',
                'check_target': 'relative_humidity_2m',
                'issue_count': outlier_count,
                'issue_detail': f'relative_humidity_2mが異常範囲（<0 or >100）: {outlier_count}件',
                'check_period_start': str(period_start),
                'check_period_end': str(period_end),
                'status': status
            })
            print(f"  異常値チェック(relative_humidity_2m): {status} (異常{outlier_count}件)")
        except Exception as e:
            raise Exception(f"天気データ: relative_humidity_2m 異常値チェッククエリ実行失敗 - {str(e)}")

        # 6. 異常値チェック - precipitation（0～40mm範囲外）
        try:
            query_outlier_precip = f"""
            SELECT COUNT(*) as outlier_count
            FROM `{self.project_id}.{self.dataset_id}.weather_data`
            WHERE date >= '{period_start}'
              AND date <= '{period_end}'
              AND prefecture = '千葉県'
              AND (precipitation < 0 OR precipitation > 40)
            """
            result = self.bq_client.query(query_outlier_precip).result()
            outlier_count = list(result)[0]['outlier_count']

            status = 'OK' if outlier_count == 0 else ('WARNING' if outlier_count < 5 else 'ERROR')
            check_results.append({
                'check_date': str(check_date),
                'check_timestamp': check_timestamp.isoformat(),
                'data_type': 'weather',
                'check_type': 'outlier',
                'check_target': 'precipitation',
                'issue_count': outlier_count,
                'issue_detail': f'precipitationが異常範囲（<0 or >40）: {outlier_count}件',
                'check_period_start': str(period_start),
                'check_period_end': str(period_end),
                'status': status
            })
            print(f"  異常値チェック(precipitation): {status} (異常{outlier_count}件)")
        except Exception as e:
            raise Exception(f"天気データ: precipitation 異常値チェッククエリ実行失敗 - {str(e)}")

        print(f"天気データチェック完了: {len(check_results)}項目")
        return check_results

    def run_all_checks(self, days=7):
        """
        全データ品質チェックを実行

        Args:
            days (int): チェック対象日数（デフォルト: 7日）

        Returns:
            dict: 処理結果
        """
        # 実行ID・開始時刻記録
        execution_id = str(uuid.uuid4())
        started_at = datetime.now()
        target_date_str = datetime.now().strftime('%Y-%m-%d')

        print(f"データ品質チェック開始: 直近{days}日分, execution_id={execution_id}")

        try:
            # 1. 電力データチェック
            power_results = self.check_power_data(days)

            # 2. 天気データチェック
            weather_results = self.check_weather_data(days)

            # 3. チェック結果を保存
            all_results = power_results + weather_results
            self._save_check_results(all_results)

            # 4. エラー・ワーニングの集計
            error_count = sum(1 for r in all_results if r['status'] == 'ERROR')
            warning_count = sum(1 for r in all_results if r['status'] == 'WARNING')
            ok_count = sum(1 for r in all_results if r['status'] == 'OK')

            print(f"\nデータ品質チェック完了: ERROR={error_count}, WARNING={warning_count}, OK={ok_count}")

            # データ品質結果に応じたステータス判定
            if error_count > 0:
                overall_status = "ERROR"
            elif warning_count > 0:
                overall_status = "WARNING"
            else:
                overall_status = "OK"

            # 品質チェック結果ログ記録
            completed_at = datetime.now()
            duration_seconds = int((completed_at - started_at).total_seconds())

            log_data = {
                "execution_id": execution_id,
                "date": target_date_str,
                "process_type": "DATA_QUALITY_CHECK",
                "status": overall_status,
                "error_message": None,
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
                "duration_seconds": duration_seconds,
                "records_processed": len(all_results),
                "file_size_mb": None,
                "additional_info": json.dumps({
                    "days": days,
                    "total_checks": len(all_results),
                    "error_count": error_count,
                    "warning_count": warning_count,
                    "ok_count": ok_count
                })
            }
            self._write_log(log_data)

            return {
                'status': 'success',
                'message': f'品質チェック完了: ERROR={error_count}, WARNING={warning_count}, OK={ok_count}',
                'total_checks': len(all_results),
                'error_count': error_count,
                'warning_count': warning_count,
                'ok_count': ok_count
            }

        except Exception as e:
            print(f"データ品質チェック失敗: {e}")

            # 失敗ログ記録
            completed_at = datetime.now()
            duration_seconds = int((completed_at - started_at).total_seconds())

            log_data = {
                "execution_id": execution_id,
                "date": target_date_str,
                "process_type": "DATA_QUALITY_CHECK",
                "status": "FAILED",
                "error_message": str(e),
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
                "duration_seconds": duration_seconds,
                "records_processed": None,
                "file_size_mb": None,
                "additional_info": json.dumps({
                    "days": days
                })
            }
            self._write_log(log_data)

            return {
                'status': 'failed',
                'message': f'品質チェック失敗: {str(e)}',
                'total_checks': 0,
                'error_count': 0,
                'warning_count': 0,
                'ok_count': 0
            }


def print_check_results(results):
    """チェック結果を表示"""
    print(f"\n{'='*60}")
    print("データ品質チェック結果")
    print('='*60)

    status_mark = '成功' if results['status'] == 'success' else '失敗'

    print(f"\n処理結果: {status_mark}")
    print(f"メッセージ: {results['message']}")
    print(f"総チェック項目数: {results['total_checks']}")
    print(f"  - ERROR: {results['error_count']}")
    print(f"  - WARNING: {results['warning_count']}")
    print(f"  - OK: {results['ok_count']}")
    print('='*60)


def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(description='データ品質監視システム')
    parser.add_argument('--days', type=int, default=7,
                       help='チェック対象日数（デフォルト: 7日）')
    parser.add_argument('--project-id', type=str, default='energy-env',
                       help='GCPプロジェクトID')

    args = parser.parse_args()

    print("データ品質監視システム開始")
    print(f"プロジェクト: {args.project_id}")
    print(f"対象範囲: 直近{args.days}日分")

    # チェック処理実行
    checker = DataQualityChecker(args.project_id)
    results = checker.run_all_checks(args.days)

    # 結果表示
    print_check_results(results)

    # 失敗時はexit code 1を返す
    if results['status'] == 'failed':
        import sys
        sys.exit(1)

    print("処理完了")


if __name__ == "__main__":
    main()
