"""
ml_featuresテーブル差分更新モジュール

電力・天気データ投入後に実行し、ml_featuresテーブルを最新化する。
過去7日分を削除→再投入する方式で効率的に更新。

実行方法:
    python -m src.data_processing.ml_features_updater
"""

import json
import os
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from google.cloud import bigquery


class MLFeaturesUpdater:
    """ml_features差分更新クラス"""

    def __init__(self, project_id="energy-env"):
        """
        初期化

        Args:
            project_id (str): GCPプロジェクトID
        """
        self.project_id = project_id
        self.dataset_id = "prod_energy_data"
        self.table_id = "ml_features"

        # 環境変数チェック
        energy_env_path = os.getenv('ENERGY_ENV_PATH')
        if energy_env_path is None:
            raise ValueError("ENERGY_ENV_PATH環境変数が設定されていません")

        # ログディレクトリ設定
        self.log_dir = Path(energy_env_path) / 'logs' / 'ml_features_updater'
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # BigQueryクライアント初期化
        self.bq_client = bigquery.Client(project=project_id)

        # BQログテーブル設定
        self.bq_log_table_id = f"{self.project_id}.{self.dataset_id}.process_execution_log"

        print(f"MLFeaturesUpdater初期化完了: {project_id}")

    def delete_recent_data(self):
        """
        過去7日分のデータを削除

        Returns:
            int: 削除行数

        Raises:
            Exception: BigQueryエラー時
        """
        try:
            delete_query = f"""
            DELETE FROM `{self.project_id}.{self.dataset_id}.{self.table_id}`
            WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 7 DAY)
            """

            job = self.bq_client.query(delete_query)
            job.result()  # クエリ完了を待機
            deleted_rows = job.num_dml_affected_rows

            print(f"過去7日分のデータ削除完了: {deleted_rows}行削除")
            return deleted_rows

        except Exception as e:
            error_msg = f"データ削除SQL実行失敗: {e}"
            print(error_msg)
            raise Exception(error_msg)

    def insert_ml_features(self):
        """
        過去7日分のml_featuresデータを再投入
        create_ml_features_table.sqlのロジックを流用

        Returns:
            int: 投入行数

        Raises:
            Exception: BigQueryエラー時
        """
        try:
            insert_query = f"""
            INSERT INTO `{self.project_id}.{self.dataset_id}.{self.table_id}` (
                date, hour, actual_power, supply_capacity,
                temperature_2m, relative_humidity_2m, precipitation, weather_code,
                day_of_week, is_weekend, is_holiday, month,
                hour_sin, hour_cos,
                lag_1_day, lag_7_day, lag_1_business_day
            )
            WITH energy_filtered AS (
              SELECT
                date,
                hour,
                actual_power,
                supply_capacity
              FROM `{self.project_id}.{self.dataset_id}.energy_data_hourly`
              WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 7 DAY)
            ),
            weather_filtered AS (
              SELECT
                date,
                hour,
                temperature_2m,
                relative_humidity_2m,
                precipitation,
                weather_code
              FROM `{self.project_id}.{self.dataset_id}.weather_data`
              WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 7 DAY)
                AND prefecture = '千葉県'
            ),
            calendar_filtered AS (
              SELECT
                date,
                day_of_week,
                is_weekend,
                is_holiday
              FROM `{self.project_id}.{self.dataset_id}.calendar_data`
              WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 7 DAY)
            ),
            lag_mapping_filtered AS (
              SELECT
                base_date,
                lag_1_day_date,
                lag_7_day_date,
                lag_1_business_date
              FROM `{self.project_id}.{self.dataset_id}.date_lag_mapping`
              WHERE base_date >= DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 7 DAY)
            ),
            base_data AS (
              SELECT
                energy.date,
                energy.hour,
                energy.actual_power,
                energy.supply_capacity,
                weather.temperature_2m,
                weather.relative_humidity_2m,
                weather.precipitation,
                weather.weather_code,
                calendar.day_of_week,
                calendar.is_weekend,
                calendar.is_holiday,
                EXTRACT(MONTH FROM energy.date) as month
              FROM energy_filtered energy
              LEFT JOIN weather_filtered weather
                ON energy.date = weather.date
                AND energy.hour = CAST(weather.hour AS INT64)
              LEFT JOIN calendar_filtered calendar
                ON energy.date = calendar.date
            )
            SELECT
              base.date,
              base.hour,
              base.actual_power,
              base.supply_capacity,
              base.temperature_2m,
              base.relative_humidity_2m,
              base.precipitation,
              base.weather_code,
              base.day_of_week,
              base.is_weekend,
              base.is_holiday,
              base.month,

              -- 循環特徴量（時間の周期性）
              SIN(2 * 3.141592653589793 * base.hour / 24) as hour_sin,
              COS(2 * 3.141592653589793 * base.hour / 24) as hour_cos,

              -- lag特徴量（予測で使用する3つ）
              lag1.actual_power as lag_1_day,
              lag7.actual_power as lag_7_day,
              blag1.actual_power as lag_1_business_day

            FROM base_data base
            LEFT JOIN lag_mapping_filtered dlm
              ON base.date = dlm.base_date
            LEFT JOIN base_data lag1
              ON lag1.date = dlm.lag_1_day_date AND lag1.hour = base.hour
            LEFT JOIN base_data lag7
              ON lag7.date = dlm.lag_7_day_date AND lag7.hour = base.hour
            LEFT JOIN base_data blag1
              ON blag1.date = dlm.lag_1_business_date AND blag1.hour = base.hour
            """

            job = self.bq_client.query(insert_query)
            job.result()  # クエリ完了を待機
            inserted_rows = job.num_dml_affected_rows

            print(f"ml_featuresデータ投入完了: {inserted_rows}行")
            return inserted_rows

        except Exception as e:
            error_msg = f"データ投入SQL実行失敗: {e}"
            print(error_msg)
            raise Exception(error_msg)

    def _write_log(self, log_data):
        """
        ログをローカルファイルとBigQueryに記録

        Args:
            log_data (dict): ログデータ
        """
        # ローカルファイルに記録
        log_date = datetime.now(ZoneInfo('Asia/Tokyo')).strftime('%Y-%m-%d')
        log_file = self.log_dir / f"{log_date}_ml_features_update_execution.jsonl"

        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_data, ensure_ascii=False) + '\n')
        except Exception as e:
            print(f"ログファイル書き込み失敗: {e}")

        # BigQueryに記録
        try:
            errors = self.bq_client.insert_rows_json(self.bq_log_table_id, [log_data])
            if errors:
                raise Exception(f"BigQueryログ投入エラー: {errors}")
        except Exception as e:
            # BQエラーをローカルログにも記録
            error_log = {
                'timestamp': datetime.now(ZoneInfo('Asia/Tokyo')).isoformat(),
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

    def update_ml_features(self):
        """
        ml_featuresテーブル更新のメイン処理

        処理フロー:
        1. 過去7日分のデータを削除
        2. 過去7日分のデータを再投入

        Returns:
            dict: 処理結果
        """
        # 実行ID・開始時刻記録
        execution_id = str(uuid.uuid4())
        started_at = datetime.now(ZoneInfo('Asia/Tokyo'))
        target_date_str = datetime.now(ZoneInfo('Asia/Tokyo')).strftime('%Y-%m-%d')

        print(f"ml_features更新開始: execution_id={execution_id}")

        try:
            # 1. 過去7日分のデータ削除
            deleted_rows = self.delete_recent_data()

            # 2. 過去7日分のデータを再投入
            inserted_rows = self.insert_ml_features()

            print(f"ml_features更新完了: 削除{deleted_rows}行, 挿入{inserted_rows}行")

            # 成功ログ記録
            completed_at = datetime.now(ZoneInfo('Asia/Tokyo'))
            duration_seconds = int((completed_at - started_at).total_seconds())

            log_data = {
                "execution_id": execution_id,
                "date": target_date_str,
                "process_type": "ML_FEATURES_UPDATE",
                "status": "SUCCESS",
                "error_message": None,
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
                "duration_seconds": duration_seconds,
                "records_processed": inserted_rows,
                "file_size_mb": None,
                "additional_info": json.dumps({
                    "deleted_rows": deleted_rows,
                    "inserted_rows": inserted_rows
                })
            }
            self._write_log(log_data)

            return {
                'status': 'success',
                'message': f'ml_features更新成功',
                'deleted_rows': deleted_rows,
                'inserted_rows': inserted_rows
            }

        except Exception as e:
            print(f"ml_features更新失敗: {e}")

            # 失敗ログ記録
            completed_at = datetime.now(ZoneInfo('Asia/Tokyo'))
            duration_seconds = int((completed_at - started_at).total_seconds())

            log_data = {
                "execution_id": execution_id,
                "date": target_date_str,
                "process_type": "ML_FEATURES_UPDATE",
                "status": "FAILED",
                "error_message": str(e),
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
                "duration_seconds": duration_seconds,
                "records_processed": None,
                "file_size_mb": None,
                "additional_info": None
            }
            self._write_log(log_data)

            return {
                'status': 'failed',
                'message': f'更新失敗: {str(e)}',
                'deleted_rows': 0,
                'inserted_rows': 0
            }


def print_update_results(results):
    """更新結果を表示"""
    print(f"\n{'='*60}")
    print("ml_features更新結果")
    print('='*60)

    status_mark = '成功' if results['status'] == 'success' else '失敗'

    print(f"\n処理結果: {status_mark}")
    print(f"メッセージ: {results['message']}")
    print(f"削除レコード数: {results['deleted_rows']}")
    print(f"挿入レコード数: {results['inserted_rows']}")
    print('='*60)


def main():
    """メイン関数"""
    print("ml_features更新システム開始")

    # 更新処理実行
    updater = MLFeaturesUpdater()
    results = updater.update_ml_features()

    # 結果表示
    print_update_results(results)

    # 失敗時はexit code 1を返す
    if results['status'] == 'failed':
        import sys
        sys.exit(1)

    print("処理完了")


if __name__ == "__main__":
    main()
