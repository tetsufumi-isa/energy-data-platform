#!/bin/bash
# 日次ETL実行スクリプト
# cronから実行される

# 環境変数を直接設定（cronはnon-interactiveなのでbashrcが読み込まれない）
export ENERGY_ENV_PATH=/home/teisa/dev/energy-prediction-pipeline
export GOOGLE_APPLICATION_CREDENTIALS=/home/teisa/dev/energy-prediction-pipeline/key/energy-data-processor-key.json

# プロジェクトディレクトリに移動
cd "$ENERGY_ENV_PATH"

# 仮想環境を有効化
source venv/bin/activate

# ETLパイプライン実行（標準出力・標準エラー出力をログに記録）
python -m src.pipelines.main_etl >> "$ENERGY_ENV_PATH/logs/cron_etl.log" 2>&1
