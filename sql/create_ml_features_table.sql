-- ml_featuresテーブル作成（本番環境・パーティション + 3年保持）
-- 目的: 予測に必要な全特徴量を統合（電力・気象・カレンダー・lag特徴量）
-- 更新方針: 当月全置換（日次実行）

-- 既存テーブル削除
DROP TABLE IF EXISTS `energy-env.prod_energy_data.ml_features`;

-- テーブル作成
CREATE TABLE `energy-env.prod_energy_data.ml_features`
PARTITION BY date
OPTIONS(partition_expiration_days=1095)
AS
WITH base_data AS (
  SELECT
    energy.date,
    energy.hour,
    energy.actual_power,
    energy.supply_capacity,
    weather.temperature_2m,
    weather.relative_humidity_2m,
    weather.precipitation,
    weather.weather_code,
    calendar.day_of_week,
    calendar.is_weekend,
    calendar.is_holiday,
    EXTRACT(MONTH FROM energy.date) as month
  FROM `energy-env.prod_energy_data.energy_data_hourly` energy
  LEFT JOIN `energy-env.prod_energy_data.weather_data` weather
    ON energy.date = weather.date
    AND energy.hour = CAST(weather.hour AS INTEGER)
    AND weather.prefecture = 'chiba'
  LEFT JOIN `energy-env.prod_energy_data.calendar_data` calendar
    ON energy.date = calendar.date
)
SELECT
  base.date,
  base.hour,
  base.actual_power,
  base.supply_capacity,
  base.temperature_2m,
  base.relative_humidity_2m,
  base.precipitation,
  base.weather_code,
  base.day_of_week,
  base.is_weekend,
  base.is_holiday,
  base.month,

  -- 循環特徴量（時間の周期性）
  SIN(2 * 3.141592653589793 * base.hour / 24) as hour_sin,
  COS(2 * 3.141592653589793 * base.hour / 24) as hour_cos,

  -- lag特徴量（予測で使用する3つ）
  lag1.actual_power as lag_1_day,
  lag7.actual_power as lag_7_day,
  blag1.actual_power as lag_1_business_day

FROM base_data base
LEFT JOIN `energy-env.prod_energy_data.date_lag_mapping` dlm
  ON base.date = dlm.base_date
LEFT JOIN base_data lag1
  ON lag1.date = dlm.lag_1_day_date AND lag1.hour = base.hour
LEFT JOIN base_data lag7
  ON lag7.date = dlm.lag_7_day_date AND lag7.hour = base.hour
LEFT JOIN base_data blag1
  ON blag1.date = dlm.lag_1_business_date AND blag1.hour = base.hour;