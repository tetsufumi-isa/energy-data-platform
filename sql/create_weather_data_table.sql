-- weather_dataテーブル作成（パーティション + 3年保持）

DROP TABLE IF EXISTS `energy-env.prod_energy_data.weather_data`;

CREATE TABLE `energy-env.prod_energy_data.weather_data` (
  prefecture STRING,
  date DATE,
  hour STRING,
  temperature_2m FLOAT64,
  relative_humidity_2m FLOAT64,
  precipitation FLOAT64,
  weather_code INT64,
  created_at TIMESTAMP
)
PARTITION BY date
OPTIONS(
  partition_expiration_days=1095,
  description='気象データ（千葉県・時間別）- Open-Meteo API'
);
