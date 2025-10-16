-- 昨日までの全履歴データをdashboard_dataに一括投入（1回切り）
-- 実行前にテーブルが作成されている必要があります（create_dashboard_data_table.sql）

INSERT INTO `prod_energy_data.dashboard_data` (
  date,
  hour,
  actual_power,
  supply_capacity,
  predicted_power,
  error_absolute,
  error_percentage,
  temperature_2m,
  relative_humidity_2m,
  precipitation,
  weather_code,
  day_of_week,
  is_weekend,
  is_holiday,
  usage_rate,
  weekday_jp,
  created_at
)
WITH latest_predictions AS (
  -- 最新のexecution_idの予測データのみを取得
  SELECT
    prediction_date,
    prediction_hour,
    predicted_power_kwh,
    ROW_NUMBER() OVER (
      PARTITION BY prediction_date, prediction_hour
      ORDER BY created_at DESC
    ) as rn
  FROM `prod_energy_data.prediction_results`
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

  CURRENT_TIMESTAMP() AS created_at

FROM `prod_energy_data.energy_data_hourly` e

-- 天気データを結合（千葉県のデータ、hourをINTEGERにCASTして結合）
LEFT JOIN `prod_energy_data.weather_data` w
  ON e.date = w.date
  AND e.hour = CAST(w.hour AS INT64)
  AND w.prefecture = '千葉県'

-- カレンダー情報を結合
LEFT JOIN `prod_energy_data.calendar_data` c
  ON e.date = c.date

-- 最新の予測データを結合
LEFT JOIN latest_predictions p
  ON e.date = p.prediction_date
  AND e.hour = p.prediction_hour
  AND p.rn = 1

-- 昨日まで（今日は除外）
WHERE e.date < CURRENT_DATE('Asia/Tokyo')

ORDER BY e.date ASC, e.hour ASC;
