# Phase 11 main_etl統合・設計方針決定

## セッション概要
**日付**: 2025年10月8日
**作業内容**: main_etl.pyへの天気データ統合実装、設計方針の根本的な議論と決定
**成果**: 天気データ統合完了、パイプライン設計方針の明確化、次ステップの優先順位決定

## 今回の主要成果

### 1. main_etl.pyへの天気データ統合実装

#### 統合したコンポーネント
```python
# 追加import
from src.data_processing.weather_downloader import WeatherDownloader
from src.data_processing.weather_bigquery_loader import WeatherBigQueryLoader
from src.data_processing.power_bigquery_loader import PowerBigQueryLoader

# 初期化時に全コンポーネント生成
self.power_downloader = PowerDataDownloader(...)
self.weather_downloader = WeatherDownloader()
self.power_bq_loader = PowerBigQueryLoader(...)
self.weather_bq_loader = WeatherBigQueryLoader(...)
```

#### 実装したフロー（run_etl_for_days）
```
Phase 1: データダウンロード
  ├─ 1-1. 電力データダウンロード（過去5日分）
  └─ 1-2. 気象データダウンロード（過去10日+予測16日）

Phase 2: GCSアップロード
  └─ 電力データのみアップロード

Phase 3: BigQuery投入
  ├─ 3-1. 電力データBQ投入
  └─ 3-2. 気象データBQ投入（historical + forecast）
```

#### エラーハンドリング
- 各フェーズで個別にtry/except
- 電力DL失敗 → GCSスキップ
- 天気DL失敗 → 天気BQスキップ
- 各コンポーネントは独自のログ・BQログを記録

### 2. argparse削除・不要メソッド削除

#### 削除した機能
- ✅ argparse関連コード全削除
- ✅ `run_etl_for_month`メソッド削除（天気データ未対応、動作しない）
- ✅ `run_etl_for_date`メソッド削除（天気データ未対応、動作しない）
- ✅ `_create_summary`メソッド削除（古い電力のみ版）
- ✅ 不要なimport削除（argparse, calendar, datetime, timedelta）

#### main関数のシンプル化
```python
def main():
    setup_logging()
    pipeline = MainETLPipeline()  # 引数なし、固定パラメータ
    results = pipeline.run_etl_for_days(days=5)
    print_results(results)
```

### 3. 統合版結果表示の実装

#### print_results関数の拡張
```python
# 電力データダウンロード結果
# 気象データダウンロード結果
# GCSアップロード結果（電力データ）
# BigQuery投入結果（電力データ）
# BigQuery投入結果（気象データ - historical/forecast別）
# 総合結果サマリー
```

## 設計方針の根本的な議論と決定

### 問題提起: なぜコードがこんなに長いのか

**議論の発端**:
各モジュールは独立して動く設計なのに、なぜmain_etl.pyが複雑なのか？

### 調査結果

#### 各モジュールの性質
| モジュール | 種類 | CLI対応 | 直接実行 |
|-----------|------|---------|---------|
| data_downloader | CLIツール | ✅ | 可能 |
| weather_downloader | CLIツール | ✅ | 可能 |
| power_bigquery_loader | CLIツール | ✅ | 可能 |
| weather_bigquery_loader | CLIツール | ✅ | 可能 |
| **gcs_uploader** | **ライブラリ** | ❌ | **不可** |

#### test_main_etl.pyの状態
- MainETLPipelineをimportしている
- しかし**既に壊れている**（天気データ統合前の仕様のまま）
- `pipeline.downloader` → 現在は`pipeline.power_downloader`
- `run_etl_for_month/date` → 削除済み
- 期待する戻り値と実際の戻り値が不一致

### パイプライン設計の2つのアプローチ

#### パターンA: CLIツールを順次叩く（Unix哲学）
```bash
python -m src.data_processing.data_downloader --days 5
python -m src.data_processing.gcs_uploader --source data/raw
python -m src.data_processing.power_bigquery_loader --days 5
```

**メリット**:
- 各ツール完全独立（疎結合）
- デバッグ容易（個別実行可能）
- Airflow/シェルスクリプトで簡単にパイプライン構築
- Unix哲学: Do One Thing Well

#### パターンB: ライブラリとしてimport（現在の実装）
```python
from src.data_processing.data_downloader import PowerDataDownloader
downloader = PowerDataDownloader()
results = downloader.download_for_days(5)
```

**メリット**:
- プロセス起動オーバーヘッドなし
- Pythonでリッチなエラーハンドリング
- 中間データをメモリで受け渡し

### 決定事項

#### 採用方針: **パターンB（import）を維持**

**理由**:
1. TODO 14「Airflow環境構築」があるため、将来パターンAに移行可能
2. 現時点ではシンプルさ優先
3. 各モジュールは既にCLI対応済み → Airflow移行時に切り替え容易

#### main_etl.pyの役割定義

**main_etl.pyは日次実行専用**:
- 引数なし、固定パラメータ（電力5日分 + 天気10日+予測16日）
- オーケストレーション（正しい順序、エラー時のスキップ判断）
- 統合ログ・サマリー

**柔軟な実行（月指定、日指定、カスタムパラメータ）は各モジュールを直接叩く**:
```bash
# アドホック作業例: 7月だけやり直し
python -m src.data_processing.data_downloader --month 202507
python -m src.data_processing.gcs_uploader --upload-dir data/raw/202507
python -m src.data_processing.power_bigquery_loader --days 30
```

### なぜ柔軟性をmain_etl.pyに持たせないのか

**理由**:
1. **頻度とコストの不釣り合い** - アドホック作業は年数回、複雑なコード維持コストが高い
2. **ユースケースが根本的に違う** - 日次実行とアドホック修正は別物
3. **責務分離** - main_etl.py（日次専用）と各モジュール（柔軟性提供）で明確に分離
4. **実務でもそう** - Airflowの日次DAGは固定、データ修正は個別タスク実行

## ログ設計の確認

### setup_logging()の動作
```python
# src/utils/logging_config.py
app_logger = getLogger('energy_env')  # トップレベルロガー
console_handler = StreamHandler(sys.stdout)  # 標準出力のみ
app_logger.addHandler(console_handler)
```

**出力先**: **標準出力（コンソール）のみ**、ファイル出力なし

### ログテーブルでの追跡

各コンポーネントがBQログテーブル（`process_execution_log`）に記録：
- WeatherDownloader → `WEATHER_API`
- PowerBigQueryLoader → `POWER_BQ_LOAD`
- WeatherBigQueryLoader → `WEATHER_BQ_LOAD`

時系列で並べれば、どのフェーズまで成功/失敗したかが追跡可能。

**main_etl.pyはファイルログ不要** - コンソール出力 + BQログテーブルで十分。

## 技術的理解の向上

### なぜmain_etl.pyが元々複雑だったか

**元の設計意図（天気データ統合前）**:
- 電力データの「ダウンロード→GCSアップロード」を1コマンド実行
- 柔軟性も提供（--month, --date対応）
- 統合エントリポイント思想

**問題**: 天気データ統合で矛盾発生
- 天気データは月/日指定機能なし
- run_etl_for_month/dateに天気データを統合できない
- argparseがあるのに天気データは使えない（中途半端）

### GCSUploaderがライブラリのみな理由

**GCSUploaderには`if __name__ == "__main__"`なし**:
- ライブラリクラスとして設計
- main_etl.pyで制御ロジック（どのファイルをどのパスに）を書く

**元の設計**:
「各CLIツールを順次叩く」のではなく「各クラスライブラリをimportして組み合わせる統合スクリプト」

## 次回セッションで実装すること（重要）

### **優先順位の変更** - 実装順序を逆転

**誤った順序（今回やってしまった）**:
1. main_etl.pyシンプル化
2. WeatherDownloader改修
3. gcs_uploader改修

**正しい順序**:
1. ✅ **WeatherDownloader改修** ← 最優先
2. ✅ **gcs_uploader改修** ← 次
3. → **main_etl.py根本的作り直し** ← 最後

**理由**:
- main_etl.pyをシンプル化 = 「柔軟性は各モジュールで」という前提
- でも今は各モジュールに柔軟性がない
- 前提機能がないのにmain_etl.pyだけ直しても意味がない

### 1. WeatherDownloaderに月/日指定機能追加（最優先）

**現状の問題**:
```python
# download_daily_weather_data(target_date=None)
target_date=None: 過去10日+予測16日（日次自動実行用）
target_date指定: 指定日から30日前まで
```
→ **月単位取得機能がない**

**必要な機能**:
```python
# 目標: 柔軟な過去データ取得
download_historical_data(start_date, end_date)  # 期間指定
download_for_month(yyyymm)  # 月指定（1日～月末）
```

**実装方針**:
- Historical APIを使った期間指定取得
- main関数にargparse追加（--start-date, --end-date, --month）
- 既存のdownload_daily_weather_dataは維持（後方互換性）

**ファイル名規則**:
```
chiba_2025_07_historical_range.json  # 期間指定
chiba_2025_07_historical_month.json  # 月指定
```

### 2. gcs_uploaderにCLI対応追加

**現状の問題**:
- ライブラリクラスのみ、CLI未対応
- 直接実行できない

**必要な機能**:
```bash
# ファイル単体アップロード
python -m src.data_processing.gcs_uploader \
  --file data/raw/202507/20250701_power_usage.csv \
  --destination raw_data/202507/20250701_power_usage.csv

# ディレクトリアップロード
python -m src.data_processing.gcs_uploader \
  --upload-dir data/raw/202507 \
  --prefix raw_data/202507
```

**実装方針**:
```python
def main():
    parser = argparse.ArgumentParser(description='GCSアップローダー')
    parser.add_argument('--file', help='アップロードするファイル')
    parser.add_argument('--destination', help='GCS上の保存先パス')
    parser.add_argument('--upload-dir', help='アップロードするディレクトリ')
    parser.add_argument('--prefix', help='GCS上のプレフィックス')
    parser.add_argument('--bucket', default='energy-env-data', help='GCSバケット名')

    args = parser.parse_args()

    uploader = GCSUploader(args.bucket)

    if args.file:
        uploader.upload_file(args.file, args.destination)
    elif args.upload_dir:
        uploader.upload_directory(args.upload_dir, args.prefix)

if __name__ == "__main__":
    main()
```

### 3. main_etl.py根本的作り直し（最後）

**現状のコード**（約370行）:
- MainETLPipelineクラス（約240行）
- run_etl_for_days（約100行）
- _upload_downloaded_data（約50行）
- _create_summary_integrated（約50行）
- print_results（約60行）

**目標のコード**（約100行以下）:
```python
def main():
    """日次ETLパイプライン - シンプル版"""
    setup_logging()

    print("🚀 日次ETLパイプライン開始")

    # 1. 電力データダウンロード
    power_downloader = PowerDataDownloader(...)
    power_results = power_downloader.download_for_days(5)

    # 2. 気象データダウンロード
    weather_downloader = WeatherDownloader()
    weather_results = weather_downloader.download_daily_weather_data()

    # 3. GCSアップロード（電力データ）
    if power_results['success']:
        uploader = GCSUploader('energy-env-data')
        for month in power_results['success']:
            # アップロード処理
            ...

    # 4. 電力データBQ投入
    power_bq = PowerBigQueryLoader(...)
    power_bq.load_power_data(5)

    # 5. 気象データBQ投入
    weather_bq = WeatherBigQueryLoader(...)
    weather_bq.load_weather_data('historical')
    weather_bq.load_weather_data('forecast')

    print("🏁 日次ETLパイプライン完了")

if __name__ == "__main__":
    main()
```

**削除するもの**:
- MainETLPipelineクラス全削除
- run_etl_for_daysメソッド削除
- _upload_downloaded_dataメソッド削除（GCS CLI化により不要）
- _create_summary_integratedメソッド削除（各モジュールが結果返すのでシンプルに）
- print_resultsも大幅簡略化

**シンプル化の理由**:
- 各モジュールがCLI対応 → 柔軟性は各モジュールで提供
- main_etl.pyは日次専用 → 複雑なエラーハンドリング不要（各モジュールで実装済み）
- クラス化不要 → テストは壊れているし、再利用されていない

## 引継ぎ事項（重要）

### なぜmain_etl.pyを根本から作り直すのか

**現状の問題**:
1. **前提が崩れた** - 元の設計は「柔軟性もmain_etl.pyで」だったが、天気データ統合で不可能に
2. **中途半端** - argparse削除したが、クラス設計はそのまま（複雑なまま）
3. **テストが壊れている** - test_main_etl.pyが既に動かない
4. **方針決定** - 「main_etl.pyは日次専用、柔軟性は各モジュールで」と決めた

**ゴール**:
- main_etl.py = 100行以下のシンプルなスクリプト
- 各モジュールを順次呼び出すだけ
- クラス不要、複雑なエラーハンドリング不要

**前提条件**:
- WeatherDownloader月/日指定対応完了
- gcs_uploader CLI対応完了

### 実装上の注意点

**GCSアップロード部分**:
現在の`_upload_downloaded_data`は以下をやっている：
1. 成功した月ディレクトリをループ
2. 各月の*.csvファイルを検索
3. `raw_data/{month}/{filename}`のパスでアップロード

CLI化後:
```bash
# 各モジュールが返す結果から月を特定
for month in power_results['success']:
    python -m src.data_processing.gcs_uploader \
      --upload-dir data/raw/${month} \
      --prefix raw_data/${month}
```

またはPythonで直接呼び出し:
```python
uploader = GCSUploader('energy-env-data')
for month in power_results['success']:
    month_dir = Path(base_dir) / month
    csv_files = list(month_dir.glob("*.csv"))
    for csv_file in csv_files:
        gcs_path = f"raw_data/{month}/{csv_file.name}"
        uploader.upload_file(str(csv_file), gcs_path)
```

**エラーハンドリング**:
現在はrun_etl_for_daysで全てtry/exceptしているが、各モジュールが既にエラーハンドリング済みなので、main_etl.pyは最小限で良い。

## プロジェクト全体への影響

### データパイプライン整備状況

| コンポーネント | CLI対応 | 月/日指定 | 状態 |
|--------------|---------|---------|------|
| PowerDataDownloader | ✅ | ✅ | 完成 |
| WeatherDownloader | ✅ | ❌ | **要改修** |
| GCSUploader | ❌ | - | **要改修** |
| PowerBigQueryLoader | ✅ | ✅ | 完成 |
| WeatherBigQueryLoader | ✅ | ✅ | 完成 |
| main_etl.py | - | - | **要作り直し** |

### 今後の実装フロー

```
1. WeatherDownloader改修（月/日指定追加）
   ↓
2. gcs_uploader改修（CLI対応追加）
   ↓
3. main_etl.py根本的作り直し（シンプル化）
   ↓
4. 最新月までのデータ取得実行（テスト）
   ↓
5. 日次処理実装・Airflow環境構築
```

---

## Phase 11 実装TODO（更新版）

### **最優先（順序重要）**
1. ⏸️ **WeatherDownloaderに月/日指定機能追加** [pending] ← **次セッション最優先**
2. ⏸️ **gcs_uploaderにCLI対応追加** [pending] ← **次セッション優先**
3. ⏸️ **main_etl.pyに天気データ統合・根本的作り直し** [in_progress] ← **上記2つ完了後**

### **テスト・運用開始**
4. ⏸️ **最新月までのデータ取得実行（電気・天気）← テスト代わり** [pending]
5. ⏸️ **日次処理実装（電気・天気の自動実行）** [pending]

### **監視・精度検証**
6. ⏸️ **異常検知システム実装** [pending]
7. ⏸️ **過去5回分の予測実行（例：10/4、10/3、10/2、10/1、9/30）** [pending]
8. ⏸️ **予測精度検証モジュール実装（1日目～16日目の精度を5回分平均で算出）** [pending]
9. ⏸️ **BQ修正・作成（精度検証結果反映）** [pending]
10. ⏸️ **日次実行セット（予測+精度検証の自動運用開始）** [pending]

### **可視化・インフラ**
11. ⏸️ **Looker Studio予測結果表示ダッシュボード作成** [pending]
12. ⏸️ **天気データGCSアップロード実装** [pending]
13. ⏸️ **予測結果GCSアップロード実装** [pending]
14. ⏸️ **Airflow環境構築・DAG実装（Cloud Composer使用）** [pending]

---

**次回**: WeatherDownloader月/日指定機能追加（最優先）
**目標**: 各モジュールの完全独立化・CLI対応完了
