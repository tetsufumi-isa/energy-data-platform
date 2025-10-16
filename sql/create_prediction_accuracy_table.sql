-- 予測精度検証テーブル
-- 予測値と実績値を紐付けて精度分析を行うためのテーブル

CREATE TABLE IF NOT EXISTS `prod_energy_data.prediction_accuracy` (
  -- 予測実行情報
  execution_id STRING NOT NULL,        -- 実行ID（process_execution_logと紐付け）
  prediction_run_date DATE NOT NULL,   -- 予測実行日（いつ予測したか）

  -- 予測対象情報
  prediction_date DATE NOT NULL,       -- 予測対象日
  prediction_hour INT64 NOT NULL,      -- 予測対象時間（0-23）

  -- 予測値・実績値
  predicted_power FLOAT64 NOT NULL,    -- 予測電力量（kWh）
  actual_power FLOAT64 NOT NULL,       -- 実績電力量（kWh）

  -- 誤差計算（保存時に計算）
  error_absolute FLOAT64,              -- 絶対誤差（|予測 - 実績|）
  error_percentage FLOAT64,            -- 誤差率（%）

  -- 予測期間
  days_ahead INT64,                    -- 何日後の予測か（0～13: 0=当日、1=翌日、...、13=13日後）

  -- メタデータ
  created_at TIMESTAMP NOT NULL        -- レコード作成日時
)
PARTITION BY prediction_date
CLUSTER BY prediction_run_date, days_ahead
OPTIONS(
  description = '予測精度検証テーブル（予測値vs実績値）',
  labels = [("env", "production"), ("data_type", "accuracy")],
  partition_expiration_days = 1095    -- 3年間保持
);
