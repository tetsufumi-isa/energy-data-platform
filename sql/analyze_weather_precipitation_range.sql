-- precipitationの実データ範囲確認
-- プロジェクトID: energy-env
-- データセット: prod_energy_data

SELECT
  -- precipitationの統計
  MIN(precipitation) as precipitation_min,
  MAX(precipitation) as precipitation_max,
  AVG(precipitation) as precipitation_avg,
  APPROX_QUANTILES(precipitation, 100)[OFFSET(50)] as precipitation_median,
  APPROX_QUANTILES(precipitation, 100)[OFFSET(1)] as precipitation_p1,
  APPROX_QUANTILES(precipitation, 100)[OFFSET(95)] as precipitation_p95,
  APPROX_QUANTILES(precipitation, 100)[OFFSET(99)] as precipitation_p99,

  -- NULL件数
  COUNTIF(precipitation IS NULL) as precipitation_nulls,

  -- 現在のコードでの異常判定件数（負の値）
  COUNTIF(precipitation < 0) as precipitation_negative_count,

  -- データ件数
  COUNT(*) as total_records

FROM `energy-env.prod_energy_data.weather_data`
WHERE prefecture = '千葉県';
