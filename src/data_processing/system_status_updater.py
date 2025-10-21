"""
システム監視ステータス更新システム

Looker Studio監視ページ用のsystem_statusテーブルを更新する。
process_execution_logとdata_quality_checksから最新状態を取得して1レコードに集約。

実行方法:
    python -m src.data_processing.system_status_updater
"""

import json
import os
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from google.cloud import bigquery


class SystemStatusUpdater:
    """システム監視ステータス更新クラス"""

    def __init__(self, project_id="energy-env"):
        """
        初期化

        Args:
            project_id (str): GCPプロジェクトID
        """
        self.project_id = project_id
        self.dataset_id = "prod_energy_data"
        self.table_id = "system_status"

        # 環境変数チェック
        energy_env_path = os.getenv('ENERGY_ENV_PATH')
        if energy_env_path is None:
            raise ValueError("ENERGY_ENV_PATH環境変数が設定されていません")

        # ログディレクトリ設定
        self.log_dir = Path(energy_env_path) / 'logs' / 'system_status_updater'
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # BigQueryクライアント初期化
        self.bq_client = bigquery.Client(project=project_id)

        # BQログテーブル設定
        self.bq_log_table_id = f"{self.project_id}.{self.dataset_id}.process_execution_log"

        print(f"SystemStatusUpdater初期化完了: {project_id}")

    def delete_all_records(self):
        """
        全レコード削除

        Returns:
            int: 削除行数

        Raises:
            Exception: BigQueryエラー時
        """
        try:
            delete_query = f"""
            DELETE FROM `{self.project_id}.{self.dataset_id}.{self.table_id}`
            WHERE TRUE
            """

            job = self.bq_client.query(delete_query)
            job.result()
            deleted_rows = job.num_dml_affected_rows

            print(f"全レコード削除完了: {deleted_rows}行削除")
            return deleted_rows

        except Exception as e:
            error_msg = f"全レコード削除SQL実行失敗: {e}"
            print(error_msg)
            raise Exception(error_msg)

    def insert_latest_status(self):
        """
        最新ステータスを1レコード投入

        process_execution_logとdata_quality_checksから最新データを取得し、
        OK/ERROR/WARNINGに変換してsystem_statusに投入。

        Returns:
            int: 投入行数（常に1）

        Raises:
            Exception: BigQueryエラー時
        """
        try:
            insert_query = f"""
            INSERT INTO `{self.project_id}.{self.dataset_id}.{self.table_id}` (
                updated_at,
                tepco_api_status,
                weather_api_status,
                ml_features_update_status,
                ml_prediction_status,
                prediction_accuracy_update_status,
                data_quality_status,
                dashboard_update_status,
                tepco_api_message,
                weather_api_message,
                ml_features_update_message,
                ml_prediction_message,
                prediction_accuracy_update_message,
                data_quality_message,
                dashboard_update_message
            )
            WITH latest_process_status AS (
              -- process_execution_logから各プロセスの最新ステータスを取得
              SELECT
                process_type,
                status,
                error_message,
                ROW_NUMBER() OVER (
                  PARTITION BY process_type
                  ORDER BY started_at DESC
                ) as rn
              FROM `{self.project_id}.{self.dataset_id}.process_execution_log`
              WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 2 DAY)
            ),
            latest_quality_check AS (
              -- data_quality_checksから最新のチェック結果を取得
              SELECT
                status,
                issue_detail,
                ROW_NUMBER() OVER (
                  ORDER BY check_timestamp DESC
                ) as rn
              FROM `{self.project_id}.{self.dataset_id}.data_quality_checks`
              WHERE check_date >= DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 2 DAY)
            )
            SELECT
              CURRENT_DATETIME('Asia/Tokyo') AS updated_at,

              -- 各プロセスのステータス（SUCCESS→OK, FAILED→ERROR）
              CASE
                WHEN MAX(CASE WHEN process_type = 'TEPCO_API' AND rn = 1 THEN status END) = 'SUCCESS' THEN 'OK'
                WHEN MAX(CASE WHEN process_type = 'TEPCO_API' AND rn = 1 THEN status END) = 'FAILED' THEN 'ERROR'
                ELSE 'WARNING'
              END AS tepco_api_status,

              CASE
                WHEN MAX(CASE WHEN process_type = 'WEATHER_API' AND rn = 1 THEN status END) = 'SUCCESS' THEN 'OK'
                WHEN MAX(CASE WHEN process_type = 'WEATHER_API' AND rn = 1 THEN status END) = 'FAILED' THEN 'ERROR'
                ELSE 'WARNING'
              END AS weather_api_status,

              CASE
                WHEN MAX(CASE WHEN process_type = 'ML_FEATURES_UPDATE' AND rn = 1 THEN status END) = 'SUCCESS' THEN 'OK'
                WHEN MAX(CASE WHEN process_type = 'ML_FEATURES_UPDATE' AND rn = 1 THEN status END) = 'FAILED' THEN 'ERROR'
                ELSE 'WARNING'
              END AS ml_features_update_status,

              CASE
                WHEN MAX(CASE WHEN process_type = 'ML_PREDICTION' AND rn = 1 THEN status END) = 'SUCCESS' THEN 'OK'
                WHEN MAX(CASE WHEN process_type = 'ML_PREDICTION' AND rn = 1 THEN status END) = 'FAILED' THEN 'ERROR'
                ELSE 'WARNING'
              END AS ml_prediction_status,

              CASE
                WHEN MAX(CASE WHEN process_type = 'PREDICTION_ACCURACY_UPDATE' AND rn = 1 THEN status END) = 'SUCCESS' THEN 'OK'
                WHEN MAX(CASE WHEN process_type = 'PREDICTION_ACCURACY_UPDATE' AND rn = 1 THEN status END) = 'FAILED' THEN 'ERROR'
                ELSE 'WARNING'
              END AS prediction_accuracy_update_status,

              -- データ品質ステータス（OK/WARNING/ERROR）
              COALESCE(
                (SELECT status FROM latest_quality_check WHERE rn = 1),
                'WARNING'
              ) AS data_quality_status,

              CASE
                WHEN MAX(CASE WHEN process_type = 'DASHBOARD_UPDATE' AND rn = 1 THEN status END) = 'SUCCESS' THEN 'OK'
                WHEN MAX(CASE WHEN process_type = 'DASHBOARD_UPDATE' AND rn = 1 THEN status END) = 'FAILED' THEN 'ERROR'
                ELSE 'WARNING'
              END AS dashboard_update_status,

              -- 各プロセスのエラーメッセージ
              MAX(CASE WHEN process_type = 'TEPCO_API' AND rn = 1 THEN error_message END) AS tepco_api_message,
              MAX(CASE WHEN process_type = 'WEATHER_API' AND rn = 1 THEN error_message END) AS weather_api_message,
              MAX(CASE WHEN process_type = 'ML_FEATURES_UPDATE' AND rn = 1 THEN error_message END) AS ml_features_update_message,
              MAX(CASE WHEN process_type = 'ML_PREDICTION' AND rn = 1 THEN error_message END) AS ml_prediction_message,
              MAX(CASE WHEN process_type = 'PREDICTION_ACCURACY_UPDATE' AND rn = 1 THEN error_message END) AS prediction_accuracy_update_message,

              -- データ品質チェックの詳細メッセージ
              (SELECT issue_detail FROM latest_quality_check WHERE rn = 1) AS data_quality_message,

              -- ダッシュボード更新のエラーメッセージ
              MAX(CASE WHEN process_type = 'DASHBOARD_UPDATE' AND rn = 1 THEN error_message END) AS dashboard_update_message

            FROM latest_process_status
            """

            job = self.bq_client.query(insert_query)
            job.result()
            inserted_rows = job.num_dml_affected_rows

            print(f"最新ステータス投入完了: {inserted_rows}行")
            return inserted_rows

        except Exception as e:
            error_msg = f"最新ステータス投入SQL実行失敗: {e}"
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
        log_file = self.log_dir / f"{log_date}_system_status_update_execution.jsonl"

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

    def update_system_status(self):
        """
        システム監視ステータス更新のメイン処理

        処理フロー:
        1. 全レコード削除
        2. 最新ステータスを1レコード投入

        Returns:
            dict: 処理結果
        """
        # 実行ID・開始時刻記録
        execution_id = str(uuid.uuid4())
        started_at = datetime.now(ZoneInfo('Asia/Tokyo'))
        target_date_str = datetime.now(ZoneInfo('Asia/Tokyo')).strftime('%Y-%m-%d')

        print(f"system_status更新開始: execution_id={execution_id}")

        try:
            # 1. 全レコード削除
            deleted_rows = self.delete_all_records()

            # 2. 最新ステータスを1レコード投入
            inserted_rows = self.insert_latest_status()

            print(f"system_status更新完了: 削除{deleted_rows}行, 挿入{inserted_rows}行")

            # 成功ログ記録
            completed_at = datetime.now(ZoneInfo('Asia/Tokyo'))
            duration_seconds = int((completed_at - started_at).total_seconds())

            log_data = {
                "execution_id": execution_id,
                "date": target_date_str,
                "process_type": "SYSTEM_STATUS_UPDATE",
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
                'message': 'システム監視ステータス更新成功',
                'deleted_rows': deleted_rows,
                'inserted_rows': inserted_rows
            }

        except Exception as e:
            print(f"system_status更新失敗: {e}")

            # 失敗ログ記録
            completed_at = datetime.now(ZoneInfo('Asia/Tokyo'))
            duration_seconds = int((completed_at - started_at).total_seconds())

            log_data = {
                "execution_id": execution_id,
                "date": target_date_str,
                "process_type": "SYSTEM_STATUS_UPDATE",
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
    print("システム監視ステータス更新結果")
    print('='*60)

    status_mark = '成功' if results['status'] == 'success' else '失敗'

    print(f"\n処理結果: {status_mark}")
    print(f"メッセージ: {results['message']}")
    print(f"削除レコード数: {results['deleted_rows']}")
    print(f"挿入レコード数: {results['inserted_rows']}")
    print('='*60)


def main():
    """メイン関数"""
    print("system_status更新システム開始")

    # 更新処理実行
    updater = SystemStatusUpdater()
    results = updater.update_system_status()

    # 結果表示
    print_update_results(results)

    # 失敗時はexit code 1を返す
    if results['status'] == 'failed':
        import sys
        sys.exit(1)

    print("処理完了")


if __name__ == "__main__":
    main()
