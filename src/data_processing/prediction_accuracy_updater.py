"""
prediction_accuracyテーブル更新モジュール

予測値と実績値を紐付けて精度分析用テーブルを更新する。
過去7日分を削除→再投入する方式で効率的に更新。

実行方法:
    python -m src.data_processing.prediction_accuracy_updater
"""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from google.cloud import bigquery


class PredictionAccuracyUpdater:
    """prediction_accuracy更新クラス"""

    def __init__(self, project_id="energy-env"):
        """
        初期化

        Args:
            project_id (str): GCPプロジェクトID
        """
        self.project_id = project_id
        self.dataset_id = "prod_energy_data"
        self.table_id = "prediction_accuracy"

        # 環境変数チェック
        energy_env_path = os.getenv('ENERGY_ENV_PATH')
        if energy_env_path is None:
            raise ValueError("ENERGY_ENV_PATH環境変数が設定されていません")

        # ログディレクトリ設定
        self.log_dir = Path(energy_env_path) / 'logs' / 'prediction_accuracy_updater'
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # BigQueryクライアント初期化
        self.bq_client = bigquery.Client(project=project_id)

        # BQログテーブル設定
        self.bq_log_table_id = f"{self.project_id}.{self.dataset_id}.process_execution_log"

        print(f"PredictionAccuracyUpdater初期化完了: {project_id}")

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
            WHERE prediction_date >= DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 7 DAY)
              AND prediction_date < CURRENT_DATE('Asia/Tokyo')
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

    def insert_prediction_accuracy(self):
        """
        過去7日分のprediction_accuracyデータを再投入
        prediction_resultsとenergy_data_hourlyをJOINして精度計算

        Returns:
            int: 投入行数

        Raises:
            Exception: BigQueryエラー時
        """
        try:
            insert_query = f"""
            INSERT INTO `{self.project_id}.{self.dataset_id}.{self.table_id}` (
                execution_id,
                prediction_run_date,
                prediction_date,
                prediction_hour,
                predicted_power,
                actual_power,
                error_absolute,
                error_percentage,
                days_ahead,
                created_at
            )
            WITH prediction_filtered AS (
              SELECT
                execution_id,
                DATE(created_at, 'Asia/Tokyo') AS prediction_run_date,
                prediction_date,
                prediction_hour,
                predicted_power_kwh AS predicted_power,
                created_at
              FROM `{self.project_id}.{self.dataset_id}.prediction_results`
              WHERE prediction_date >= DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 7 DAY)
                AND prediction_date < CURRENT_DATE('Asia/Tokyo')  -- 実績確定済みデータのみ（今日は除外）
            ),
            energy_filtered AS (
              SELECT
                date,
                hour,
                actual_power
              FROM `{self.project_id}.{self.dataset_id}.energy_data_hourly`
              WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 7 DAY)
                AND date < CURRENT_DATE('Asia/Tokyo')
            )
            SELECT
              pred.execution_id,
              pred.prediction_run_date,
              pred.prediction_date,
              pred.prediction_hour,
              pred.predicted_power,
              energy.actual_power,
              ABS(pred.predicted_power - energy.actual_power) AS error_absolute,
              ABS(pred.predicted_power - energy.actual_power) / NULLIF(energy.actual_power, 0) * 100 AS error_percentage,
              DATE_DIFF(pred.prediction_date, pred.prediction_run_date, DAY) AS days_ahead,
              CURRENT_TIMESTAMP() AS created_at
            FROM prediction_filtered pred
            INNER JOIN energy_filtered energy
              ON pred.prediction_date = energy.date
              AND pred.prediction_hour = energy.hour
            """

            job = self.bq_client.query(insert_query)
            job.result()  # クエリ完了を待機
            inserted_rows = job.num_dml_affected_rows

            print(f"prediction_accuracyデータ投入完了: {inserted_rows}行")
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
        log_date = datetime.now().strftime('%Y-%m-%d')
        log_file = self.log_dir / f"{log_date}_prediction_accuracy_update_execution.jsonl"

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

    def update_prediction_accuracy(self):
        """
        prediction_accuracyテーブル更新のメイン処理

        処理フロー:
        1. 過去7日分のデータを削除
        2. 過去7日分の予測値+実績値をJOINして再投入

        Returns:
            dict: 処理結果
        """
        # 実行ID・開始時刻記録
        execution_id = str(uuid.uuid4())
        started_at = datetime.now()
        target_date_str = datetime.now().strftime('%Y-%m-%d')

        print(f"prediction_accuracy更新開始: execution_id={execution_id}")

        try:
            # 1. 過去7日分のデータ削除
            deleted_rows = self.delete_recent_data()

            # 2. 過去7日分のデータを再投入
            inserted_rows = self.insert_prediction_accuracy()

            print(f"prediction_accuracy更新完了: 削除{deleted_rows}行, 挿入{inserted_rows}行")

            # 成功ログ記録
            completed_at = datetime.now()
            duration_seconds = int((completed_at - started_at).total_seconds())

            log_data = {
                "execution_id": execution_id,
                "date": target_date_str,
                "process_type": "PREDICTION_ACCURACY_UPDATE",
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
                'message': f'prediction_accuracy更新成功',
                'deleted_rows': deleted_rows,
                'inserted_rows': inserted_rows
            }

        except Exception as e:
            print(f"prediction_accuracy更新失敗: {e}")

            # 失敗ログ記録
            completed_at = datetime.now()
            duration_seconds = int((completed_at - started_at).total_seconds())

            log_data = {
                "execution_id": execution_id,
                "date": target_date_str,
                "process_type": "PREDICTION_ACCURACY_UPDATE",
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
    print("prediction_accuracy更新結果")
    print('='*60)

    status_mark = '成功' if results['status'] == 'success' else '失敗'

    print(f"\n処理結果: {status_mark}")
    print(f"メッセージ: {results['message']}")
    print(f"削除レコード数: {results['deleted_rows']}")
    print(f"挿入レコード数: {results['inserted_rows']}")
    print('='*60)


def main():
    """メイン関数"""
    print("prediction_accuracy更新システム開始")

    # 更新処理実行
    updater = PredictionAccuracyUpdater()
    results = updater.update_prediction_accuracy()

    # 結果表示
    print_update_results(results)

    # 失敗時はexit code 1を返す
    if results['status'] == 'failed':
        import sys
        sys.exit(1)

    print("処理完了")


if __name__ == "__main__":
    main()
