#!/bin/bash

# Energy Environment セットアップスクリプト (Linux用)
# 使用方法: bash setup.sh

set -e  # エラー時に終了

echo "========================================="
echo "Energy Environment セットアップ開始"
echo "========================================="

# カレントディレクトリをENERGY_ENV_PATHとして取得
export ENERGY_ENV_PATH=$(pwd)
echo "プロジェクトパス: $ENERGY_ENV_PATH"

# Pythonバージョン確認
echo ""
echo "1. Pythonバージョン確認..."
if ! command -v python3 &> /dev/null; then
    echo "エラー: Python3がインストールされていません"
    exit 1
fi

PYTHON_VERSION=$(python3 --version)
echo "検出: $PYTHON_VERSION"

# Python 3.12推奨の確認
PYTHON_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)')
if [ "$PYTHON_MINOR" -lt 10 ]; then
    echo "警告: Python 3.10以上を推奨します（現在: 3.$PYTHON_MINOR）"
fi

# 仮想環境作成
echo ""
echo "2. 仮想環境作成..."
if [ -d "venv" ]; then
    echo "仮想環境は既に存在します (venv/)"
    read -p "再作成しますか? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf venv
        python3 -m venv venv
        echo "仮想環境を再作成しました"
    fi
else
    python3 -m venv venv
    echo "仮想環境を作成しました (venv/)"
fi

# 仮想環境アクティベート
echo ""
echo "3. 仮想環境アクティベート..."
source venv/bin/activate
echo "仮想環境がアクティブになりました"

# pipアップグレード
echo ""
echo "4. pipアップグレード..."
pip install --upgrade pip

# パッケージインストール
echo ""
echo "5. Pythonパッケージインストール..."
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
    echo "パッケージインストール完了"
else
    echo "エラー: requirements.txtが見つかりません"
    exit 1
fi

# .envファイル作成
echo ""
echo "6. 環境変数設定ファイル作成..."
if [ -f ".env" ]; then
    echo ".envファイルは既に存在します"
else
    if [ -f ".env.template" ]; then
        cp .env.template .env
        echo ".envファイルを作成しました"
        echo "警告: .envファイルを編集して、実際の値を設定してください"
    else
        echo "エラー: .env.templateが見つかりません"
        exit 1
    fi
fi

# 必要なディレクトリ作成
echo ""
echo "7. ディレクトリ構造作成..."
mkdir -p data/raw
mkdir -p data/weather
mkdir -p logs/tepco_api
mkdir -p logs/weather_api
mkdir -p logs/power_bq_loader
mkdir -p logs/weather_bq_loader
mkdir -p logs/prediction
mkdir -p credentials
mkdir -p output
echo "ディレクトリ構造を作成しました"

# .envファイルに ENERGY_ENV_PATH を自動設定
echo ""
echo "8. 環境変数自動設定..."
if grep -q "^ENERGY_ENV_PATH=/path/to/energy-env" .env; then
    sed -i "s|^ENERGY_ENV_PATH=/path/to/energy-env|ENERGY_ENV_PATH=$ENERGY_ENV_PATH|" .env
    echo "ENERGY_ENV_PATH を自動設定しました: $ENERGY_ENV_PATH"
else
    echo "ENERGY_ENV_PATH は既に設定されています"
fi

# セットアップ完了メッセージ
echo ""
echo "========================================="
echo "セットアップ完了！"
echo "========================================="
echo ""
echo "次のステップ:"
echo "1. .envファイルを編集して、GCP認証キーのパスを設定"
echo "   GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json"
echo ""
echo "2. GCPサービスアカウントキーをcredentials/ディレクトリに配置"
echo ""
echo "3. 仮想環境をアクティベート (新しいターミナルを開いた場合)"
echo "   source venv/bin/activate"
echo ""
echo "4. 環境変数を読み込み"
echo "   export \$(cat .env | grep -v '^#' | xargs)"
echo ""
echo "5. GCP接続テスト"
echo "   python -m src.data_processing.gcp_auth"
echo ""
echo "6. データダウンロードテスト"
echo "   python -m src.data_processing.data_downloader --days 1"
echo ""
echo "========================================="
