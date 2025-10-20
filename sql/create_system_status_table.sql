-- システム監視ステータステーブル
-- 目的: Looker Studio監視ページで最新のシステム状態を即座に表示
-- 特徴: 常に最新1レコードのみ保持（全削除→再投入方式）

CREATE OR REPLACE TABLE `prod_energy_data.system_status` (
  -- 更新情報
  updated_at DATETIME NOT NULL,

  -- 各プロセスのステータス（OK/ERROR/WARNING）
  tepco_api_status STRING NOT NULL,
  weather_api_status STRING NOT NULL,
  bigquery_process_status STRING NOT NULL,
  ml_prediction_status STRING NOT NULL,
  data_quality_status STRING NOT NULL,

  -- 各項目の詳細情報（エラーメッセージなど）
  tepco_api_message STRING,
  weather_api_message STRING,
  bigquery_process_message STRING,
  ml_prediction_message STRING,
  data_quality_message STRING
)
OPTIONS(
  description = 'システム監視ステータステーブル（最新1レコードのみ保持）',
  labels = [("env", "production"), ("data_type", "monitoring")]
);
