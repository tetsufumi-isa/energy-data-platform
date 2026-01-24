"""
Energy ETL DAG - 電力使用量予測パイプライン

毎朝7:00（JST）に実行される日次ETLパイプライン
各タスクは独立したDockerコンテナで実行・リトライ可能

処理フロー:
1. データ取得（電力・気象）
2. BigQuery投入
3. 特徴量更新・品質チェック
4. 予測実行
5. 結果更新・ダッシュボード反映
"""

import os
from datetime import datetime, timedelta
from airflow import DAG
from airflow.providers.docker.operators.docker import DockerOperator
from docker.types import Mount

# プロジェクトのベースパス（環境変数から取得）
BASE_PATH = os.environ.get('ENERGY_ENV_PATH')
if not BASE_PATH:
    raise ValueError('環境変数 ENERGY_ENV_PATH が設定されていません')

# DAGのデフォルト引数
default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
}

# Docker共通設定
docker_common = {
    'image': 'energy-pipeline:latest',
    'api_version': 'auto',
    'auto_remove': True,  # タスク完了後にコンテナを自動削除
    'docker_url': 'unix://var/run/docker.sock',
    'network_mode': 'bridge',
    'mount_tmp_dir': False,  # Airflowの/tmpマウントを無効化（パス問題回避）
    'mounts': [
        Mount(source=f'{BASE_PATH}/logs', target='/app/logs', type='bind'),
        Mount(source=f'{BASE_PATH}/keys', target='/app/keys', type='bind'),
        Mount(source=f'{BASE_PATH}/data', target='/app/data', type='bind'),
    ],
    'environment': {
        'GOOGLE_APPLICATION_CREDENTIALS': '/app/keys/energy-data-processor-key.json',
        'TZ': 'Asia/Tokyo',
    },
}

# DAG定義
with DAG(
    dag_id='energy_etl_pipeline',
    default_args=default_args,
    description='電力使用量予測パイプライン - 日次ETL処理',
    schedule_interval='0 7 * * *',  # 毎朝7:00（JST）
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=['energy', 'etl', 'prediction'],
) as dag:

    # Phase 1: 電力データダウンロード
    download_power_data = DockerOperator(
        task_id='download_power_data',
        command='python -m src.data_processing.data_downloader --days 5',
        **docker_common,
    )

    # Phase 2: 気象データダウンロード
    download_weather_data = DockerOperator(
        task_id='download_weather_data',
        command='python -m src.data_processing.weather_downloader',
        **docker_common,
    )

    # Phase 3: 電力データBigQuery投入
    load_power_to_bq = DockerOperator(
        task_id='load_power_to_bq',
        command='python -m src.data_processing.power_bigquery_loader --days 5',
        **docker_common,
    )

    # Phase 4-1: 気象データBigQuery投入（過去データ）
    load_weather_historical_to_bq = DockerOperator(
        task_id='load_weather_historical_to_bq',
        command='python -m src.data_processing.weather_bigquery_loader --data-type historical',
        **docker_common,
    )

    # Phase 4-2: 気象データBigQuery投入（予測データ）
    load_weather_forecast_to_bq = DockerOperator(
        task_id='load_weather_forecast_to_bq',
        command='python -m src.data_processing.weather_bigquery_loader --data-type forecast',
        **docker_common,
    )

    # Phase 5: ml_features更新（dbt経由・ログ記録あり）
    update_ml_features = DockerOperator(
        task_id='update_ml_features',
        command='python -m src.data_processing.dbt_runner --model ml_features',
        **docker_common,
    )

    # Phase 6: データ品質チェック
    check_data_quality = DockerOperator(
        task_id='check_data_quality',
        command='python -m src.monitoring.data_quality_checker --days 7',
        **docker_common,
    )

    # Phase 7: 予測実行
    run_prediction = DockerOperator(
        task_id='run_prediction',
        command='python -m src.prediction.prediction_iterative_with_export',
        **docker_common,
    )

    # Phase 8: prediction_accuracy更新
    update_prediction_accuracy = DockerOperator(
        task_id='update_prediction_accuracy',
        command='python -m src.data_processing.prediction_accuracy_updater',
        **docker_common,
    )

    # Phase 9: ダッシュボードデータ更新（dbt経由・ログ記録あり）
    update_dashboard_data = DockerOperator(
        task_id='update_dashboard_data',
        command='python -m src.data_processing.dbt_runner --model dashboard_data',
        **docker_common,
    )

    # Phase 10: システム監視ステータス更新
    update_system_status = DockerOperator(
        task_id='update_system_status',
        command='python -m src.data_processing.system_status_updater',
        **docker_common,
    )

    # タスク依存関係の定義
    # 電力データ: ダウンロード -> BQ投入
    download_power_data >> load_power_to_bq

    # 気象データ: ダウンロード -> BQ投入（historical -> forecast の順で直列実行）
    # 同じテーブルへのINSERT/DELETEでstreaming buffer問題を回避
    download_weather_data >> load_weather_historical_to_bq >> load_weather_forecast_to_bq

    # ml_features更新: 電力・気象データがBQに入った後
    [load_power_to_bq, load_weather_forecast_to_bq] >> update_ml_features

    # データ品質チェック: ml_features更新後
    update_ml_features >> check_data_quality

    # 予測実行: 品質チェック後
    check_data_quality >> run_prediction

    # 結果更新フェーズ: 予測実行後（並列実行可能）
    run_prediction >> [update_prediction_accuracy, update_dashboard_data, update_system_status]