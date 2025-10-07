# Phase 11 power_bigquery_loader コードレビュー完了・リファクタリング実施

## セッション概要
**日付**: 2025年10月7日
**作業内容**: power_bigquery_loader.pyのコードレビュー実施、複数のリファクタリング対応
**成果**: コードの簡潔化、データ検証強化、ファイル管理方針の最適化

## 今回の主要成果

### 1. get_required_months メソッド削除

#### 問題点
- 1箇所でしか使われない3-4行の単純な処理を関数化していた
- 複数日 → 該当月を取得してdistinctする処理が過剰に抽象化

#### 修正内容
```python
# 修正前: メソッド化
months = self.get_required_months(days)

# 修正後: load_power_data内に直書き
dates = [yesterday - timedelta(days=i) for i in range(days + 1)]
months = {date.strftime('%Y%m') for date in dates}
print(f"過去{days}日分に必要な月: {sorted(months)}")
```

### 2. CSV解析ロジックの修正

#### 実際のCSV構造の確認
```
2023/1/1 23:55 UPDATE
ピーク時供給力(万kW),時間帯,...           ← ヘッダー1
4506,20:00～21:00,1/1,23:50,48,67        ← データ1

予想最大電力(万kW),時間帯,...           ← ヘッダー2
...

DATE,TIME,当日実績(万kW),予想値(万kW),... ← ヘッダー3（14行目）
2023/1/1,0:00,2870,2866,78,3672         ← 実データ開始（15行目）
2023/1/1,1:00,2721,2720,77,3492
...
2023/1/1,23:00,...                      ← 実データ終了（38行目）
```

- CSVは複数セクションに分かれたテキスト形式
- 14行目に`DATE,TIME,当日実績(万kW)`ヘッダー
- 15-38行目の24行が実データ（0時～23時）

#### 修正内容

**修正前（DictReader使用）**:
```python
with open(csv_file_path, 'r', encoding='shift_jis') as f:
    reader = csv.DictReader(f)
    for csv_row in reader:
        date_str = csv_row.get('DATE')
        # ...
```
→ 複数ヘッダーがある構造に対応できない

**修正後（行単位で処理）**:
```python
# 1. ファイル全体を読み込み
with open(csv_file_path, 'r', encoding='shift_jis') as f:
    content = f.read()
lines = content.split('\n')

# 2. ヘッダー行を探す
header_line_index = -1
for i, line in enumerate(lines):
    if 'DATE,TIME,当日実績(万kW)' in line:
        header_line_index = i
        break

# 3. ヘッダーの次行から24行処理
for i in range(header_line_index + 1, header_line_index + 25):
    # ...
```

### 3. データ検証の強化

#### 追加した検証
1. **24行分のデータ存在確認**
2. **空行・列数不足のエラー検出**
3. **24行取得できたか確認**
4. **最終行の時刻が23時であることを確認**

```python
# 24行取得できたか確認
if len(rows) != 24:
    print(f"24時間分のデータが取得できませんでした: {csv_file_path.name} (取得行数: {len(rows)})")
    return []

# 最後の行の時刻が23時であることを確認
if rows[-1]['hour'] != 23:
    print(f"最終行の時刻が23時ではありません: {csv_file_path.name} (最終時刻: {rows[-1]['hour']})")
    return []
```

### 4. 日付変換の簡潔化

**修正前（冗長）**:
```python
date_parts = date_str.split('/')
if len(date_parts) == 3:
    year = date_parts[0]
    month = date_parts[1].zfill(2)
    day = date_parts[2].zfill(2)
    formatted_date = f"{year}-{month}-{day}"
else:
    formatted_date = date_str
```

**修正後（シンプル）**:
```python
formatted_date = datetime.strptime(date_str, '%Y/%m/%d').strftime('%Y-%m-%d')
```

### 5. ファイル管理方針の変更

#### 方針変更
- **修正前**: 処理済みCSVをarchiveディレクトリに移動
- **修正後**: 処理済みCSVを削除

#### 理由
1. **元データはZIPで残っている**（data/raw/202501/202501.zip）
2. **GCSにアップロード済み**
3. **BigQueryに投入済み**

→ 3箇所にデータがあるので解凍後のCSVを保持する必要なし

#### 実装
```python
# move_processed_files メソッド削除

# load_power_data内で直接削除
for csv_file in processed_files:
    csv_file.unlink()
    print(f"処理済みファイル削除: {csv_file.name}")
```

### 6. BQスキーマへの対応

**created_atカラムを追加**:
```sql
ALTER TABLE `energy-env.prod_energy_data.energy_data_hourly`
ADD COLUMN created_at TIMESTAMP;
```

**BQスキーマ（最終版）**:
- date: DATE型
- hour: INTEGER型（文字列 → 整数に修正）
- actual_power: FLOAT型
- supply_capacity: FLOAT型
- created_at: TIMESTAMP型（新規追加）

## 技術的理解の向上

### 1. split()の動作

**split('\n')**: 改行文字で分割、区切り文字自体は削除される

```python
content = "行1\n行2\n行3"
lines = content.split('\n')
# → ['行1', '行2', '行3']  # \nは消える
```

他の例：
```python
"apple,banana,orange".split(',')
# → ['apple', 'banana', 'orange']  # カンマは消える
```

### 2. strip()の役割

**strip()**: 文字列の前後の空白（スペース、タブ、改行）を削除

```python
"  hello  ".strip()  # → "hello"
"\n  data  \n".strip()  # → "data"
```

CSVの各行処理で行末の改行や余計な空白を削除するために使用。

### 3. extendとappendの違い

**extend**: リストの要素を展開してフラットに追加
```python
all_rows.extend(rows)
# [辞書1, 辞書2] に [辞書3, 辞書4] を追加
# → [辞書1, 辞書2, 辞書3, 辞書4]  # フラット
```

**append**: リストをそのまま追加（ネスト）
```python
all_rows.append(rows)
# [辞書1, 辞書2] に [辞書3, 辞書4] を追加
# → [辞書1, 辞書2, [辞書3, 辞書4]]  # ネスト
```

### 4. globの動作

**Pathオブジェクトのメソッド**: ワイルドカードパターンでファイルを検索

```python
csv_files = list(month_dir.glob("*_power_usage.csv"))
# *_power_usage.csv = 「任意の文字列 + _power_usage.csv」
# 20250701_power_usage.csv、20250702_power_usage.csv などにマッチ
```

### 5. 負のインデックス

**rows[-1]**: リストの最後の要素

```python
rows = ['hour0', 'hour1', 'hour2', 'hour23']
rows[0]   # → 'hour0'   (最初)
rows[-1]  # → 'hour23'  (最後)
rows[-2]  # → 'hour2'   (最後から2番目)
```

### 6. if rows: の評価

**空でない場合のみ処理**:
```python
rows = []  # 空のリスト
if rows:  # → False（実行されない）
    all_rows.extend(rows)

rows = [{'date': '2023-01-01', ...}]  # 要素あり
if rows:  # → True（実行される）
    all_rows.extend(rows)
```

## プロジェクト全体への影響

### データパイプライン整備状況

| コンポーネント | 実装状況 | 備考 |
|--------------|---------|------|
| 電力データダウンロード | ✅ 完了 | PowerDataDownloader |
| 電力データBQ投入 | ✅ 完了 | PowerBigQueryLoader（今回レビュー完了） |
| 気象データダウンロード | ✅ 完了 | WeatherDownloader |
| 気象データBQ投入 | ✅ 完了 | WeatherBigQueryLoader |

### 次のステップ
main_etl.pyへの統合により、電力+天気の完全自動パイプライン構築へ。

## 次回セッション予定

### 1. main_etl.pyに天気データ統合（優先）
**目的**: 電力+天気の統合パイプライン化

**実装内容**:
- WeatherDownloader、WeatherBigQueryLoaderの統合
- PowerBigQueryLoaderの統合
- 実行フロー整理（ダウンロード → BQ投入の2段階）

### 2. 最新月までのデータ取得実行（テスト）
**目的**: 実装したパイプラインの動作確認

**実行内容**:
- 電力データ: 最新月までダウンロード・BQ投入
- 気象データ: 最新データダウンロード・BQ投入
- エラーハンドリング確認

---

## Phase 11 実装TODO

1. ✅ **weather_bigquery_loader コードレビュー完了** [completed]
2. ✅ **weather_downloader 欠損値チェック実装（データ長一致検証）** [completed]
3. ✅ **電力BQインサート実装（power_bigquery_loader.py新規作成）** [completed]
4. ✅ **power_bigquery_loader コードレビュー完了・リファクタリング実施** [completed]
5. ⏸️ **main_etl.pyに天気データ統合（電力+天気の統合パイプライン化）** [pending]
6. ⏸️ **最新月までのデータ取得実行（電気・天気）← テスト代わり** [pending]
7. ⏸️ **日次処理実装（電気・天気の自動実行）** [pending]
8. ⏸️ **異常検知システム実装** [pending]
9. ⏸️ **過去5回分の予測実行（例：10/4、10/3、10/2、10/1、9/30）** [pending]
10. ⏸️ **予測精度検証モジュール実装（1日目～16日目の精度を5回分平均で算出）** [pending]
11. ⏸️ **BQ修正・作成（精度検証結果反映）** [pending]
12. ⏸️ **日次実行セット（予測+精度検証の自動運用開始）** [pending]
13. ⏸️ **Looker Studio予測結果表示ダッシュボード作成** [pending]
14. ⏸️ **天気データGCSアップロード実装** [pending]
15. ⏸️ **予測結果GCSアップロード実装** [pending]
16. ⏸️ **Airflow環境構築・DAG実装（Cloud Composer使用）** [pending]

---

**次回**: main_etl.pyに天気データ統合（電力+天気の統合パイプライン化）
**目標**: ETLパイプラインの完全統合
