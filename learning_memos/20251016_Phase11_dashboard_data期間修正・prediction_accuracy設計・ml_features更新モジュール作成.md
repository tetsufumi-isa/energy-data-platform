# Phase 11 進捗記録 - dashboard_data期間修正・prediction_accuracy設計・ml_features更新モジュール作成

**日付**: 2025年10月16日
**フェーズ**: Phase 11（基盤整備→日次運用→予測精度分析）
**セッション内容**: dashboard_data期間修正・prediction_accuracy設計・ml_features差分更新モジュール作成

---

## セッション概要

予測精度分析の基盤整備として、以下を実施：
1. **dashboard_data_updater期間修正**: 今日以降→7日前以降（昨日実績の反映漏れ対策）
2. **prediction_accuracyテーブル設計**: 予測値vs実績値の精度検証用テーブル作成
3. **ml_features_updater.py作成**: ml_featuresテーブルの差分更新モジュール実装
4. **main_etl.pyパイプライン拡張**: dashboard_data_updaterをPhase 7として組み込み

**所要時間**: 約2時間
**成果**: 予測精度分析の基盤整備完了・日次パイプライン拡張

---

## 主要成果

### 1. dashboard_data_updater.py期間修正

**問題点の発見:**
- 元の実装: 「今日以降」のデータのみ更新
- 問題: 昨日の実績は今日のETLで投入される
- 結果: **昨日の実績が反映されない**

**修正内容（4箇所）:**
```python
# 修正前
WHERE date >= CURRENT_DATE('Asia/Tokyo')

# 修正後
WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 7 DAY)
```

**修正箇所:**
- `delete_future_data()`: 削除対象（52-70行目）
- `insert_dashboard_data_direct()`: 3つのCTE（110, 126, 140行目）
  - energy_data_hourly
  - weather_data
  - prediction_results

**動作例（10月16日朝6:30実行）:**
- 削除: 10月9日（7日前）以降のデータを削除
- 投入: 10月9日～10月15日の実績 + 10月16日～10月29日の予測
- 結果: 直近1週間の実績トレンド + 未来2週間の予測を表示可能

**実装箇所**: `src/data_processing/dashboard_data_updater.py`

---

### 2. prediction_accuracyテーブル設計

**目的:**
予測値と実績値を紐付けて精度分析を行うための専用テーブル

**テーブル設計の議論:**

**当初案（実績カラム追加）:**
- prediction_resultsに`actual_power`カラムを追加
- 問題: BigQueryのUPDATEは高コスト（パーティション全体書き直し）

**最終案（専用テーブル）:**
- prediction_accuracyテーブルを新規作成
- 実績確定後にINSERTのみ（UPDATEなし）
- 効率的・低コスト

**スキーマ設計のポイント:**

**1. 予測実行日の表現:**
- 当初案: `days_ahead`のみ（例: 2 = 2日前の予測）
- 問題: 「いつ予測したか」が直接わからない
- 改善: `prediction_run_date`を追加

**2. days_aheadの定義:**
- 検討: 「2日前の予測」vs「2日後の予測」
- 結論: 「X日後の予測」の方が直感的
- 定義: `days_ahead = DATE_DIFF(prediction_date, prediction_run_date, DAY)`
- 範囲: 0～13（0=当日、1=翌日、...、13=13日後）

**最終スキーマ:**
```sql
CREATE TABLE prediction_accuracy (
  execution_id STRING NOT NULL,
  prediction_run_date DATE NOT NULL,   -- 予測実行日
  prediction_date DATE NOT NULL,       -- 予測対象日
  prediction_hour INT64 NOT NULL,
  predicted_power FLOAT64 NOT NULL,
  actual_power FLOAT64 NOT NULL,
  error_absolute FLOAT64,
  error_percentage FLOAT64,
  days_ahead INT64,                    -- 何日後の予測か（0～13）
  created_at TIMESTAMP NOT NULL
)
PARTITION BY prediction_date
CLUSTER BY prediction_run_date, days_ahead;
```

**実装箇所**: `sql/create_prediction_accuracy_table.sql`

---

### 3. ml_features_updater.py作成

**背景:**
- ml_featuresテーブルが7月4日で更新停止
- 原因: 日次パイプラインに組み込まれていない
- 影響: 予測モデルが古いデータでしか学習できない

**更新方式の選択:**

**案A: 全置換（DROP + CREATE）**
- 既存SQL: `create_ml_features_table.sql`
- デメリット: 毎日全データ読み込み（遅い、コスト高）

**案B: 差分更新（DELETE + INSERT）**
- dashboard_data_updaterと同じ方式
- メリット: 高速、低コスト、シンプル
- **採用**

**実装内容:**

**1. delete_recent_data():**
```python
DELETE FROM ml_features
WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 7 DAY)
```

**2. insert_ml_features():**
```sql
INSERT INTO ml_features (...)
WITH base_data AS (
  SELECT ... FROM energy_data_hourly energy
  LEFT JOIN weather_data weather ...
  LEFT JOIN calendar_data calendar ...
  WHERE energy.date >= DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 7 DAY)
)
SELECT
  base.*,
  SIN(2 * PI * base.hour / 24) as hour_sin,
  COS(2 * PI * base.hour / 24) as hour_cos,
  lag1.actual_power as lag_1_day,
  lag7.actual_power as lag_7_day,
  blag1.actual_power as lag_1_business_day
FROM base_data base
LEFT JOIN date_lag_mapping dlm ...
LEFT JOIN base_data lag1 ...
LEFT JOIN base_data lag7 ...
LEFT JOIN base_data blag1 ...
```

**特徴量の取得:**
- 1日前、7日前: 単純なDATE_SUB
- 1営業日前: `date_lag_mapping`テーブルを使用
  - 営業日に連番付与 → 連番-1の日付を取得
  - 土日・祝日を自動スキップ

**修正点:**
- weather_dataのJOIN条件を `prefecture = '千葉県'` に変更（元のSQLは`'chiba'`）

**実装箇所**: `src/data_processing/ml_features_updater.py`

---

### 4. main_etl.pyパイプライン拡張

**Phase 7追加:**
```python
# Phase 7: ダッシュボードデータ更新
print("Phase 7: ダッシュボードデータ更新（Looker Studio用）")
result = subprocess.run(['python', '-m', 'src.data_processing.dashboard_data_updater'])
```

**更新後の処理フロー:**
1. Phase 1: 電力データダウンロード
2. Phase 2: 気象データダウンロード
3. Phase 3: 電力データBigQuery投入
4. Phase 4-1/4-2: 気象データBigQuery投入
5. Phase 5: データ品質チェック
6. Phase 6: 予測実行
7. **Phase 7: ダッシュボードデータ更新** ← NEW!

**次回実装予定（ml_features更新）:**
- Phase 5として挿入（電力・天気データ投入後、予測実行前）
- 予測モデルが最新のml_featuresを使用できるようになる

**実装箇所**: `src/pipelines/main_etl.py`

---

## 技術的理解の向上

### 予測精度分析のデータフロー

**1. 予測実行（毎日）:**
```
prediction_iterative_with_export.py
  ↓
prediction_resultsテーブル（予測値のみ）
```

**2. 実績確定後（翌日以降）:**
```
prediction_results + energy_data_hourly
  ↓ JOIN
prediction_accuracy（予測値 + 実績値）
```

**3. 精度分析:**
```sql
SELECT
  days_ahead,
  AVG(error_percentage) as avg_mape
FROM prediction_accuracy
GROUP BY days_ahead
ORDER BY days_ahead
```

### BigQueryのUPDATE vs INSERT

**UPDATEのコスト:**
- パーティションテーブルのUPDATEは内部的に全体を書き直す
- 特定カラムのみの更新でもコスト高
- 毎日実行には不向き

**INSERT（追記型）のメリット:**
- 追記のみで高速
- コスト効率的
- BigQueryの推奨パターン

### date_lag_mappingの営業日計算

**エレガントな実装:**
```sql
-- 営業日に連番付与
business_days AS (
  SELECT date, ROW_NUMBER() OVER (ORDER BY date) as biz_row_num
  FROM calendar
  WHERE NOT is_holiday AND NOT is_weekend
)

-- 連番-1の日付を取得
lag_1_business_date = (
  SELECT date FROM business_days
  WHERE biz_row_num = (base_biz_row_num - 1)
)
```

**メリット:**
- 土日・祝日を自動スキップ
- 連休（GW、年末年始）も正しく処理
- calendar_dataの祝日マスタに依存

---

## 修正ファイル一覧

| ファイル | 修正内容 |
|---------|---------|
| `src/data_processing/dashboard_data_updater.py` | 期間を今日以降→7日前以降に変更 |
| `sql/create_prediction_accuracy_table.sql` | 予測精度検証テーブル作成SQL（新規） |
| `src/data_processing/ml_features_updater.py` | ml_features差分更新モジュール（新規） |
| `src/pipelines/main_etl.py` | Phase 7追加（dashboard_data_updater組み込み） |

---

## 次回セッション予定

### 実施予定タスク（優先順）

1. **ml_features_updater.pyコードレビュー**（継続中）
   - ユーザーレビュー待ち

2. **ml_features更新をmain_etl.pyに組み込み**
   - Phase 5として挿入（電力・天気投入後、予測実行前）

3. **prediction_accuracyインサートモジュール作成**
   - 実績確定後にprediction_results + energy_data_hourlyをJOINしてINSERT
   - 日次実行に組み込み

4. **予測精度の検証（手動確認）**
   - ml_features更新後に予測実行
   - 最新データでの予測精度確認

5. **予測モジュールの日別実行対応（基準日指定機能追加）**

6. **予測精度向上（特徴量・モデル改善）**

7. **Looker Studio監視ページ実装**

8. **Looker Studio予測結果表示ダッシュボード作成**

---

## TODOリスト

### 完了済み
- [x] dashboard_data_updater.pyを7日前以降に修正
- [x] main_etl.pyにdashboard_data_updater組み込み
- [x] ml_features差分更新モジュール作成（MERGE方式）

### 未完了
- [ ] ml_features_updater.pyコードレビュー（進行中）
- [ ] ml_features更新をmain_etl.pyに組み込み
- [ ] prediction_accuracyインサートモジュール作成
- [ ] 予測精度の検証（手動確認）
- [ ] 予測モジュールの日別実行対応（基準日指定機能追加）
- [ ] 予測精度向上（特徴量・モデル改善）
- [ ] Looker Studio監視ページ実装（BigQueryビュー作成 → Looker Studio接続）
- [ ] Looker Studio予測結果表示ダッシュボード作成

---

## 備考

### 今回のセッションで学んだこと

**1. データ反映タイミングの重要性**
- 昨日の実績は今日のETLで投入される
- 更新範囲を「今日以降」にすると昨日の実績が漏れる
- **「7日前以降」で余裕を持って更新**

**2. BigQueryのコスト最適化**
- UPDATEは高コスト（パーティション全体書き直し）
- 追記型（INSERT）が推奨
- 差分更新はDELETE + INSERTで実現

**3. テーブル設計の工夫**
- `days_ahead`よりも`prediction_run_date`の方が直感的
- 両方持つことで柔軟な分析が可能
- カラム名は「何日後」の方がわかりやすい（0=当日）

**4. 営業日計算の実装**
- ROW_NUMBER()を使った連番付与
- date_lag_mappingテーブルで事前計算
- カレンダーマスタへの依存で祝日も自動対応

### 日次パイプラインの進化

**現在の構成（Phase 1-7）:**
1. 電力データ取得・投入
2. 気象データ取得・投入
3. データ品質チェック
4. 予測実行
5. ダッシュボードデータ更新

**次回追加予定（Phase 5としてml_features更新）:**
1. 電力データ取得・投入
2. 気象データ取得・投入
3. **ml_features更新** ← NEW!
4. データ品質チェック
5. 予測実行
6. ダッシュボードデータ更新

**さらに追加予定（prediction_accuracy更新）:**
- 予測実行後にprediction_accuracy更新
- 実績確定後の精度計算

### prediction_accuracyの活用方法

**1. 日数別精度分析:**
```sql
SELECT
  days_ahead,
  AVG(error_percentage) as avg_mape
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
WHERE days_ahead <= 7
GROUP BY prediction_hour
ORDER BY prediction_hour
```

**3. トレンド分析:**
```sql
SELECT
  prediction_run_date,
  AVG(error_percentage) as avg_mape
FROM prediction_accuracy
WHERE days_ahead = 1  -- 1日後の予測のみ
GROUP BY prediction_run_date
ORDER BY prediction_run_date
```
