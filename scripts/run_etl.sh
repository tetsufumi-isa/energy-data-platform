#!/bin/bash
# 日次ETL実行スクリプト
# cronから実行される

# .bashrcから環境変数を読み込む
source ~/.bashrc

# プロジェクトディレクトリに移動（環境変数使用）
cd "$ENERGY_ENV_PATH"

# 仮想環境を有効化
source venv/bin/activate

# ETLパイプライン実行（標準出力・標準エラー出力をログに記録）
python -m src.pipelines.main_etl >> "$ENERGY_ENV_PATH/logs/cron_etl.log" 2>&1
