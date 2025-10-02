-- prediction_results テーブル作成
-- 予測結果を保存するテーブル

CREATE TABLE IF NOT EXISTS `prod_energy_data.prediction_results` (
  execution_id STRING NOT NULL,        -- 実行ID（process_execution_logと紐付け）
  prediction_date DATE NOT NULL,       -- 予測対象日
  prediction_hour INT64 NOT NULL,      -- 予測対象時間（0-23）
  predicted_power_kwh FLOAT64 NOT NULL,-- 予測電力量（kWh）
  created_at TIMESTAMP NOT NULL        -- レコード作成日時
)
PARTITION BY prediction_date
CLUSTER BY execution_id, prediction_hour
OPTIONS(
  description = '機械学習モデルによる電力使用量予測結果テーブル',
  labels = [("env", "production"), ("data_type", "prediction")]
);
