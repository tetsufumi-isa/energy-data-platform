{{
  config(
    materialized='incremental',
    incremental_strategy='insert_overwrite',
    partition_by={
      "field": "date",
      "data_type": "date",
      "granularity": "day"
    }
  )
}}

-- incremental_strategy='insert_overwrite'
-- パーティション単位で削除→挿入（洗い替え）を行う
-- Python版のDELETE→INSERTと同等の動作

-- ML用特徴量テーブル
-- 電力・天気・カレンダーデータを統合し、lag特徴量を計算

WITH energy_filtered AS (
  -- lag特徴量計算のため20日分取得
  SELECT
    date,
    hour,
    actual_power,
    supply_capacity
  FROM {{ source('energy_data', 'energy_data_hourly') }}
  {% if is_incremental() %}
  WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 20 DAY)
  {% endif %}
),

weather_filtered AS (
  -- 天気データは7日分でOK
  SELECT
    date,
    hour,
    temperature_2m,
    relative_humidity_2m,
    precipitation,
    weather_code
  FROM {{ source('energy_data', 'weather_data') }}
  WHERE prefecture = '千葉県'
  {% if is_incremental() %}
    AND date >= DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 7 DAY)
  {% endif %}
),

calendar_filtered AS (
  -- カレンダーデータ
  SELECT
    date,
    day_of_week,
    is_weekend,
    is_holiday
  FROM {{ source('energy_data', 'calendar_data') }}
  {% if is_incremental() %}
  WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 7 DAY)
  {% endif %}
),

lag_mapping_filtered AS (
  -- lag日付マッピング
  SELECT
    base_date,
    lag_1_day_date,
    lag_7_day_date,
    lag_1_business_date
  FROM {{ source('energy_data', 'date_lag_mapping') }}
  {% if is_incremental() %}
  WHERE base_date >= DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 7 DAY)
  {% endif %}
),

energy_with_lag AS (
  -- 電力データにlag特徴量を追加
  SELECT
    energy.date,
    energy.hour,
    energy.actual_power,
    energy.supply_capacity,
    lag1.actual_power AS lag_1_day,
    lag7.actual_power AS lag_7_day,
    blag1.actual_power AS lag_1_business_day
  FROM energy_filtered energy
  LEFT JOIN lag_mapping_filtered dlm
    ON energy.date = dlm.base_date
  LEFT JOIN energy_filtered lag1
    ON lag1.date = dlm.lag_1_day_date AND lag1.hour = energy.hour
  LEFT JOIN energy_filtered lag7
    ON lag7.date = dlm.lag_7_day_date AND lag7.hour = energy.hour
  LEFT JOIN energy_filtered blag1
    ON blag1.date = dlm.lag_1_business_date AND blag1.hour = energy.hour
),

base_data AS (
  -- 電力+lag特徴量に天気・カレンダーをjoin
  SELECT
    energy.date,
    energy.hour,
    energy.actual_power,
    energy.supply_capacity,
    energy.lag_1_day,
    energy.lag_7_day,
    energy.lag_1_business_day,
    weather.temperature_2m,
    weather.relative_humidity_2m,
    weather.precipitation,
    weather.weather_code,
    calendar.day_of_week,
    calendar.is_weekend,
    calendar.is_holiday,
    EXTRACT(MONTH FROM energy.date) AS month
  FROM energy_with_lag energy
  LEFT JOIN weather_filtered weather
    ON energy.date = weather.date
    AND energy.hour = CAST(weather.hour AS INT64)
  LEFT JOIN calendar_filtered calendar
    ON energy.date = calendar.date
  {% if is_incremental() %}
  WHERE energy.date >= DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 7 DAY)
  {% endif %}
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
  SIN(2 * 3.141592653589793 * base.hour / 24) AS hour_sin,
  COS(2 * 3.141592653589793 * base.hour / 24) AS hour_cos,

  -- lag特徴量
  base.lag_1_day,
  base.lag_7_day,
  base.lag_1_business_day

FROM base_data base