# Phase 11 weather_bigquery_loader.py JSON対応リファクタリング完了

## セッション概要
**日付**: 2025年10月5日
**作業内容**: weather_bigquery_loader.pyをCSV→JSON対応にリファクタリング
**成果**: JSONファイル直接読み込み・BQ投入処理完成

## 今回の主要成果

### 1. 背景：天気データBQインサート処理の課題発覚

#### 現状確認
- `weather_downloader.py`: JSONファイルでデータ保存
- `weather_bigquery_loader.py`: CSV前提の処理（EXTERNAL TABLE方式）
- **問題**: JSONデータをBQにインサートできない

#### BQテーブルスキーマ確認
```
テーブル: energy-env.dev_energy_data.weather_data

カラム:
- prefecture: STRING (都道府県)
- date: DATE (日付)
- hour: STRING (時刻)
- temperature_2m: FLOAT (気温)
- relative_humidity_2m: FLOAT (相対湿度)
- precipitation: FLOAT (降水量)
- weather_code: INTEGER (天気コード)
- created_at: TIMESTAMP (登録日時)
```

### 2. リファクタリング実装内容

#### 主要変更点

**before（CSV方式）:**
1. GCSからCSVファイル取得
2. EXTERNAL TABLE作成
3. EXTERNAL TABLE → 本テーブルにINSERT
4. EXTERNAL TABLE削除
5. GCS内でファイル移動

**after（JSON方式）:**
1. ローカルJSONファイル検索
2. JSON解析 → BQ用行データに変換
3. 重複削除
4. `insert_rows_json()`で直接BQインサート
5. 処理済みファイルをarchive/に移動

#### 新規メソッド実装

**`get_unprocessed_json_files()` (53-67行目)**
```python
def get_unprocessed_json_files(self, data_type="forecast"):
    pattern = f"*_{data_type}.json"
    json_files = list(self.json_dir.glob(pattern))
    return json_files
```
- ローカルディレクトリからJSONファイル検索
- `*_historical.json` または `*_forecast.json`パターン

**`parse_json_to_rows()` (69-109行目)**
```python
def parse_json_to_rows(self, json_file_path):
    # JSON読み込み
    data = json.load(f)
    hourly_data = data.get('hourly', {})

    # 各時刻のデータを行に変換
    for i, time_str in enumerate(times):
        dt = datetime.fromisoformat(time_str)
        row = {
            'prefecture': '千葉県',
            'date': dt.strftime('%Y-%m-%d'),
            'hour': dt.strftime('%H'),
            'temperature_2m': temps[i],
            'relative_humidity_2m': humidity[i],
            'precipitation': precip[i],
            'weather_code': weather_codes[i],
            'created_at': datetime.now().isoformat()
        }
        rows.append(row)
```

**重要な変換処理:**
- `hourly.time`: `"2024-10-01T00:00"` → `date: "2024-10-01"`, `hour: "00"`
- `prefecture`: 固定値 `"千葉県"`を追加
- `created_at`: 現在時刻を追加

**`delete_duplicate_data()` (111-137行目)**
```python
def delete_duplicate_data(self, rows):
    dates = [row['date'] for row in rows]
    min_date = min(dates)
    max_date = max(dates)

    delete_query = f"""
    DELETE FROM `{self.project_id}.{self.dataset_id}.{self.table_id}`
    WHERE date >= '{min_date}'
      AND date <= '{max_date}'
      AND prefecture = '千葉県'
    """
```
- インサート予定データの日付範囲を取得
- その範囲の既存データを削除（重複防止）

**`insert_weather_data()` (139-162行目)**
```python
def insert_weather_data(self, rows):
    table_ref = f"{self.project_id}.{self.dataset_id}.{self.table_id}"
    errors = self.bq_client.insert_rows_json(table_ref, rows)

    if errors:
        raise Exception(f"BQインサートエラー: {errors}")
```
- `insert_rows_json()`で直接BQインサート
- EXTERNAL TABLE不要

**`move_processed_files()` (164-184行目)**
```python
def move_processed_files(self, json_files):
    archive_dir = self.json_dir / 'archive'
    archive_dir.mkdir(exist_ok=True)

    for json_file in json_files:
        archive_path = archive_dir / json_file.name
        json_file.rename(archive_path)
```
- 処理済みJSONを`archive/`サブディレクトリに移動
- ローカルファイル管理で完結

#### メイン処理フロー (186-243行目)
```python
def load_weather_data(self, data_type="forecast"):
    # 1. JSONファイル取得
    json_files = self.get_unprocessed_json_files(data_type)

    # 2. JSON解析
    all_rows = []
    for json_file in json_files:
        rows = self.parse_json_to_rows(json_file)
        all_rows.extend(rows)

    # 3. 重複削除
    self.delete_duplicate_data(all_rows)

    # 4. データ投入
    rows_inserted = self.insert_weather_data(all_rows)

    # 5. ファイル移動
    self.move_processed_files(json_files)
```

### 3. 使用方法

```bash
# 予測データ投入
python -m src.data_processing.weather_bigquery_loader

# 過去データ投入
python -m src.data_processing.weather_bigquery_loader --data-type historical

# JSONディレクトリ指定
python -m src.data_processing.weather_bigquery_loader --json-dir /path/to/json
```

## 技術的理解の向上

### 1. 辞書のキー動的追加

```python
validation_result = {
    'valid': True,
    'issues': [],
    'stats': {}  # 空の辞書
}

# 存在しないキーへの代入で自動的にキー作成
validation_result['stats']['total_hours'] = len(hourly_data['time'])

# 結果
# {'stats': {'total_hours': 192}}
```

**重要な理解:**
- Pythonの辞書は存在しないキーへの代入で自動的にそのキーを作成
- 事前にキーを宣言する必要なし

### 2. CSV vs JSON BQ投入方式の違い

| 項目 | CSV (EXTERNAL TABLE) | JSON (insert_rows_json) |
|------|---------------------|------------------------|
| ファイル保存先 | GCS必須 | ローカルでOK |
| 処理方式 | SQL経由 | API経由 |
| 一時テーブル | 必要 | 不要 |
| データ変換 | SQL内で実施 | Python内で実施 |
| パフォーマンス | 大量データ向き | 小〜中量データ向き |

### 3. Open-Meteo APIレスポンス構造

```json
{
  "latitude": 35.6047,
  "longitude": 140.1233,
  "timezone": "Asia/Tokyo",
  "hourly": {
    "time": ["2024-10-01T00:00", "2024-10-01T01:00", ...],
    "temperature_2m": [20.5, 19.8, ...],
    "relative_humidity_2m": [65, 68, ...],
    "precipitation": [0.0, 0.0, ...],
    "weather_code": [1, 2, ...]
  }
}
```

**データ抽出ポイント:**
- `hourly.time`: 時刻情報（ISO形式） → `date`と`hour`に分割
- 4つの気象変数: 配列形式で同じインデックスが対応

## 次回セッション予定

### 優先実装項目
1. **weather_downloader.pyコードレビュー続き**
   - 335行目から再開
   - 残りのメソッド確認

2. **weather_downloader.pyリファクタリング実装のユーザーレビュー**

3. **weather_bigquery_loader.pyリファクタリング実装のユーザーレビュー**

4. **統合テスト実行**
   - weather_downloader.py実行（JSON保存）
   - weather_bigquery_loader.py実行（BQインサート）
   - BQデータ確認

## プロジェクト全体への影響

### コード改善
- **JSON対応完了**: weather_downloader → weather_bigquery_loaderの連携確立
- **シンプル化**: EXTERNAL TABLE不要、GCS不要でローカル完結
- **保守性向上**: データ変換ロジックがPython内で完結、SQLより可読性高い

### 学習の深化
- **辞書の動的キー追加**: Pythonの柔軟性理解
- **BQ投入方式の比較**: CSV vs JSONのユースケース理解
- **APIレスポンス処理**: JSON解析とデータ変換の実装パターン習得

---

## Phase 11 実装TODO

1. ⏸️ **weather_downloader.pyコードレビュー：335行目から続き** [pending]
2. ⏸️ **weather_downloader.pyリファクタリング実装のユーザーレビュー待ち** [pending]
3. ⏸️ **weather_bigquery_loader.pyリファクタリング実装のユーザーレビュー** [pending]
4. ⏳ 最新月までのデータ取得実行（電気・天気）← テスト代わり [pending]
5. ⏳ 日次処理実装（電気・天気の自動実行） [pending]
6. ⏳ 異常検知システム実装 [pending]
7. ⏳ 過去5回分の予測実行（例：10/4、10/3、10/2、10/1、9/30） [pending]
8. ⏳ 予測精度検証モジュール実装（1日目～16日目の精度を5回分平均で算出） [pending]
9. ⏳ BQ修正・作成（精度検証結果反映） [pending]
10. ⏳ 日次実行セット（予測+精度検証の自動運用開始） [pending]
11. ⏳ Looker Studio予測結果表示ダッシュボード作成 [pending]

---

**次回**: weather_downloader.pyコードレビュー335行目から再開
**目標**: Phase 11基盤修正フェーズ完了・日次運用開始準備
