# Phase 11 WeatherDownloader・gcs_uploader改修完了

## セッション概要
**日付**: 2025年10月9日
**作業内容**: WeatherDownloaderの月/日指定機能追加、gcs_uploaderのCLI対応・リファクタリング
**成果**: 各モジュールの完全独立化・CLI対応完了、次回main_etl.pyシンプル化の準備完了

## 今回の主要成果

### 1. WeatherDownloaderに月/日指定機能追加

#### 追加したメソッド

**`download_historical_data(start_date, end_date)`** - 期間指定取得
```python
# 開始日・終了日を明示的に指定
downloader.download_historical_data('2025-07-01', '2025-07-31')
# → chiba_2025_07_historical_range.json
```

**`download_for_month(yyyymm)`** - 月指定取得
```python
# YYYYMM形式で月を指定（1日～月末を自動計算）
downloader.download_for_month('202507')
# → chiba_2025_07_historical_month.json
```

#### argparse拡張

```bash
# 期間指定
python -m src.data_processing.weather_downloader --start-date 2025-07-01 --end-date 2025-07-31

# 月指定
python -m src.data_processing.weather_downloader --month 202507

# 既存の日次自動実行（変更なし）
python -m src.data_processing.weather_downloader
```

#### 既存メソッドとの関係

- **`download_daily_weather_data(target_date=None)`**: 変更なし
  - `target_date=None`: 日次自動実行用（過去10日+予測16日）
  - `target_date`指定: 指定日から30日前まで（**自動計算**）
- **`download_historical_data(start_date, end_date)`**: 新規追加
  - 両方の日付を**明示的に指定**
- **`download_for_month(yyyymm)`**: 新規追加
  - 月指定から1日～月末を**自動計算**

3つのメソッドが**並存**し、用途に応じて使い分け可能。

### 2. gcs_uploaderにCLI対応追加

#### 追加したCLI機能

**ファイル単体アップロード**
```bash
python -m src.data_processing.gcs_uploader \
  --file data/raw/202507/20250701_power_usage.csv \
  --destination raw_data/202507/20250701_power_usage.csv
```

**ディレクトリアップロード**
```bash
python -m src.data_processing.gcs_uploader \
  --upload-dir data/raw/202507 \
  --prefix raw_data/202507
```

#### オプション

- `--file`: アップロードするファイルパス
- `--destination`: GCS上の保存先パス（**必須**、バケットルート配置防止）
- `--upload-dir`: アップロードするディレクトリパス
- `--prefix`: GCS上のプレフィックス（**必須**、バケットルート配置防止）
- `--bucket`: GCSバケット名（デフォルト: energy-env-data）
- `--file-extension`: 特定の拡張子のファイルのみアップロード

#### 引数チェック

- `--file`と`--upload-dir`の排他チェック
- `--file`指定時の`--destination`必須チェック
- `--upload-dir`指定時の`--prefix`必須チェック
- 全てバケットルート配置を防ぐ設計

### 3. gcs_uploaderのリファクタリング

#### pathlib使用

**Before（os.path）**:
```python
for item in os.listdir(local_dir_path):
    local_file_path = os.path.join(local_dir_path, item)
    if os.path.isdir(local_file_path):
        continue
```

**After（pathlib）**:
```python
for file_path in dir_path.iterdir():
    if not file_path.is_file():
        continue
```

**メリット**:
- より読みやすい
- `is_file()`で明確
- パス操作がシンプル

#### 一時ファイル削除（メモリ内処理）

**Before（無駄な一時ファイル）**:
```python
# 1. ファイルに書き出し
processed_file_path = self._process_raw_csv_to_hourly(input_csv_path)
# → data/raw/202507/20250701_hourly_temp.csv 作成

# 2. そのファイルをアップロード
uri = self.upload_file(processed_file_path, processed_gcs_path)

# 3. 削除
os.remove(processed_file_path)  # ← 無駄！
```

**After（メモリで処理）**:
```python
# 1. メモリで加工（文字列を返す）
processed_content = self._process_raw_csv_to_hourly_memory(input_csv_path)

# 2. メモリから直接GCSにアップロード
blob = self.bucket.blob(processed_gcs_path)
blob.upload_from_string(processed_content, content_type='text/csv')
```

**メリット**:
- 一時ファイル不要
- ディスクI/O削減
- より高速

#### os.walk削除（1階層のみ処理）

**設計判断**: このプロジェクトの実態
- 日次実行が99%（1つの月フォルダのファイルをアップロード）
- 複数月一括はイレギュラー（年数回、その時はforで回せる）
- 月フォルダ内はフラット構造（`data/raw/202507/*.csv`、サブフォルダなし）

**Before（os.walk、再帰的探索）**:
```python
for root, _, files in os.walk(local_dir_path):
    # サブディレクトリも探索（archiveも含まれる可能性）
```

**After（iterdir、1階層のみ）**:
```python
for file_path in dir_path.iterdir():
    if not file_path.is_file():
        continue  # サブディレクトリは無視
```

**メリット**:
- archiveフォルダの心配なし
- シンプルで意図が明確
- 日次実行に最適

#### デフォルト値設定

**`__init__`メソッド**:
```python
def __init__(self, bucket_name='energy-env-data', project_id='energy-env'):
```

**メリット**:
- 引数なしでインスタンス化可能
- プロジェクトのデフォルト値を明示

#### 英語ログの日本語化

全てのログメッセージを日本語に統一：
- `ローカルファイルが見つかりません`
- `ファイルアップロード完了`
- `ディレクトリではありません`
- `CSV加工・アップロード完了`
- `CSVファイル加工失敗`
- `ディレクトリアップロード完了`
- `CSVを1時間データに加工中`
- `CSVヘッダー行が見つかりません`
- `無効な行をスキップ`
- `1時間データ加工完了`
- `CSV加工エラー`

## 技術的理解の向上

### パターンA vs パターンB（前回の議論の続き）

前回セッション（20251008）で「各モジュールの完全独立化・CLI対応」という方針が決定。

**正しい実装順序**:
1. ✅ **WeatherDownloader改修**（月/日指定追加）← 今回完了
2. ✅ **gcs_uploader改修**（CLI対応追加）← 今回完了
3. → **main_etl.py根本的作り直し**（シンプル化）← 次回

**理由**: main_etl.pyをシンプル化 = 「柔軟性は各モジュールで」という前提。前提機能がないのにmain_etl.pyだけ直しても意味がない。

### gcs_uploaderの設計判断

#### 当初の懸念: CSV加工処理の重複

**power_bigquery_loader.py（既に実装済み）**:
- CSV加工: `parse_csv_to_rows()`
- BQ投入
- CSV削除: `csv_file.unlink()`
- BQログ記録

**gcs_uploader.py（今回実装）**:
- CSV加工: `_process_raw_csv_to_hourly_memory()` ← 重複？
- GCSアップロード
- CSV削除 ← 重複？

#### 最終設計: 汎用アップローダーに

**決定事項**: gcs_uploaderを「電力、天気、予測結果」に対応した汎用アップローダーにする

```python
def upload_directory(self, local_dir_path, destination_prefix,
                     data_type='raw', file_extension=None):
    """
    Args:
        data_type (str): データタイプ
            - 'power': 電力CSV（加工してアップロード + 削除）
            - 'weather': 天気JSON（そのままアップロード）
            - 'prediction': 予測結果CSV（そのままアップロード）
    """
```

**各モジュールから呼び出し**:
```python
# power_bigquery_loader.py
uploader = GCSUploader()
uploader.upload_directory(month_dir, f'raw_data/{month}', data_type='power')

# weather_bigquery_loader.py (将来)
uploader.upload_directory(weather_dir, f'weather_data/{date}', data_type='weather')

# prediction_exporter.py (将来)
uploader.upload_directory(pred_dir, f'predictions/{date}', data_type='prediction')
```

**実装タイミング**: 後回し（TODO 12で実施）

### Pythonの基礎理解

#### クラス vs 関数

**関数（一般的）**:
```python
def calculate_sum(a, b):
    return a + b

result = calculate_sum(1, 2)
```

**クラス（状態を保持）**:
```python
uploader = GCSUploader('bucket-name')  # ←状態を保持
uploader.upload_file('f1.csv', 'd1.csv')
uploader.upload_file('f2.csv', 'd2.csv')  # ←同じclientを使いまわす
```

- **状態不要 → 関数**（シンプル）
- **状態必要 → クラス**（gcs_uploaderはこっち）

#### インポート

どちらもインポート可能：
```python
from module import MyClass, my_function, CONSTANT

# すべて使える
obj = MyClass()
obj.method()
my_function()
print(CONSTANT)
```

**クラスのメリット**: クラスをインポートすれば、そのクラスのすべてのメソッドが使える

#### pathlib

**`os.listdir()`**: ファイルもディレクトリも混ざって返す
```python
os.listdir('data/raw/202507')
# → ['file1.csv', 'file2.csv', 'subdir', 'file3.csv']
```

**`Path.iterdir()`**: 1階層のみ列挙（明確）
```python
for item in Path('data/raw/202507').iterdir():
    if item.is_file():
        ...  # ファイルのみ処理
```

**glob**: パターンマッチング
```python
Path('data/raw').glob('*.csv')  # → file1.csv, file2.csv
Path('data/raw').glob('**/*.csv')  # → 再帰的（サブディレクトリも）
```

**このプロジェクトでは`iterdir()`が最適**（意図が明確、1階層のみ）

#### GCS Blob

**Blob = Binary Large Object**: GCSでは**ファイル1つ1つ**を「blob」と呼ぶ

```python
# Blobオブジェクト作成（アップロード先情報を保持）
blob = self.bucket.blob(destination_blob_name)
# → blobは「energy-env-dataバケットのraw_data/test.csv」という情報を持つ

# アップロード実行（ローカルファイルパスだけ渡す）
blob.upload_from_filename(local_file_path)
# → blobが既に持っている「アップロード先情報」に、local_file_pathのファイルをアップロード
```

**`blob`オブジェクト** = Google Cloud Storage Python SDK (`google-cloud-storage`) が提供する専用クラス

#### パス操作

```python
path = "C:/Users/tetsu/data/raw/202507/file.csv"

os.path.basename(path)  # → "file.csv"（ファイル名のみ）
os.path.dirname(path)   # → "C:/Users/tetsu/data/raw/202507"（ディレクトリ部分）
```

#### GCSのプレフィックス

GCSは実際には**フォルダがなく、すべてフラットなオブジェクト名**。プレフィックスは「フォルダっぽく見せる」ための仕組み。

```
バケット: energy-env-data
  ├─ raw_data/           ← フォルダっぽく見える（実際はプレフィックス）
  │   └─ 202507/         ← フォルダっぽく見える（実際はプレフィックス）
  │       └─ 20250701_power_usage.csv
```

実際には `raw_data/202507/20250701_power_usage.csv` という**1つの長い名前のオブジェクト**。

## 次回セッションで実装すること

### 優先度順

1. **main_etl.pyに天気データ統合・根本的作り直し**（TODO 2）
   - 前提条件: WeatherDownloader、gcs_uploaderの改修完了 ✅
   - main_etl.pyをシンプルなスクリプトに（100行以下目標）
   - クラス削除、各モジュールを順次呼び出すだけ

2. **最新月までのデータ取得実行（電気・天気）**（TODO 3）
   - テスト代わりに大量データ取得
   - 改修したモジュールの動作確認

3. **日次処理実装（電気・天気の自動実行）**（TODO 4）
   - main_etl.pyを日次で自動実行

4. **gcs_uploaderをdata_type対応にリファクタリング**（TODO 12）
   - power/weather/prediction対応
   - 各BQローダーから呼び出すように修正

## プロジェクト全体への影響

### データパイプライン整備状況

| コンポーネント | CLI対応 | 月/日指定 | 状態 |
|--------------|---------|---------|------|
| PowerDataDownloader | ✅ | ✅ | 完成 |
| WeatherDownloader | ✅ | ✅ | **完成** ← 今回 |
| GCSUploader | ✅ | - | **CLI完成**（リファクタリング保留）← 今回 |
| PowerBigQueryLoader | ✅ | ✅ | 完成 |
| WeatherBigQueryLoader | ✅ | ✅ | 完成 |
| main_etl.py | - | - | **要作り直し** ← 次回 |

### パイプライン設計の明確化

**パターンB（import）を維持**:
- TODO 15「Airflow環境構築」があるため、将来パターンA（CLI実行）に移行可能
- 現時点ではシンプルさ優先
- 各モジュールは既にCLI対応済み → Airflow移行時に切り替え容易

**main_etl.pyの役割**:
- 日次実行専用（引数なし、固定パラメータ）
- オーケストレーション（正しい順序、エラー時のスキップ判断）
- 統合ログ・サマリー

**柔軟な実行**（月指定、日指定、カスタムパラメータ）は各モジュールを直接叩く:
```bash
# アドホック作業例: 7月だけやり直し
python -m src.data_processing.data_downloader --month 202507
python -m src.data_processing.weather_downloader --month 202507
python -m src.data_processing.gcs_uploader --upload-dir data/raw/202507 --prefix raw_data/202507
```

---

## Phase 11 実装TODO（更新版）

### 完了
1. ✅ **WeatherDownloaderに月/日指定機能追加**

### 未完了（優先度順）
2. ⏸️ **main_etl.pyに天気データ統合・根本的作り直し** ← 次セッション最優先
3. ⏸️ **最新月までのデータ取得実行（電気・天気）← テスト代わり**
4. ⏸️ **日次処理実装（電気・天気の自動実行）**
5. ⏸️ **異常検知システム実装**
6. ⏸️ **過去5回分の予測実行（例：10/4、10/3、10/2、10/1、9/30）**
7. ⏸️ **予測精度検証モジュール実装（1日目～16日目の精度を5回分平均で算出）**
8. ⏸️ **BQ修正・作成（精度検証結果反映）**
9. ⏸️ **日次実行セット（予測+精度検証の自動運用開始）**
10. ⏸️ **Looker Studio予測結果表示ダッシュボード作成**
11. ⏸️ **Looker Studio監視ページ作成（プロセス実行ログ・エラー監視）** ← 今回追加
12. ⏸️ **gcs_uploaderをdata_type対応にリファクタリング（power/weather/prediction）**
13. ⏸️ **power_bigquery_loaderからgcs_uploader呼び出し実装（電力データGCSアップロード）**
14. ⏸️ **weather_bigquery_loaderからgcs_uploader呼び出し実装（天気データGCSアップロード）**
15. ⏸️ **prediction系モジュールからgcs_uploader呼び出し実装（予測結果GCSアップロード）**
16. ⏸️ **Airflow環境構築・DAG実装（Cloud Composer使用）**

---

**次回**: main_etl.py根本的作り直し（シンプル化）
**目標**: 各モジュールの完全独立化完了、日次実行環境整備
