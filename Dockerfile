# ベースイメージ（Python 3.12の軽量版）
FROM python:3.12-slim

# メタデータ
LABEL maintainer="energy-prediction-pipeline"
LABEL description="Energy prediction pipeline with XGBoost and GCP integration"

# 作業ディレクトリ設定
WORKDIR /app

# システムパッケージの更新と必要な依存関係インストール
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# タイムゾーン設定
RUN ln -sf /usr/share/zoneinfo/Asia/Tokyo /etc/localtime && \
    echo "Asia/Tokyo" > /etc/timezone

# Pythonパッケージの依存関係をコピー
COPY requirements.txt .

# Pythonパッケージのインストール
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir dbt-bigquery

# ソースコードをコピー
COPY src/ ./src/
COPY sql/ ./sql/
COPY dbt_energy/ ./dbt_energy/

# 環境変数設定
ENV ENERGY_ENV_PATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV TZ=Asia/Tokyo

# ログディレクトリ作成
RUN mkdir -p /app/logs /app/data/raw /app/data/weather

# デフォルトコマンド（ETLパイプライン実行）
CMD ["python", "-m", "src.pipelines.main_etl"]
