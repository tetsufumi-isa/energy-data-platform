-- date_lag_mappingテーブル作成（2023-2027）
-- 目的: 実日・営業日ベースのlag日付マッピングテーブル
-- 用途: ml_featuresビューでlag特徴量を効率的に取得

CREATE OR REPLACE TABLE `energy-env.prod_energy_data.date_lag_mapping` AS
WITH calendar AS (
  SELECT
    date,
    is_holiday,
    is_weekend
  FROM `energy-env.prod_energy_data.calendar_data`
),
business_days AS (
  -- 営業日のみ抽出して連番付与
  SELECT
    date,
    ROW_NUMBER() OVER (ORDER BY date) as biz_row_num
  FROM calendar
  WHERE NOT is_holiday AND NOT is_weekend
),
all_dates AS (
  SELECT
    c.date as base_date,
    bd.biz_row_num as base_biz_row_num
  FROM calendar c
  LEFT JOIN business_days bd ON c.date = bd.date
)
SELECT
  ad.base_date,

  -- 実日ベースlag（1～30日前）
  DATE_SUB(ad.base_date, INTERVAL 1 DAY) as lag_1_day_date,
  DATE_SUB(ad.base_date, INTERVAL 2 DAY) as lag_2_day_date,
  DATE_SUB(ad.base_date, INTERVAL 3 DAY) as lag_3_day_date,
  DATE_SUB(ad.base_date, INTERVAL 4 DAY) as lag_4_day_date,
  DATE_SUB(ad.base_date, INTERVAL 5 DAY) as lag_5_day_date,
  DATE_SUB(ad.base_date, INTERVAL 6 DAY) as lag_6_day_date,
  DATE_SUB(ad.base_date, INTERVAL 7 DAY) as lag_7_day_date,
  DATE_SUB(ad.base_date, INTERVAL 8 DAY) as lag_8_day_date,
  DATE_SUB(ad.base_date, INTERVAL 9 DAY) as lag_9_day_date,
  DATE_SUB(ad.base_date, INTERVAL 10 DAY) as lag_10_day_date,
  DATE_SUB(ad.base_date, INTERVAL 11 DAY) as lag_11_day_date,
  DATE_SUB(ad.base_date, INTERVAL 12 DAY) as lag_12_day_date,
  DATE_SUB(ad.base_date, INTERVAL 13 DAY) as lag_13_day_date,
  DATE_SUB(ad.base_date, INTERVAL 14 DAY) as lag_14_day_date,
  DATE_SUB(ad.base_date, INTERVAL 15 DAY) as lag_15_day_date,
  DATE_SUB(ad.base_date, INTERVAL 16 DAY) as lag_16_day_date,
  DATE_SUB(ad.base_date, INTERVAL 17 DAY) as lag_17_day_date,
  DATE_SUB(ad.base_date, INTERVAL 18 DAY) as lag_18_day_date,
  DATE_SUB(ad.base_date, INTERVAL 19 DAY) as lag_19_day_date,
  DATE_SUB(ad.base_date, INTERVAL 20 DAY) as lag_20_day_date,
  DATE_SUB(ad.base_date, INTERVAL 21 DAY) as lag_21_day_date,
  DATE_SUB(ad.base_date, INTERVAL 22 DAY) as lag_22_day_date,
  DATE_SUB(ad.base_date, INTERVAL 23 DAY) as lag_23_day_date,
  DATE_SUB(ad.base_date, INTERVAL 24 DAY) as lag_24_day_date,
  DATE_SUB(ad.base_date, INTERVAL 25 DAY) as lag_25_day_date,
  DATE_SUB(ad.base_date, INTERVAL 26 DAY) as lag_26_day_date,
  DATE_SUB(ad.base_date, INTERVAL 27 DAY) as lag_27_day_date,
  DATE_SUB(ad.base_date, INTERVAL 28 DAY) as lag_28_day_date,
  DATE_SUB(ad.base_date, INTERVAL 29 DAY) as lag_29_day_date,
  DATE_SUB(ad.base_date, INTERVAL 30 DAY) as lag_30_day_date,

  -- 営業日ベースlag（1～30営業日前）
  (SELECT date FROM business_days WHERE biz_row_num = ad.base_biz_row_num - 1) as lag_1_business_date,
  (SELECT date FROM business_days WHERE biz_row_num = ad.base_biz_row_num - 2) as lag_2_business_date,
  (SELECT date FROM business_days WHERE biz_row_num = ad.base_biz_row_num - 3) as lag_3_business_date,
  (SELECT date FROM business_days WHERE biz_row_num = ad.base_biz_row_num - 4) as lag_4_business_date,
  (SELECT date FROM business_days WHERE biz_row_num = ad.base_biz_row_num - 5) as lag_5_business_date,
  (SELECT date FROM business_days WHERE biz_row_num = ad.base_biz_row_num - 6) as lag_6_business_date,
  (SELECT date FROM business_days WHERE biz_row_num = ad.base_biz_row_num - 7) as lag_7_business_date,
  (SELECT date FROM business_days WHERE biz_row_num = ad.base_biz_row_num - 8) as lag_8_business_date,
  (SELECT date FROM business_days WHERE biz_row_num = ad.base_biz_row_num - 9) as lag_9_business_date,
  (SELECT date FROM business_days WHERE biz_row_num = ad.base_biz_row_num - 10) as lag_10_business_date,
  (SELECT date FROM business_days WHERE biz_row_num = ad.base_biz_row_num - 11) as lag_11_business_date,
  (SELECT date FROM business_days WHERE biz_row_num = ad.base_biz_row_num - 12) as lag_12_business_date,
  (SELECT date FROM business_days WHERE biz_row_num = ad.base_biz_row_num - 13) as lag_13_business_date,
  (SELECT date FROM business_days WHERE biz_row_num = ad.base_biz_row_num - 14) as lag_14_business_date,
  (SELECT date FROM business_days WHERE biz_row_num = ad.base_biz_row_num - 15) as lag_15_business_date,
  (SELECT date FROM business_days WHERE biz_row_num = ad.base_biz_row_num - 16) as lag_16_business_date,
  (SELECT date FROM business_days WHERE biz_row_num = ad.base_biz_row_num - 17) as lag_17_business_date,
  (SELECT date FROM business_days WHERE biz_row_num = ad.base_biz_row_num - 18) as lag_18_business_date,
  (SELECT date FROM business_days WHERE biz_row_num = ad.base_biz_row_num - 19) as lag_19_business_date,
  (SELECT date FROM business_days WHERE biz_row_num = ad.base_biz_row_num - 20) as lag_20_business_date,
  (SELECT date FROM business_days WHERE biz_row_num = ad.base_biz_row_num - 21) as lag_21_business_date,
  (SELECT date FROM business_days WHERE biz_row_num = ad.base_biz_row_num - 22) as lag_22_business_date,
  (SELECT date FROM business_days WHERE biz_row_num = ad.base_biz_row_num - 23) as lag_23_business_date,
  (SELECT date FROM business_days WHERE biz_row_num = ad.base_biz_row_num - 24) as lag_24_business_date,
  (SELECT date FROM business_days WHERE biz_row_num = ad.base_biz_row_num - 25) as lag_25_business_date,
  (SELECT date FROM business_days WHERE biz_row_num = ad.base_biz_row_num - 26) as lag_26_business_date,
  (SELECT date FROM business_days WHERE biz_row_num = ad.base_biz_row_num - 27) as lag_27_business_date,
  (SELECT date FROM business_days WHERE biz_row_num = ad.base_biz_row_num - 28) as lag_28_business_date,
  (SELECT date FROM business_days WHERE biz_row_num = ad.base_biz_row_num - 29) as lag_29_business_date,
  (SELECT date FROM business_days WHERE biz_row_num = ad.base_biz_row_num - 30) as lag_30_business_date

FROM all_dates ad
ORDER BY ad.base_date;