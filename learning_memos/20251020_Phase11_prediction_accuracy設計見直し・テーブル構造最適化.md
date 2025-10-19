# Phase 11 進捗記録: prediction_accuracy設計見直し・テーブル構造最適化

**日付**: 2025-10-20
**Phase**: 11 - 基盤整備フェーズ
**ステータス**: prediction_accuracyテーブル設計最適化完了

---

## セッション概要

prediction_accuracyテーブルの問題点を発見し、テーブル構造とパーティション設計を根本から見直し。予測実行日時の管理方法を改善し、より効率的で分析しやすい設計に最適化。

---

## 主要成果

### 1. prediction_accuracyの問題点を発見

**ユーザーからの指摘**:
- ✅ created_atが全部同一で、いつの予測か判別しづらい
- ✅ prediction_run_dateが同じで同じ予測が複数ある
- ✅ days_aheadがマイナスになっている

**原因分析**:

1. **created_atの問題**（136行目）:
```sql
-- 問題のあるコード
CURRENT_DATETIME('Asia/Tokyo') AS created_at
```
- updater実行時刻になってしまう
- 本来は予測実行時刻を記録すべき

2. **prediction_run_dateの問題**（108行目）:
```sql
-- 問題のあるコード
DATE(created_at) AS prediction_run_date
```
- DATETIME → DATEに変換して時刻情報を喪失
- 同じ日に複数回予測した場合、区別できない

3. **days_aheadのマイナス問題**:
- 過去7日分を削除→再投入する際、古い予測も含まれる
- 過去の予測と最新の実績を比較するとマイナスになる

### 2. テーブル構造の最適化設計

**旧設計の問題**:
```sql
-- 問題のある設計
PARTITION BY prediction_date       -- 予測対象日
CLUSTER BY prediction_run_date     -- 予測実行日（DATE型）
created_at DATETIME                -- 不正確な時刻
```

**新設計（最適化版）**:
```sql
-- 最適化された設計
PARTITION BY prediction_run_date         -- 予測実行日（いつ予測したか）
CLUSTER BY prediction_date, prediction_hour  -- 予測対象（何を予測したか）

-- カラム構成
prediction_run_date DATE              -- 予測実行日（パーティション用）
prediction_run_datetime DATETIME      -- 予測実行日時（詳細時刻）
-- created_at削除（不要）
```

**設計の利点**:
1. **パーティション最適化**: 「10/15に実行した全予測」が1パーティションにまとまる
2. **クラスタリング最適化**: 予測対象でソートされ、分析クエリが高速化
3. **データの正確性**: 予測実行の正確な日時が保持される

### 3. テーブル定義の修正

**ファイル**: `sql/create_prediction_accuracy_table.sql`

```sql
-- 既存テーブルがあれば削除
DROP TABLE IF EXISTS `prod_energy_data.prediction_accuracy`;

-- テーブル作成
CREATE TABLE `prod_energy_data.prediction_accuracy` (
  -- 予測実行情報
  execution_id STRING NOT NULL,
  prediction_run_date DATE NOT NULL,         -- パーティション用
  prediction_run_datetime DATETIME NOT NULL, -- 詳細時刻

  -- 予測対象情報
  prediction_date DATE NOT NULL,
  prediction_hour INT64 NOT NULL,

  -- 予測値・実績値
  predicted_power FLOAT64 NOT NULL,
  actual_power FLOAT64 NOT NULL,

  -- 誤差計算
  error_absolute FLOAT64,
  error_percentage FLOAT64,

  -- 予測期間
  days_ahead INT64
)
PARTITION BY prediction_run_date
CLUSTER BY prediction_date, prediction_hour
OPTIONS(
  description = '予測精度検証テーブル（予測値vs実績値）',
  labels = [("env", "production"), ("data_type", "accuracy")],
  partition_expiration_days = 1095
);
```

### 4. updaterモジュールの修正

**ファイル**: `src/data_processing/prediction_accuracy_updater.py`

**修正1: DELETE文の条件変更**（64-65行目）:
```python
# 修正前
WHERE prediction_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)

# 修正後
WHERE prediction_run_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
```

**修正2: INSERT文のカラム追加**（93-141行目）:
```sql
WITH prediction_filtered AS (
  SELECT
    execution_id,
    CAST(created_at AS DATE) AS prediction_run_date,      -- 追加
    created_at AS prediction_run_datetime,                 -- 追加
    prediction_date,
    prediction_hour,
    predicted_power_kwh AS predicted_power
  FROM prediction_results
  ...
)
SELECT
  pred.execution_id,
  pred.prediction_run_date,          -- 追加
  pred.prediction_run_datetime,      -- 追加
  pred.prediction_date,
  pred.prediction_hour,
  pred.predicted_power,
  energy.actual_power,
  ABS(pred.predicted_power - energy.actual_power) AS error_absolute,
  ABS(pred.predicted_power - energy.actual_power) / NULLIF(energy.actual_power, 0) * 100 AS error_percentage,
  DATE_DIFF(pred.prediction_date, pred.prediction_run_date, DAY) AS days_ahead
  -- created_at削除
FROM prediction_filtered pred
INNER JOIN energy_filtered energy
  ON pred.prediction_date = energy.date
  AND pred.prediction_hour = energy.hour
```

**修正3: 削除期間を14日に延長**（64行目）:
```python
# 理由: 予測期間が14日間のため、過去14日分を削除→再投入する必要がある
DELETE FROM prediction_accuracy
WHERE prediction_run_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
```

### 5. 動作確認

**実行結果**:
```
prediction_accuracy更新システム開始
PredictionAccuracyUpdater初期化完了: energy-env
prediction_accuracy更新開始: execution_id=474281d2-6e66-41ac-acdb-7f89c21254ec
過去14日分のデータ削除完了: 0行削除
prediction_accuracyデータ投入完了: 528行
prediction_accuracy更新完了: 削除0行, 挿入528行

処理結果: 成功
削除レコード数: 0
挿入レコード数: 528
```

✅ 新テーブル構造で正常に動作

---

## 技術的理解の向上

### 予測と保存タイミングの整理

**10/15に予測実行した場合**:
- 予測期間: 10/15（当日）〜 10/28（13日後）= 14日分
- 各日24時間 = 336行の予測

**prediction_accuracyへの保存タイミング**:
```
10/15に予測実行（10/15～10/28の予測）

・10/15 → 保存なし（10/15の実績がまだ確定していない）
・10/16 → 10/15分を保存（10/15の実績が確定）
・10/17 → 10/15,16分を保存（10/16の実績が確定）
・10/18 → 10/15,16,17分を保存（10/17の実績が確定）
...
・10/29 → 10/15,16,...,28分を保存（全期間の実績が確定）
```

**重要なポイント**:
- 当日の実績は翌日にならないと確定しない
- `WHERE prediction_date < CURRENT_DATE`で今日を除外
- 日々、過去の予測精度が蓄積されていく

### 削除期間を14日にした理由

**問題**:
- 予測期間が14日間
- 7日分しか削除していなかった場合、古いデータが残る

**例**:
```
10/15の予測（10/15〜10/28対象）

7日削除の場合:
- 10/22まで: 削除→再投入される ✅
- 10/23以降: 削除されない！古いデータが残る ❌

14日削除の場合:
- 10/29まで: 削除→再投入される ✅
```

### データ量の見積もり

**1日あたりのデータ量**:
- 24時間 × 14日分 = 336行/実行
- 1日2〜3回実行 = 672〜1,008行/日

**3年間のデータ量**:
```
日数 = 365 × 3 = 1,095日
時間 = 24
予測期間 = 14
実行回数/日 = 3（朝・昼・夕）

総行数 = 1,095 × 24 × 14 × 3 = 1,103,760行

データサイズ（概算）:
1行 ≈ 100バイト
総サイズ ≈ 110MB
```

**結論**: BigQueryの無料枠（10GB）内で十分収まる

### BigQueryのPARTITION・CLUSTERの理解

**PARTITION**:
- データを物理的に分割（フォルダのようなイメージ）
- `prediction_run_date`でパーティション → 予測実行日ごとにデータ分割
- メリット: 特定の日の予測を高速検索、古いデータの削除が容易

**CLUSTER**:
- パーティション内のデータをソート
- `prediction_date, prediction_hour`でクラスタリング
- メリット: 予測対象でソートされ、分析クエリが高速化、スキャン量削減

**イメージ**:
```
パーティション（予測実行日ごとのフォルダ）
├── 2025-10-15/
│   └── データ（予測対象日・時間でソート済み）
├── 2025-10-16/
│   └── データ（予測対象日・時間でソート済み）
└── 2025-10-17/
    └── データ（予測対象日・時間でソート済み）
```

---

## 次回セッション予定

### 残りのタスク

1. **Looker Studio監視ページ実装**
2. **Looker Studio予測結果表示ダッシュボード作成**
3. **予測モジュールの日別実行対応実装**（argparse追加・基準日の変数化・テストモード分岐・精度評価機能追加）
4. **予測モジュールのテスト実行**（過去日で実行して精度確認）

---

## TODOリスト

### ✅ 完了
1. **prediction_accuracyテーブル構造修正**
   - created_at削除
   - prediction_run_date（DATE）とprediction_run_datetime（DATETIME）に分離
2. **prediction_accuracyテーブル再設計**
   - パーティション最適化（prediction_run_date）
   - クラスタリング最適化（prediction_date, prediction_hour）
3. **prediction_accuracy_updaterのSQL修正**
   - 新テーブル構造対応
   - 削除期間を14日に延長

### 🔲 未着手
4. **Looker Studio監視ページ実装**
5. **Looker Studio予測結果表示ダッシュボード作成**
6. **予測モジュールの日別実行対応実装**
7. **予測モジュールのテスト実行**

---

## 技術メモ

### 修正パターン例

**テーブル定義**:
```sql
-- 旧: prediction_run_date DATE, created_at DATETIME
-- 新: prediction_run_date DATE, prediction_run_datetime DATETIME

-- 旧: PARTITION BY prediction_date
-- 新: PARTITION BY prediction_run_date

-- 旧: CLUSTER BY prediction_run_date
-- 新: CLUSTER BY prediction_date, prediction_hour
```

**updater SQL**:
```sql
-- 旧: DATE(created_at) AS prediction_run_date
-- 新: CAST(created_at AS DATE) AS prediction_run_date
--     created_at AS prediction_run_datetime

-- 旧: CURRENT_DATETIME() AS created_at
-- 新: (削除)

-- 旧: WHERE prediction_date >= DATE_SUB(..., INTERVAL 7 DAY)
-- 新: WHERE prediction_run_date >= DATE_SUB(..., INTERVAL 14 DAY)
```

### 学んだこと

1. **時刻情報の重要性**: 予測実行の正確な時刻を保持することで、より詳細な分析が可能
2. **パーティション設計**: よく使う検索条件でパーティションを切ることで、クエリ性能とコストを最適化
3. **データライフサイクル**: 予測期間（14日）を考慮した削除期間の設定が重要

---

**次回アクション**: Looker Studio監視ページ実装、または予測結果表示ダッシュボード作成
