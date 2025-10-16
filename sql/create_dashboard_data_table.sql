-- Looker Studio用ダッシュボードデータテーブル
-- 実績電力・予測電力・天気データ・カレンダー情報を統合したマテリアライズドテーブル

CREATE TABLE IF NOT EXISTS `prod_energy_data.dashboard_data` (
  -- 日時情報
  date DATE NOT NULL,
  hour INTEGER NOT NULL,

  -- 電力データ
  actual_power FLOAT64,
  supply_capacity FLOAT64,
  predicted_power FLOAT64,

  -- 誤差データ（計算値）
  error_absolute FLOAT64,
  error_percentage FLOAT64,

  -- 天気データ
  temperature_2m FLOAT64,
  relative_humidity_2m FLOAT64,
  precipitation FLOAT64,
  weather_code INTEGER,

  -- カレンダー情報
  day_of_week STRING,
  is_weekend BOOLEAN,
  is_holiday BOOLEAN,

  -- 計算値
  usage_rate FLOAT64,
  weekday_jp STRING,

  -- メタデータ
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY date
CLUSTER BY hour
OPTIONS (
  description = 'Looker Studio用ダッシュボードデータ（実績+予測+天気+カレンダー統合）',
  partition_expiration_days = 1095,  -- 3年間保持
  require_partition_filter = FALSE
);
