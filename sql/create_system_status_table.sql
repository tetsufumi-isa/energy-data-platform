-- システム監視ステータステーブル
-- 目的: Looker Studio監視ページで最新のシステム状態を即座に表示
-- 特徴: 常に最新1レコードのみ保持（全削除→再投入方式）

CREATE OR REPLACE TABLE `prod_energy_data.system_status` (
  -- 更新情報
  updated_at DATETIME NOT NULL,

  -- 各プロセスのステータス（OK/ERROR/WARNING）
  tepco_api_status STRING NOT NULL,
  weather_api_status STRING NOT NULL,
  ml_features_update_status STRING NOT NULL,
  ml_prediction_status STRING NOT NULL,
  prediction_accuracy_update_status STRING NOT NULL,
  data_quality_status STRING NOT NULL,
  dashboard_update_status STRING NOT NULL,

  -- 各項目の詳細情報（エラーメッセージなど）
  tepco_api_message STRING,
  weather_api_message STRING,
  ml_features_update_message STRING,
  ml_prediction_message STRING,
  prediction_accuracy_update_message STRING,
  data_quality_message STRING,
  dashboard_update_message STRING,

  -- 各プロセスの作業時間（秒、小数点以下含む）
  tepco_api_duration_seconds FLOAT64,
  weather_api_duration_seconds FLOAT64,
  ml_features_update_duration_seconds FLOAT64,
  ml_prediction_duration_seconds FLOAT64,
  prediction_accuracy_update_duration_seconds FLOAT64,
  data_quality_duration_seconds FLOAT64,
  dashboard_update_duration_seconds FLOAT64
)
OPTIONS(
  description = 'システム監視ステータステーブル（最新1レコードのみ保持）',
  labels = [("env", "production"), ("data_type", "monitoring")]
);
