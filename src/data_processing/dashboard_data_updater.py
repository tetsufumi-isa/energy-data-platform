"""
ダッシュボードデータ更新システム

Looker Studio用のdashboard_dataテーブルを更新する。
電力・天気・カレンダー・予測データを統合して投入。

実行方法:
    python -m src.data_processing.dashboard_data_updater
"""

import json
import os
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from google.cloud import bigquery


class DashboardDataUpdater:
    """ダッシュボードデータ更新クラス"""

    def __init__(self, project_id="energy-env"):
        """
        初期化

        Args:
            project_id (str): GCPプロジェクトID
        """
        self.project_id = project_id
        self.dataset_id = "prod_energy_data"
        self.table_id = "dashboard_data"

        # 環境変数チェック
        energy_env_path = os.getenv('ENERGY_ENV_PATH')
        if energy_env_path is None:
            raise ValueError("ENERGY_ENV_PATH環境変数が設定されていません")

        # ログディレクトリ設定
        self.log_dir = Path(energy_env_path) / 'logs' / 'dashboard_updater'
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # BigQueryクライアント初期化
        self.bq_client = bigquery.Client(project=project_id)

        # BQログテーブル設定
        self.bq_log_table_id = f"{self.project_id}.{self.dataset_id}.process_execution_log"

        print(f"DashboardDataUpdater初期化完了: {project_id}")

    def delete_future_data(self):
        """
        7日前以降のデータを全削除

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
            job.result()  # クエリ完了を待機（返り値は使用しない）
            deleted_rows = job.num_dml_affected_rows

            print(f"7日前以降のデータ削除完了: {deleted_rows}行削除")
            return deleted_rows

        except Exception as e:
            error_msg = f"データ削除SQL実行失敗: {e}"
            print(error_msg)
            raise Exception(error_msg)

    def insert_dashboard_data_direct(self):
        """
        BigQuery内で直接INSERT
        各テーブルからデータを統合してdashboard_dataに投入

        Returns:
            int: 投入行数

        Raises:
            Exception: BigQueryエラー時
        """
        try:
            insert_query = f"""
            INSERT INTO `{self.project_id}.{self.dataset_id}.{self.table_id}` (
                date, hour, actual_power, supply_capacity, predicted_power,
                error_absolute, error_percentage,
                temperature_2m, relative_humidity_2m, precipitation, weather_code,
                day_of_week, is_weekend, is_holiday,
                usage_rate, weekday_jp
            )
            WITH latest_energy AS (
              -- 最新の電力データのみを取得（重複排除）
              SELECT
                date,
                hour,
                actual_power,
                supply_capacity,
                ROW_NUMBER() OVER (
                  PARTITION BY date, hour
                  ORDER BY created_at DESC
                ) as rn
              FROM `{self.project_id}.{self.dataset_id}.energy_data_hourly`
              WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 7 DAY)
            ),
            latest_weather AS (
              -- 最新の天気データのみを取得（重複排除）
              SELECT
                date,
                hour,
                temperature_2m,
                relative_humidity_2m,
                precipitation,
                weather_code,
                ROW_NUMBER() OVER (
                  PARTITION BY date, hour
                  ORDER BY created_at DESC
                ) as rn
              FROM `{self.project_id}.{self.dataset_id}.weather_data`
              WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 7 DAY)
                AND prefecture = '千葉県'
            ),
            latest_predictions AS (
              -- 最新の予測データのみを取得
              SELECT
                prediction_date,
                prediction_hour,
                predicted_power_kwh,
                ROW_NUMBER() OVER (
                  PARTITION BY prediction_date, prediction_hour
                  ORDER BY created_at DESC
                ) as rn
              FROM `{self.project_id}.{self.dataset_id}.prediction_results`
              WHERE prediction_date >= DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 7 DAY)
            )
            SELECT
              e.date,
              e.hour,
              e.actual_power,
              e.supply_capacity,
              p.predicted_power_kwh AS predicted_power,

              -- 誤差計算（予測データがある場合のみ）
              CASE
                WHEN p.predicted_power_kwh IS NOT NULL AND e.actual_power IS NOT NULL
                THEN ABS(p.predicted_power_kwh - e.actual_power)
                ELSE NULL
              END AS error_absolute,

              CASE
                WHEN p.predicted_power_kwh IS NOT NULL AND e.actual_power IS NOT NULL AND e.actual_power > 0
                THEN (ABS(p.predicted_power_kwh - e.actual_power) / e.actual_power) * 100
                ELSE NULL
              END AS error_percentage,

              -- 天気データ
              w.temperature_2m,
              w.relative_humidity_2m,
              w.precipitation,
              w.weather_code,

              -- カレンダー情報
              c.day_of_week,
              c.is_weekend,
              c.is_holiday,

              -- 使用率計算
              CASE
                WHEN e.supply_capacity > 0
                THEN ROUND((e.actual_power / e.supply_capacity) * 100, 1)
                ELSE NULL
              END AS usage_rate,

              -- 曜日日本語表記
              CASE c.day_of_week
                WHEN 'Monday' THEN '月'
                WHEN 'Tuesday' THEN '火'
                WHEN 'Wednesday' THEN '水'
                WHEN 'Thursday' THEN '木'
                WHEN 'Friday' THEN '金'
                WHEN 'Saturday' THEN '土'
                WHEN 'Sunday' THEN '日'
                ELSE NULL
              END AS weekday_jp

            FROM latest_energy e

            -- 最新の天気データを結合（重複なし）
            LEFT JOIN latest_weather w
              ON e.date = w.date
              AND e.hour = CAST(w.hour AS INT64)
              AND w.rn = 1

            -- カレンダー情報を結合
            LEFT JOIN `{self.project_id}.{self.dataset_id}.calendar_data` c
              ON e.date = c.date

            -- 最新の予測データを結合
            LEFT JOIN latest_predictions p
              ON e.date = p.prediction_date
              AND e.hour = p.prediction_hour
              AND p.rn = 1

            WHERE e.rn = 1
            """

            job = self.bq_client.query(insert_query)
            job.result()  # クエリ完了を待機
            inserted_rows = job.num_dml_affected_rows

            print(f"ダッシュボードデータ投入完了: {inserted_rows}行")
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
        log_file = self.log_dir / f"{log_date}_dashboard_update_execution.jsonl"

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

    def update_dashboard_data(self):
        """
        ダッシュボードデータ更新のメイン処理

        処理フロー:
        1. 今日以降のデータを全削除
        2. 各テーブルからデータを統合取得
        3. dashboard_dataに投入

        Returns:
            dict: 処理結果
        """
        # 実行ID・開始時刻記録
        execution_id = str(uuid.uuid4())
        started_at = datetime.now(ZoneInfo('Asia/Tokyo'))
        target_date_str = datetime.now(ZoneInfo('Asia/Tokyo')).strftime('%Y-%m-%d')

        print(f"ダッシュボードデータ更新開始: execution_id={execution_id}")

        try:
            # 1. 今日以降のデータ削除
            deleted_rows = self.delete_future_data()

            # 2. BigQuery内で統合データを直接投入
            inserted_rows = self.insert_dashboard_data_direct()

            print(f"ダッシュボードデータ更新完了: 削除{deleted_rows}行, 挿入{inserted_rows}行")

            # 成功ログ記録
            completed_at = datetime.now(ZoneInfo('Asia/Tokyo'))
            duration_seconds = (completed_at - started_at).total_seconds()

            log_data = {
                "execution_id": execution_id,
                "date": target_date_str,
                "process_type": "DASHBOARD_UPDATE",
                "status": "SUCCESS",
                "error_message": None,
                "started_at": started_at.replace(tzinfo=None).isoformat(),
                "completed_at": completed_at.replace(tzinfo=None).isoformat(),
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
                'message': f'ダッシュボードデータ更新成功',
                'deleted_rows': deleted_rows,
                'inserted_rows': inserted_rows
            }

        except Exception as e:
            print(f"ダッシュボードデータ更新失敗: {e}")

            # 失敗ログ記録
            completed_at = datetime.now(ZoneInfo('Asia/Tokyo'))
            duration_seconds = (completed_at - started_at).total_seconds()

            log_data = {
                "execution_id": execution_id,
                "date": target_date_str,
                "process_type": "DASHBOARD_UPDATE",
                "status": "FAILED",
                "error_message": str(e),
                "started_at": started_at.replace(tzinfo=None).isoformat(),
                "completed_at": completed_at.replace(tzinfo=None).isoformat(),
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
    print("ダッシュボードデータ更新結果")
    print('='*60)

    status_mark = '成功' if results['status'] == 'success' else '失敗'

    print(f"\n処理結果: {status_mark}")
    print(f"メッセージ: {results['message']}")
    print(f"削除レコード数: {results['deleted_rows']}")
    print(f"挿入レコード数: {results['inserted_rows']}")
    print('='*60)


def main():
    """メイン関数"""
    print("ダッシュボードデータ更新システム開始")

    # 更新処理実行
    updater = DashboardDataUpdater()
    results = updater.update_dashboard_data()

    # 結果表示
    print_update_results(results)

    # 失敗時はexit code 1を返す
    if results['status'] == 'failed':
        import sys
        sys.exit(1)

    print("処理完了")


if __name__ == "__main__":
    main()
