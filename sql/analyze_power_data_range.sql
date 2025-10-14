-- actual_powerとsupply_capacityの実データ範囲確認
-- プロジェクトID: energy-env
-- データセット: prod_energy_data

SELECT
  -- actual_powerの統計
  MIN(actual_power) as actual_power_min,
  MAX(actual_power) as actual_power_max,
  AVG(actual_power) as actual_power_avg,
  APPROX_QUANTILES(actual_power, 100)[OFFSET(50)] as actual_power_median,
  APPROX_QUANTILES(actual_power, 100)[OFFSET(1)] as actual_power_p1,
  APPROX_QUANTILES(actual_power, 100)[OFFSET(99)] as actual_power_p99,

  -- supply_capacityの統計
  MIN(supply_capacity) as supply_capacity_min,
  MAX(supply_capacity) as supply_capacity_max,
  AVG(supply_capacity) as supply_capacity_avg,
  APPROX_QUANTILES(supply_capacity, 100)[OFFSET(50)] as supply_capacity_median,
  APPROX_QUANTILES(supply_capacity, 100)[OFFSET(1)] as supply_capacity_p1,
  APPROX_QUANTILES(supply_capacity, 100)[OFFSET(99)] as supply_capacity_p99,

  -- NULL件数
  COUNTIF(actual_power IS NULL) as actual_power_nulls,
  COUNTIF(supply_capacity IS NULL) as supply_capacity_nulls

FROM `energy-env.prod_energy_data.energy_data_hourly`;
