"""
dbt実行ラッパーモジュール

dbtコマンドを実行し、process_execution_logにログを記録する。
Airflow DAGからはこのモジュールを呼び出すことで、
dbt実行結果をBigQueryのログテーブルに記録できる。

実行方法:
    python -m src.data_processing.dbt_runner --model ml_features
    python -m src.data_processing.dbt_runner --model dashboard_data
"""

import argparse
import json
import os
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from google.cloud import bigquery


class DbtRunner:
    """dbt実行ラッパークラス"""

    # サポートするモデル名とprocess_typeのマッピング
    MODEL_PROCESS_TYPES = {
        'ml_features': 'DBT_ML_FEATURES',
        'dashboard_data': 'DBT_DASHBOARD_DATA',
    }

    def __init__(self, project_id="energy-env"):
        """
        初期化

        Args:
            project_id (str): GCPプロジェクトID
        """
        self.project_id = project_id
        self.dataset_id = "prod_energy_data"

        # 環境変数チェック
        energy_env_path = os.getenv('ENERGY_ENV_PATH')
        if energy_env_path is None:
            raise ValueError("ENERGY_ENV_PATH環境変数が設定されていません")
        self.energy_env_path = Path(energy_env_path)

        # dbtプロジェクトディレクトリ
        self.dbt_project_dir = self.energy_env_path / 'dbt_energy'

        # ログディレクトリ設定
        self.log_dir = self.energy_env_path / 'logs' / 'dbt_runner'
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # BigQueryクライアント初期化
        self.bq_client = bigquery.Client(project=project_id)

        # BQログテーブル設定
        self.bq_log_table_id = f"{self.project_id}.{self.dataset_id}.process_execution_log"

        print(f"DbtRunner初期化完了: project_id={project_id}")

    def run_model(self, model_name: str) -> dict:
        """
        指定されたdbtモデルを実行

        Args:
            model_name (str): 実行するモデル名（ml_features, dashboard_data）

        Returns:
            dict: 実行結果
        """
        # モデル名検証
        if model_name not in self.MODEL_PROCESS_TYPES:
            raise ValueError(
                f"未対応のモデル: {model_name}。"
                f"対応モデル: {list(self.MODEL_PROCESS_TYPES.keys())}"
            )

        process_type = self.MODEL_PROCESS_TYPES[model_name]

        # 実行ID・開始時刻記録
        execution_id = str(uuid.uuid4())
        started_at = datetime.now(ZoneInfo('Asia/Tokyo'))
        target_date_str = started_at.strftime('%Y-%m-%d')

        print(f"dbt run開始: model={model_name}, execution_id={execution_id}")

        try:
            # dbtコマンド実行
            result = self._execute_dbt(model_name)

            if result['success']:
                print(f"dbt run成功: model={model_name}")

                # 成功ログ記録
                completed_at = datetime.now(ZoneInfo('Asia/Tokyo'))
                duration_seconds = (completed_at - started_at).total_seconds()

                log_data = {
                    "execution_id": execution_id,
                    "date": target_date_str,
                    "process_type": process_type,
                    "status": "SUCCESS",
                    "error_message": None,
                    "started_at": started_at.replace(tzinfo=None).isoformat(),
                    "completed_at": completed_at.replace(tzinfo=None).isoformat(),
                    "duration_seconds": duration_seconds,
                    "records_processed": None,
                    "file_size_mb": None,
                    "additional_info": json.dumps({
                        "model": model_name,
                        "dbt_output": result['output'][:1000] if result['output'] else None
                    })
                }
                self._write_log(log_data)

                return {
                    'status': 'success',
                    'message': f'dbt run {model_name} 成功',
                    'model': model_name,
                    'duration_seconds': duration_seconds
                }

            else:
                raise Exception(result['error'])

        except Exception as e:
            print(f"dbt run失敗: model={model_name}, error={e}")

            # 失敗ログ記録
            completed_at = datetime.now(ZoneInfo('Asia/Tokyo'))
            duration_seconds = (completed_at - started_at).total_seconds()

            log_data = {
                "execution_id": execution_id,
                "date": target_date_str,
                "process_type": process_type,
                "status": "FAILED",
                "error_message": str(e)[:1000],
                "started_at": started_at.replace(tzinfo=None).isoformat(),
                "completed_at": completed_at.replace(tzinfo=None).isoformat(),
                "duration_seconds": duration_seconds,
                "records_processed": None,
                "file_size_mb": None,
                "additional_info": json.dumps({"model": model_name})
            }
            self._write_log(log_data)

            return {
                'status': 'failed',
                'message': f'dbt run {model_name} 失敗: {str(e)}',
                'model': model_name,
                'duration_seconds': duration_seconds
            }

    def _execute_dbt(self, model_name: str) -> dict:
        """
        dbtコマンドをsubprocessで実行

        Args:
            model_name (str): モデル名

        Returns:
            dict: {'success': bool, 'output': str, 'error': str}
        """
        cmd = [
            'dbt', 'run',
            '--select', model_name,
            '--project-dir', str(self.dbt_project_dir),
            '--profiles-dir', str(self.dbt_project_dir),
        ]

        print(f"実行コマンド: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5分タイムアウト
                cwd=str(self.dbt_project_dir),
            )

            output = result.stdout + result.stderr

            if result.returncode == 0:
                return {
                    'success': True,
                    'output': output,
                    'error': None
                }
            else:
                return {
                    'success': False,
                    'output': output,
                    'error': f"dbt run失敗 (return code: {result.returncode}): {output}"
                }

        except subprocess.TimeoutExpired:
            return {
                'success': False,
                'output': None,
                'error': "dbt runがタイムアウトしました（5分）"
            }
        except Exception as e:
            return {
                'success': False,
                'output': None,
                'error': f"dbt実行エラー: {str(e)}"
            }

    def _write_log(self, log_data: dict):
        """
        ログをローカルファイルとBigQueryに記録

        Args:
            log_data (dict): ログデータ
        """
        # ローカルファイルに記録
        log_date = datetime.now(ZoneInfo('Asia/Tokyo')).strftime('%Y-%m-%d')
        log_file = self.log_dir / f"{log_date}_dbt_execution.jsonl"

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


def print_results(results: dict):
    """実行結果を表示"""
    print(f"\n{'='*60}")
    print("dbt実行結果")
    print('='*60)

    status_mark = '成功' if results['status'] == 'success' else '失敗'

    print(f"\n処理結果: {status_mark}")
    print(f"モデル: {results['model']}")
    print(f"メッセージ: {results['message']}")
    print(f"実行時間: {results['duration_seconds']:.2f}秒")
    print('='*60)


def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(description='dbt実行ラッパー')
    parser.add_argument(
        '--model',
        required=True,
        choices=['ml_features', 'dashboard_data'],
        help='実行するdbtモデル名'
    )

    args = parser.parse_args()

    print(f"dbt実行システム開始: model={args.model}")

    # dbt実行
    runner = DbtRunner()
    results = runner.run_model(args.model)

    # 結果表示
    print_results(results)

    # 失敗時はexit code 1を返す
    if results['status'] == 'failed':
        import sys
        sys.exit(1)

    print("処理完了")


if __name__ == "__main__":
    main()