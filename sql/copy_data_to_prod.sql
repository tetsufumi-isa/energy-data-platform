-- dev環境から本番環境へデータコピー（パーティション + 3年保持）

-- 1. energy_data_hourly（電力データ）
DROP TABLE IF EXISTS `energy-env.prod_energy_data.energy_data_hourly`;

CREATE TABLE `energy-env.prod_energy_data.energy_data_hourly`
PARTITION BY date
OPTIONS(partition_expiration_days=1095)
AS SELECT * FROM `energy-env.dev_energy_data.energy_data_hourly`;

-- 2. weather_data（気象データ）
DROP TABLE IF EXISTS `energy-env.prod_energy_data.weather_data`;

CREATE TABLE `energy-env.prod_energy_data.weather_data`
PARTITION BY date
OPTIONS(partition_expiration_days=1095)
AS SELECT * FROM `energy-env.dev_energy_data.weather_data`;