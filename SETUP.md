# Energy Environment セットアップガイド

このドキュメントは、Linuxサーバー環境でのセットアップ手順を説明します。

## 📋 前提条件

### システム要件
- **OS**: Linux（Ubuntu 20.04以降推奨）
- **Python**: 3.10以上（3.12推奨）
- **Git**: インストール済み
- **インターネット接続**: PyPI・GCP APIへのアクセスが必要

### GCP要件
- **GCPプロジェクト**: 既存のプロジェクトが必要
- **BigQuery**: データセット `prod_energy_data` が作成済み
- **サービスアカウント**: 以下の権限を持つサービスアカウントキー（JSON）
  - BigQuery データ編集者
  - BigQuery ジョブユーザー
  - Cloud Storage オブジェクト管理者

---

## 🚀 セットアップ手順

### 1. リポジトリクローン

```bash
# ホームディレクトリに移動
cd ~

# リポジトリクローン
git clone <repository-url> energy-env
cd energy-env
```

### 2. 自動セットアップスクリプト実行

```bash
# setup.shに実行権限付与
chmod +x setup.sh

# セットアップスクリプト実行
bash setup.sh
```

**スクリプトの処理内容:**
1. Pythonバージョン確認
2. 仮想環境作成 (`venv/`)
3. 仮想環境アクティベート
4. pipアップグレード
5. requirements.txtからパッケージインストール
6. `.env`ファイル作成（`.env.template`からコピー）
7. 必要なディレクトリ構造作成
8. `ENERGY_ENV_PATH`の自動設定

### 3. GCP認証キー配置

```bash
# credentialsディレクトリにサービスアカウントキーを配置
# 例: scp経由でアップロード
scp /path/to/local/service-account-key.json username@server:~/energy-env/credentials/

# パーミッション設定（重要）
chmod 600 ~/energy-env/credentials/service-account-key.json
```

### 4. 環境変数設定

`.env`ファイルを編集して、GCP認証キーのパスを設定：

```bash
nano .env
```

**編集内容:**
```bash
# プロジェクトルートパス（setup.shで自動設定済み）
ENERGY_ENV_PATH=/home/username/energy-env

# GCP認証キーファイルのパス（要編集）
GOOGLE_APPLICATION_CREDENTIALS=/home/username/energy-env/credentials/service-account-key.json
```

保存して終了（Ctrl+X → Y → Enter）

### 5. 環境変数読み込み

```bash
# 環境変数を現在のシェルに読み込み
export $(cat .env | grep -v '^#' | xargs)

# 確認
echo $ENERGY_ENV_PATH
echo $GOOGLE_APPLICATION_CREDENTIALS
```

### 6. 動作確認

#### 6.1 仮想環境アクティベート確認

```bash
# 仮想環境アクティベート
source venv/bin/activate

# Pythonバージョン確認
python --version  # Python 3.10以上であることを確認

# インストール済みパッケージ確認
pip list | grep google-cloud
```

#### 6.2 GCP接続テスト

```bash
# BigQuery・GCS接続確認
python -m src.data_processing.gcp_auth
```

**期待される出力:**
```
認証キーのパス: /home/username/energy-env/credentials/service-account-key.json
GCS接続成功: X個のバケットが見つかりました
 - bucket-name-1
 - bucket-name-2
BigQuery接続成功: X個のデータセットが見つかりました
 - prod_energy_data
すべての接続テストに成功しました！
```

#### 6.3 データダウンロードテスト

```bash
# 過去1日分のデータダウンロードテスト
python -m src.data_processing.data_downloader --days 1
```

**期待される出力:**
```
PowerDataDownloader 初期化完了 保存先: /home/username/energy-env/data/raw
東京電力でんき予報データダウンロード開始
日数指定モード: 過去1日分
...
成功: YYYYMM
ダウンロード完了
```

---

## 🔄 日次処理の設定（cron）

### cron設定例

```bash
# crontab編集
crontab -e
```

**設定内容:**
```bash
# 環境変数の設定
ENERGY_ENV_PATH=/home/username/energy-env
GOOGLE_APPLICATION_CREDENTIALS=/home/username/energy-env/credentials/service-account-key.json

# 毎日午前3時に電力データダウンロード・BQ投入
0 3 * * * cd $ENERGY_ENV_PATH && source venv/bin/activate && python -m src.pipelines.main_etl --days 7 >> logs/cron_etl.log 2>&1

# 毎日午前4時に天気データダウンロード（必要に応じて）
0 4 * * * cd $ENERGY_ENV_PATH && source venv/bin/activate && python -m src.data_processing.weather_downloader --days 7 >> logs/cron_weather.log 2>&1
```

### cronログ確認

```bash
# ETLログ確認
tail -f ~/energy-env/logs/cron_etl.log

# 天気データログ確認
tail -f ~/energy-env/logs/cron_weather.log
```

---

## 🔧 トラブルシューティング

### 1. Python仮想環境が見つからない

**症状:**
```
bash: venv/bin/activate: No such file or directory
```

**対処法:**
```bash
# 仮想環境再作成
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. GCP認証エラー

**症状:**
```
google.auth.exceptions.DefaultCredentialsError
```

**対処法:**
```bash
# 環境変数が設定されているか確認
echo $GOOGLE_APPLICATION_CREDENTIALS

# 認証キーファイルが存在するか確認
ls -la $GOOGLE_APPLICATION_CREDENTIALS

# パーミッション確認
chmod 600 $GOOGLE_APPLICATION_CREDENTIALS
```

### 3. BigQueryテーブルが見つからない

**症状:**
```
google.api_core.exceptions.NotFound: 404 Table not found
```

**対処法:**
```bash
# BigQueryコンソールで以下を確認
# - プロジェクトID: energy-env
# - データセット: prod_energy_data
# - テーブル: energy_data_hourly, weather_data_hourly など

# テーブルスキーマ作成スクリプトを実行（必要に応じて）
```

### 4. パッケージインストールエラー

**症状:**
```
ERROR: Could not find a version that satisfies the requirement
```

**対処法:**
```bash
# pipアップグレード
pip install --upgrade pip

# 個別インストール
pip install google-cloud-bigquery google-cloud-storage pandas xgboost
```

### 5. cronジョブが実行されない

**確認項目:**
```bash
# cronサービス稼働確認
systemctl status cron

# crontab確認
crontab -l

# ログ確認
grep CRON /var/log/syslog
```

---

## 📂 ディレクトリ構造

セットアップ完了後のディレクトリ構成：

```
energy-env/
├── .env                      # 環境変数（Gitで除外）
├── .env.template             # 環境変数テンプレート
├── .gitignore                # Git除外設定
├── requirements.txt          # Pythonパッケージリスト
├── setup.sh                  # セットアップスクリプト
├── SETUP.md                  # このファイル
├── CLAUDE.md                 # Claude Code向けプロジェクト説明
│
├── venv/                     # Python仮想環境（Gitで除外）
│
├── credentials/              # GCP認証キー（Gitで除外）
│   └── service-account-key.json
│
├── src/                      # ソースコード
│   ├── data_processing/
│   ├── prediction/
│   ├── pipelines/
│   └── utils/
│
├── data/                     # データファイル（Gitで除外）
│   ├── raw/
│   └── weather/
│
├── logs/                     # ログファイル（Gitで除外）
│   ├── tepco_api/
│   ├── weather_api/
│   ├── power_bq_loader/
│   ├── weather_bq_loader/
│   └── prediction/
│
├── output/                   # 出力ファイル（Gitで除外）
│
└── learning_memos/           # 学習メモ・進捗記録
```

---

## 🔐 セキュリティ注意事項

1. **認証キーの管理**
   - サービスアカウントキーは絶対にGitにコミットしない
   - `.gitignore`で`credentials/`ディレクトリを除外済み
   - ファイルパーミッションは`600`に設定

2. **環境変数の管理**
   - `.env`ファイルはGitで除外
   - `.env.template`のみバージョン管理

3. **サーバーアクセス**
   - SSH鍵認証を使用
   - 不要なポートは閉じる

---

## 📝 追加設定（オプション）

### シェル起動時に環境変数を自動読み込み

`.bashrc`または`.zshrc`に追加：

```bash
# Energy Environment
if [ -f "$HOME/energy-env/.env" ]; then
    export $(cat $HOME/energy-env/.env | grep -v '^#' | xargs)
fi
```

### エイリアス設定

```bash
# .bashrcまたは.zshrcに追加
alias energy-activate='cd ~/energy-env && source venv/bin/activate'
alias energy-logs='tail -f ~/energy-env/logs/cron_etl.log'
```

---

## 🆘 サポート

問題が解決しない場合は、以下を確認：

1. **ログファイル確認**: `logs/`ディレクトリ内の各種ログ
2. **BigQueryログ確認**: `prod_energy_data.process_execution_log`テーブル
3. **環境変数確認**: `env | grep ENERGY`

---

## ✅ チェックリスト

セットアップ完了前に以下を確認：

- [ ] Pythonバージョン確認（3.10以上）
- [ ] 仮想環境作成・アクティベート
- [ ] パッケージインストール完了
- [ ] `.env`ファイル作成・編集完了
- [ ] GCP認証キー配置完了（パーミッション600）
- [ ] 環境変数読み込み完了
- [ ] GCP接続テスト成功
- [ ] データダウンロードテスト成功
- [ ] cron設定完了（日次処理用）
- [ ] ログファイル確認

---

**最終更新**: 2025-10-11
**対象環境**: Linux (Ubuntu 20.04+)
**Python**: 3.12推奨
