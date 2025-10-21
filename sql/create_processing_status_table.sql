-- Phase 11: プロセス実行履歴テーブル作成
-- 目的: API取得・BQ処理・ML予測を個別プロセスとして記録・監視
-- 作成日: 2025-09-26

CREATE OR REPLACE TABLE `energy-env.prod_energy_data.process_execution_log` (
  execution_id STRING NOT NULL,              -- UUID（各プロセス実行の一意識別子）
  date DATE NOT NULL,                        -- 対象データの日付
  process_type STRING NOT NULL,              -- 'TEPCO_API', 'WEATHER_API', 'BQ_PROCESSING', 'ML_PREDICTION'
  status STRING NOT NULL,                    -- 'SUCCESS', 'FAILED'
  error_message STRING,                      -- エラーメッセージ（成功時はNULL）
  started_at DATETIME NOT NULL,              -- プロセス開始時刻
  completed_at DATETIME,                     -- プロセス完了時刻（実行中はNULL）
  duration_seconds FLOAT64,                  -- 処理時間（秒、小数点以下含む）
  records_processed INT,                     -- 処理レコード数
  file_size_mb FLOAT64,                        -- ファイルサイズ（MB、API_DOWNLOADのみ）
  additional_info JSON                       -- プロセス固有の追加情報
)
PARTITION BY date
OPTIONS (
  description = "Phase 11: プロセス別実行履歴管理テーブル - API取得、BQ処理、ML予測の個別追跡",
  partition_expiration_days = 1095  -- 3年間保持
);

