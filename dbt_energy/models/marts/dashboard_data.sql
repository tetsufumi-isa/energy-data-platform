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

-- Looker Studio用ダッシュボードデータ
-- 電力・天気・カレンダー・予測データを統合

WITH latest_energy AS (
  -- 最新の電力データのみを取得（重複排除）
  SELECT
    date,
    hour,
    actual_power,
    supply_capacity,
    ROW_NUMBER() OVER (
      PARTITION BY date, hour
      ORDER BY created_at DESC
    ) AS rn
  FROM {{ source('energy_data', 'energy_data_hourly') }}
  {% if is_incremental() %}
  WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 7 DAY)
  {% endif %}
),

latest_weather AS (
  -- 最新の天気データのみを取得（重複排除）
  SELECT
    date,
    hour,
    temperature_2m,
    relative_humidity_2m,
    precipitation,
    weather_code,
    ROW_NUMBER() OVER (
      PARTITION BY date, hour
      ORDER BY created_at DESC
    ) AS rn
  FROM {{ source('energy_data', 'weather_data') }}
  WHERE prefecture = '千葉県'
  {% if is_incremental() %}
    AND date >= DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 7 DAY)
  {% endif %}
),

latest_predictions AS (
  -- 最新の予測データのみを取得
  SELECT
    prediction_date,
    prediction_hour,
    predicted_power_kwh,
    ROW_NUMBER() OVER (
      PARTITION BY prediction_date, prediction_hour
      ORDER BY created_at DESC
    ) AS rn
  FROM {{ source('energy_data', 'prediction_results') }}
  {% if is_incremental() %}
  WHERE prediction_date >= DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 7 DAY)
  {% endif %}
)

SELECT
  e.date,
  e.hour,
  e.actual_power,
  e.supply_capacity,
  p.predicted_power_kwh AS predicted_power,

  -- 誤差計算（予測データがある場合のみ）
  CASE
    WHEN p.predicted_power_kwh IS NOT NULL AND e.actual_power IS NOT NULL
    THEN ABS(p.predicted_power_kwh - e.actual_power)
    ELSE NULL
  END AS error_absolute,

  CASE
    WHEN p.predicted_power_kwh IS NOT NULL AND e.actual_power IS NOT NULL AND e.actual_power > 0
    THEN (ABS(p.predicted_power_kwh - e.actual_power) / e.actual_power) * 100
    ELSE NULL
  END AS error_percentage,

  -- 天気データ
  w.temperature_2m,
  w.relative_humidity_2m,
  w.precipitation,
  w.weather_code,

  -- カレンダー情報
  c.day_of_week,
  c.is_weekend,
  c.is_holiday,

  -- 使用率計算
  CASE
    WHEN e.supply_capacity > 0
    THEN ROUND((e.actual_power / e.supply_capacity) * 100, 1)
    ELSE NULL
  END AS usage_rate,

  -- 曜日日本語表記
  CASE c.day_of_week
    WHEN 'Monday' THEN '月'
    WHEN 'Tuesday' THEN '火'
    WHEN 'Wednesday' THEN '水'
    WHEN 'Thursday' THEN '木'
    WHEN 'Friday' THEN '金'
    WHEN 'Saturday' THEN '土'
    WHEN 'Sunday' THEN '日'
    ELSE NULL
  END AS weekday_jp,

  -- 作成日時
  CURRENT_DATETIME('Asia/Tokyo') AS created_at

FROM latest_energy e

-- 最新の天気データを結合（重複なし）
LEFT JOIN latest_weather w
  ON e.date = w.date
  AND e.hour = CAST(w.hour AS INT64)
  AND w.rn = 1

-- カレンダー情報を結合
LEFT JOIN {{ source('energy_data', 'calendar_data') }} c
  ON e.date = c.date

-- 最新の予測データを結合
LEFT JOIN latest_predictions p
  ON e.date = p.prediction_date
  AND e.hour = p.prediction_hour
  AND p.rn = 1

WHERE e.rn = 1