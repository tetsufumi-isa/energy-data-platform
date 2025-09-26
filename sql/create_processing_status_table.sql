-- Phase 11: プロセス実行履歴テーブル作成
-- 目的: API取得・BQ処理・ML予測を個別プロセスとして記録・監視
-- 作成日: 2025-09-26

CREATE TABLE IF NOT EXISTS `energy-env.prod_energy_data.process_execution_log` (
  execution_id STRING NOT NULL,              -- UUID（各プロセス実行の一意識別子）
  date DATE NOT NULL,                        -- 対象データの日付
  process_type STRING NOT NULL,              -- 'TEPCO_API', 'WEATHER_API', 'BQ_PROCESSING', 'ML_PREDICTION'
  status STRING NOT NULL,                    -- 'SUCCESS', 'FAILED'
  error_message STRING,                      -- エラーメッセージ（成功時はNULL）
  started_at TIMESTAMP NOT NULL,             -- プロセス開始時刻
  completed_at TIMESTAMP,                    -- プロセス完了時刻（実行中はNULL）
  duration_seconds INT,                      -- 処理時間（秒）
  records_processed INT,                     -- 処理レコード数
  file_size_mb FLOAT64,                        -- ファイルサイズ（MB、API_DOWNLOADのみ）
  additional_info JSON                       -- プロセス固有の追加情報
)
PARTITION BY date
OPTIONS (
  description = "Phase 11: プロセス別実行履歴管理テーブル - API取得、BQ処理、ML予測の個別追跡",
  partition_expiration_days = 1095  -- 3年間保持
);

-- データ異常検知結果テーブル（独立管理）
CREATE TABLE IF NOT EXISTS `energy-env.prod_energy_data.data_anomaly_log` (
  anomaly_id STRING NOT NULL,                -- UUID
  date DATE NOT NULL,                        -- 対象データの日付
  anomaly_type STRING NOT NULL,              -- 'MISSING_DATA', 'OUTLIER', 'PATTERN_BREAK'
  severity STRING NOT NULL,                  -- 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'
  affected_records INT,                      -- 影響を受けたレコード数
  detected_at TIMESTAMP NOT NULL
)
PARTITION BY date
OPTIONS (
  description = "Phase 11: データ異常検知結果管理テーブル",
  partition_expiration_days = 1095  -- 3年間保持
);

-- Looker Studio用：日次処理サマリービュー
CREATE OR REPLACE VIEW `energy-env.prod_energy_data.daily_process_summary` AS
WITH latest_executions AS (
  -- 各日付・プロセスタイプの最新実行を取得
  SELECT
    date,
    process_type,
    status,
    error_message,
    started_at,
    completed_at,
    duration_seconds,
    records_processed,
    file_size_mb,
    ROW_NUMBER() OVER (
      PARTITION BY date, process_type
      ORDER BY started_at DESC
    ) as rn
  FROM `energy-env.prod_energy_data.process_execution_log`
),
pivot_data AS (
  SELECT
    date,
    MAX(CASE WHEN process_type = 'TEPCO_API' THEN status END) as tepco_api_status,
    MAX(CASE WHEN process_type = 'TEPCO_API' THEN error_message END) as tepco_api_error,
    MAX(CASE WHEN process_type = 'TEPCO_API' THEN duration_seconds END) as tepco_api_duration,
    MAX(CASE WHEN process_type = 'TEPCO_API' THEN file_size_mb END) as tepco_api_file_size,

    MAX(CASE WHEN process_type = 'WEATHER_API' THEN status END) as weather_api_status,
    MAX(CASE WHEN process_type = 'WEATHER_API' THEN error_message END) as weather_api_error,
    MAX(CASE WHEN process_type = 'WEATHER_API' THEN duration_seconds END) as weather_api_duration,
    MAX(CASE WHEN process_type = 'WEATHER_API' THEN file_size_mb END) as weather_api_file_size,

    MAX(CASE WHEN process_type = 'BQ_PROCESSING' THEN status END) as bq_status,
    MAX(CASE WHEN process_type = 'BQ_PROCESSING' THEN error_message END) as bq_error,
    MAX(CASE WHEN process_type = 'BQ_PROCESSING' THEN duration_seconds END) as bq_duration,
    MAX(CASE WHEN process_type = 'BQ_PROCESSING' THEN records_processed END) as bq_records,

    MAX(CASE WHEN process_type = 'ML_PREDICTION' THEN status END) as ml_status,
    MAX(CASE WHEN process_type = 'ML_PREDICTION' THEN error_message END) as ml_error,
    MAX(CASE WHEN process_type = 'ML_PREDICTION' THEN duration_seconds END) as ml_duration,
    MAX(CASE WHEN process_type = 'ML_PREDICTION' THEN records_processed END) as ml_records

  FROM latest_executions
  WHERE rn = 1
  GROUP BY date
),
anomaly_summary AS (
  SELECT
    date,
    COUNT(*) as total_anomaly_count,
    MAX(severity) as max_severity,
    MAX(CASE WHEN anomaly_type = 'MISSING_DATA' THEN affected_records END) as missing_data_records,
    MAX(CASE WHEN anomaly_type = 'OUTLIER' THEN affected_records END) as outlier_records,
    MAX(CASE WHEN anomaly_type = 'PATTERN_BREAK' THEN affected_records END) as pattern_break_records
  FROM `energy-env.prod_energy_data.data_anomaly_log`
  GROUP BY date
)
SELECT
  p.date,

  -- 全体ステータス判定
  CASE
    WHEN p.tepco_api_status = 'SUCCESS' AND p.weather_api_status = 'SUCCESS' AND p.bq_status = 'SUCCESS' AND p.ml_status = 'SUCCESS'
    THEN 'SUCCESS'
    WHEN p.tepco_api_status = 'FAILED' OR p.weather_api_status = 'FAILED' OR p.bq_status = 'FAILED' OR p.ml_status = 'FAILED'
    THEN 'FAILED'
    ELSE 'PARTIAL'
  END as overall_status,

  -- 個別プロセスステータス
  p.tepco_api_status,
  p.tepco_api_error,
  p.tepco_api_duration,
  p.tepco_api_file_size,

  p.weather_api_status,
  p.weather_api_error,
  p.weather_api_duration,
  p.weather_api_file_size,

  p.bq_status,
  p.bq_error,
  p.bq_duration,
  p.bq_records,

  p.ml_status,
  p.ml_error,
  p.ml_duration,
  p.ml_records,

  -- データ異常情報
  COALESCE(a.total_anomaly_count, 0) as total_anomaly_count,
  a.max_severity,
  COALESCE(a.missing_data_records, 0) as missing_data_records,
  COALESCE(a.outlier_records, 0) as outlier_records,
  COALESCE(a.pattern_break_records, 0) as pattern_break_records

FROM pivot_data p
LEFT JOIN anomaly_summary a ON p.date = a.date
ORDER BY p.date DESC;

