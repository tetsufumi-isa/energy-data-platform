# Energy Data Platform セットアップガイド

このドキュメントは、Docker + Airflow環境でのセットアップ手順を説明します。

## 前提条件

### システム要件
- **OS**: Linux（Ubuntu 20.04以降推奨）/ macOS / Windows（WSL2）
- **Docker**: 20.10以上
- **Docker Compose**: V2以上
- **Git**: インストール済み
- **インターネット接続**: Docker Hub・GCP APIへのアクセスが必要

### GCP要件
- **GCPプロジェクト**: 既存のプロジェクトが必要
- **BigQuery**: データセット `energy_data` が作成済み
- **サービスアカウント**: 以下の権限を持つサービスアカウントキー（JSON）
  - BigQuery データ編集者
  - BigQuery ジョブユーザー
  - Cloud Storage オブジェクト管理者

---

## セットアップ手順

### 1. リポジトリクローン

```bash
git clone https://github.com/yourusername/energy-data-platform.git
cd energy-data-platform
```

### 2. GCP認証キー配置

```bash
# keys/ディレクトリにサービスアカウントキーを配置
cp /path/to/service-account-key.json keys/

# パーミッション設定（重要）
chmod 600 keys/service-account-key.json
```

### 3. 環境変数設定

```bash
# .envファイルを作成
cp .env.template .env

# .envファイルを編集
nano .env
```

**編集内容:**
```bash
GCP_PROJECT_ID=your-project-id
GOOGLE_APPLICATION_CREDENTIALS=/app/keys/service-account-key.json
```

### 4. Dockerイメージのビルドと起動

```bash
# イメージビルド＆起動
docker compose up -d --build

# 起動確認
docker compose ps
```

**期待される出力:**
```
NAME                    STATUS
airflow-webserver       Up (healthy)
airflow-scheduler       Up (healthy)
postgres                Up (healthy)
```

### 5. Airflow UIアクセス

ブラウザで以下にアクセス：
- **URL**: http://localhost:8081
- **ユーザー名**: airflow
- **パスワード**: airflow

### 6. 動作確認

#### 6.1 DAG確認
Airflow UIで `energy_etl_pipeline` DAGが表示されることを確認。

#### 6.2 手動実行テスト
```bash
# データ収集テスト（過去1日分）
docker compose run --rm energy-pipeline python -m src.pipelines.main_etl --days 1
```

**期待される出力:**
```
電力データダウンロード開始
...
処理完了
```

---

## 日次処理について

### Airflowによる自動実行

DAGスケジュール設定：
- **DAG名**: energy_etl_pipeline
- **実行時刻**: 毎日 07:00 JST
- **タスク**: データ収集 → BigQuery投入 → dbt変換 → 予測実行

### 手動実行

```bash
# Airflow UIから手動トリガー
# または、Docker内で直接実行
docker compose run --rm energy-pipeline python -m src.pipelines.main_etl --days 7
```

---

## トラブルシューティング

### 1. コンテナが起動しない

**症状:**
```
Container airflow-scheduler is not healthy
```

**対処法:**
```bash
# ログ確認
docker compose logs airflow-scheduler

# 再起動
docker compose down && docker compose up -d
```

### 2. GCP認証エラー

**症状:**
```
google.auth.exceptions.DefaultCredentialsError
```

**対処法:**
```bash
# キーファイルが正しく配置されているか確認
ls -la keys/

# .envの設定確認
cat .env | grep GOOGLE
```

### 3. BigQueryテーブルが見つからない

**症状:**
```
google.api_core.exceptions.NotFound: 404 Table not found
```

**対処法:**
```bash
# sql/ディレクトリ内のSQLでテーブル作成
# BigQueryコンソールで実行
```

### 4. Airflow UIにアクセスできない

**確認項目:**
```bash
# ポート確認
docker compose ps

# webserverログ確認
docker compose logs airflow-webserver
```

---

## ディレクトリ構造

```
energy-data-platform/
├── .env                      # 環境変数（Gitで除外）
├── .env.template             # 環境変数テンプレート
├── docker-compose.yml        # Docker Compose設定
├── Dockerfile                # パイプライン用イメージ
├── requirements.txt          # Pythonパッケージリスト
├── SETUP.md                  # このファイル
│
├── keys/                     # GCP認証キー（Gitで除外）
│   └── service-account-key.json
│
├── dags/                     # Airflow DAG定義
│   └── energy_etl_dag.py
│
├── dbt_energy/               # dbtプロジェクト
│   ├── models/
│   ├── dbt_project.yml
│   └── profiles.yml
│
├── src/                      # ソースコード
│   ├── data_processing/
│   ├── prediction/
│   ├── pipelines/
│   └── utils/
│
├── sql/                      # BigQueryテーブル定義SQL
│
├── logs/                     # ログファイル（Gitで除外）
│
└── output/                   # 出力ファイル（Gitで除外）
```

---

## セキュリティ注意事項

1. **認証キーの管理**
   - サービスアカウントキーは絶対にGitにコミットしない
   - `.gitignore`で`keys/`ディレクトリを除外済み
   - ファイルパーミッションは`600`に設定

2. **環境変数の管理**
   - `.env`ファイルはGitで除外
   - `.env.template`のみバージョン管理

3. **Airflow認証**
   - 本番環境ではデフォルトパスワードを変更すること

---

## コマンドリファレンス

```bash
# 起動
docker compose up -d

# 停止
docker compose down

# ログ確認
docker compose logs -f

# 特定サービスのログ
docker compose logs -f airflow-scheduler

# コンテナ内でコマンド実行
docker compose run --rm energy-pipeline python -m src.pipelines.main_etl --days 7

# イメージ再ビルド
docker compose build --no-cache

# 全リソース削除（データ含む）
docker compose down -v
```

---

## チェックリスト

セットアップ完了前に以下を確認：

- [ ] Docker / Docker Composeインストール完了
- [ ] リポジトリクローン完了
- [ ] GCP認証キー配置完了（パーミッション600）
- [ ] `.env`ファイル作成・編集完了
- [ ] `docker compose up -d`で全コンテナ起動
- [ ] Airflow UI（http://localhost:8081）にアクセス可能
- [ ] DAG `energy_etl_pipeline`が表示される
- [ ] 手動実行テスト成功

---

**最終更新**: 2026-01-24
**対象環境**: Docker + Airflow