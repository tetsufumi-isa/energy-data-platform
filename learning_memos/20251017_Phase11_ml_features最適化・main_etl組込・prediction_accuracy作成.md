# Phase 11 進捗記録 - ml_features最適化・main_etl組込・prediction_accuracy作成

**日付**: 2025年10月17日
**フェーズ**: Phase 11（基盤整備→日次運用→予測精度分析）
**セッション内容**: ml_features_updater.pyクエリ最適化・main_etl.py組込・prediction_accuracy_updater.py作成

---

## セッション概要

予測精度分析の基盤整備として、以下を実施：
1. **ml_features_updater.pyコードレビュー・最適化**: BigQueryクエリの効率化（事前フィルタ・カラム指定）
2. **main_etl.pyへの組み込み**: Phase 5としてml_features更新を挿入
3. **prediction_accuracy_updater.py作成**: 予測値vs実績値の精度分析テーブル更新モジュール

**所要時間**: 約1.5時間
**成果**: 日次パイプライン拡張・予測精度分析基盤整備完了

---

## 主要成果

### 1. ml_features_updater.pyクエリ最適化

**問題点の指摘（ユーザーレビュー）:**
- WITH句内でJOIN後にWHERE条件
- SELECT *で全カラム取得
- date_lag_mappingが全テーブルスキャン

**修正内容:**

**最適化前:**
```sql
WITH base_data AS (
  SELECT ...
  FROM energy_data_hourly energy
  LEFT JOIN weather_data weather ...
  LEFT JOIN calendar_data calendar ...
  WHERE energy.date >= DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 7 DAY)
)
```

**最適化後:**
```sql
WITH energy_filtered AS (
  SELECT date, hour, actual_power, supply_capacity
  FROM energy_data_hourly
  WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 7 DAY)
),
weather_filtered AS (
  SELECT date, hour, temperature_2m, ...
  FROM weather_data
  WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 7 DAY)
    AND prefecture = '千葉県'
),
calendar_filtered AS (
  SELECT date, day_of_week, is_weekend, is_holiday
  FROM calendar_data
  WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 7 DAY)
),
lag_mapping_filtered AS (
  SELECT base_date, lag_1_day_date, lag_7_day_date, lag_1_business_date
  FROM date_lag_mapping
  WHERE base_date >= DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 7 DAY)
),
base_data AS (
  SELECT ...
  FROM energy_filtered energy
  LEFT JOIN weather_filtered weather ...
  LEFT JOIN calendar_filtered calendar ...
)
```

**改善効果:**
- 事前フィルタで7日分のみスキャン（数ヶ月分→7日分）
- 必要なカラムのみ取得（列指向ストレージの最適化）
- prefecture条件も事前適用（weather_filtered）
- date_lag_mappingも7日分に絞り込み

**実装箇所**: `src/data_processing/ml_features_updater.py` (98-148行目)

---

### 2. main_etl.pyへのml_features更新組み込み

**Phase 5として挿入:**
```python
# Phase 5: ml_features更新
print("Phase 5: ml_features更新（過去7日分の学習データ再構築）")
result = subprocess.run(['python', '-m', 'src.data_processing.ml_features_updater'])
if result.returncode != 0:
    print("Phase 5 失敗: ml_features更新エラー")
    sys.exit(1)
```

**更新後のパイプライン構成:**
1. Phase 1: 電力データダウンロード
2. Phase 2: 気象データダウンロード
3. Phase 3: 電力データBigQuery投入
4. Phase 4-1/4-2: 気象データBigQuery投入
5. **Phase 5: ml_features更新** ← NEW!
6. Phase 6: データ品質チェック（旧Phase 5）
7. Phase 7: 予測実行（旧Phase 6）
8. Phase 8: ダッシュボードデータ更新（旧Phase 7）

**重要なポイント:**
- 電力・気象データ投入の**直後**
- 予測実行の**直前**
- **予測モデルが最新の学習データを使用できる**

**実装箇所**: `src/pipelines/main_etl.py` (81-87行目)

---

### 3. prediction_accuracy_updater.py作成

**目的:**
予測値（prediction_results）と実績値（energy_data_hourly）をJOINして精度分析テーブルを更新

**主要機能:**

**1. delete_recent_data()** (67-85行目)
```python
DELETE FROM prediction_accuracy
WHERE prediction_date >= DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 7 DAY)
```

**2. insert_prediction_accuracy()** (87-159行目)
```sql
WITH prediction_filtered AS (
  SELECT
    execution_id,
    DATE(created_at, 'Asia/Tokyo') AS prediction_run_date,  -- 予測実行日を抽出
    prediction_date,
    prediction_hour,
    predicted_power_kwh AS predicted_power,
    created_at
  FROM prediction_results
  WHERE prediction_date >= DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 7 DAY)
    AND prediction_date < CURRENT_DATE('Asia/Tokyo')  -- 実績確定データのみ
),
energy_filtered AS (
  SELECT date, hour, actual_power
  FROM energy_data_hourly
  WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 7 DAY)
    AND date < CURRENT_DATE('Asia/Tokyo')
)
SELECT
  pred.execution_id,
  pred.prediction_run_date,
  pred.prediction_date,
  pred.prediction_hour,
  pred.predicted_power,
  energy.actual_power,
  ABS(pred.predicted_power - energy.actual_power) AS error_absolute,
  ABS(pred.predicted_power - energy.actual_power) / NULLIF(energy.actual_power, 0) * 100 AS error_percentage,
  DATE_DIFF(pred.prediction_date, pred.prediction_run_date, DAY) AS days_ahead,
  CURRENT_TIMESTAMP() AS created_at
FROM prediction_filtered pred
INNER JOIN energy_filtered energy  -- 実績がないデータは除外
  ON pred.prediction_date = energy.date
  AND pred.prediction_hour = energy.hour
```

**重要なポイント:**
- `DATE(created_at, 'Asia/Tokyo')`: prediction_resultsのTIMESTAMPから実行日を抽出
- `prediction_date < CURRENT_DATE()`: 今日より前（実績確定済み）のみ
- `NULLIF(energy.actual_power, 0)`: ゼロ除算回避
- `INNER JOIN`: 実績がないデータは除外
- `DATE_DIFF()`: 何日後の予測かを計算（0=当日、1=翌日、...）

**実装箇所**: `src/data_processing/prediction_accuracy_updater.py`

---

## 技術的理解の向上

### BigQueryクエリ最適化のベストプラクティス

**1. 事前フィルタリング（WHERE句を先に適用）:**
```sql
-- ❌ 非効率（JOIN後にフィルタ）
WITH base AS (
  SELECT * FROM large_table
  LEFT JOIN another_table ...
  WHERE date >= '2024-10-10'
)

-- ✅ 効率的（フィルタ後にJOIN）
WITH filtered AS (
  SELECT col1, col2 FROM large_table
  WHERE date >= '2024-10-10'
),
base AS (
  SELECT ... FROM filtered LEFT JOIN ...
)
```

**2. 必要なカラムのみ指定（列指向ストレージ最適化）:**
```sql
-- ❌ 全カラムスキャン
SELECT * FROM table

-- ✅ 必要なカラムのみ
SELECT date, hour, actual_power FROM table
```

**3. JOIN前に全テーブルを事前フィルタ:**
- energy_data_hourly
- weather_data
- calendar_data
- date_lag_mapping

### prediction_run_dateの取得方法

**課題:**
prediction_resultsテーブルには`created_at`（TIMESTAMP）しかない

**解決策:**
```sql
DATE(created_at, 'Asia/Tokyo') AS prediction_run_date
```
- TIMESTAMPを日本時間のDATEに変換
- 「いつ予測したか」を日付で表現

### 実績確定判定

**条件:**
```sql
WHERE prediction_date < CURRENT_DATE('Asia/Tokyo')
```
- 今日より前の日付のみ
- 今日のデータは実績が確定していない可能性
- 昨日以前のデータのみをINSERT

---

## 修正ファイル一覧

| ファイル | 修正内容 |
|---------|---------|
| `src/data_processing/ml_features_updater.py` | クエリ最適化（事前フィルタ・カラム指定） |
| `src/pipelines/main_etl.py` | Phase 5追加（ml_features更新組み込み） |
| `src/data_processing/prediction_accuracy_updater.py` | 新規作成（予測精度分析テーブル更新） |

---

## 次回セッション予定

### 実施予定タスク（優先順）

1. **prediction_accuracy_updater.pyコードレビュー**
   - ユーザーレビュー待ち

2. **prediction_accuracy更新をmain_etl.pyに組み込み**
   - Phase 8または9として追加

3. **予測精度の検証（手動確認）**
   - ml_features更新後に予測実行
   - prediction_accuracy更新後に精度確認

4. **予測モジュールの日別実行対応（基準日指定機能追加）**

5. **予測精度向上（特徴量・モデル改善）**

6. **Looker Studio監視ページ実装**

7. **Looker Studio予測結果表示ダッシュボード作成**

---

## TODOリスト

### 完了済み
- [x] ml_features_updater.pyコードレビュー
- [x] ml_features更新をmain_etl.pyに組み込み（Phase 5として挿入）
- [x] prediction_accuracyインサートモジュール作成

### 未完了
- [ ] prediction_accuracy_updater.pyコードレビュー
- [ ] prediction_accuracy更新をmain_etl.pyに組み込み
- [ ] 予測精度の検証（手動確認）
- [ ] 予測モジュールの日別実行対応（基準日指定機能追加）
- [ ] 予測精度向上（特徴量・モデル改善）
- [ ] Looker Studio監視ページ実装（BigQueryビュー作成 → Looker Studio接続）
- [ ] Looker Studio予測結果表示ダッシュボード作成

---

## 備考

### 今回のセッションで学んだこと

**1. BigQueryのクエリ最適化は明示的に:**
- オプティマイザーを信頼せず、事前フィルタを明示
- 列指向ストレージの特性を活かす（必要なカラムのみ）
- JOIN前に全テーブルをフィルタ

**2. TIMESTAMPからDATEの抽出:**
```sql
DATE(created_at, 'Asia/Tokyo')
```
- タイムゾーン指定が重要
- prediction_run_dateの取得に活用

**3. ゼロ除算対策:**
```sql
NULLIF(actual_power, 0)
```
- 除算前に0をNULLに変換
- エラー率計算で必須

**4. INNER JOIN vs LEFT JOIN:**
- 実績がないデータは除外したい → INNER JOIN
- 予測だけ存在して実績がない場合はスキップ

### 日次パイプラインの進化

**現在の構成（Phase 1-8）:**
1. 電力データ取得・投入
2. 気象データ取得・投入
3. **ml_features更新** ← NEW!
4. データ品質チェック
5. 予測実行
6. ダッシュボードデータ更新

**次回追加予定（prediction_accuracy更新）:**
- 予測実行後またはダッシュボード更新後
- 実績確定後の精度計算
- Phase 8または9として追加

### prediction_accuracyの活用イメージ

**1. 日数別精度分析（0日後～13日後）:**
```sql
SELECT
  days_ahead,
  AVG(error_percentage) as avg_mape,
  COUNT(*) as prediction_count
FROM prediction_accuracy
WHERE prediction_run_date >= '2024-10-01'
GROUP BY days_ahead
ORDER BY days_ahead
```

**2. 時刻別精度分析:**
```sql
SELECT
  prediction_hour,
  AVG(error_percentage) as avg_mape
FROM prediction_accuracy
WHERE days_ahead = 1  -- 1日後予測のみ
GROUP BY prediction_hour
ORDER BY prediction_hour
```

**3. トレンド分析（精度は改善しているか）:**
```sql
SELECT
  prediction_run_date,
  AVG(error_percentage) as avg_mape
FROM prediction_accuracy
WHERE days_ahead <= 7
GROUP BY prediction_run_date
ORDER BY prediction_run_date
```
