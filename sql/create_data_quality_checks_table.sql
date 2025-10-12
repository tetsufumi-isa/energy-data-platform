-- data_quality_checksテーブル作成（パーティション + 2年保持）
-- 目的: データ品質監視・異常検知結果の記録
-- 更新方針: 日次実行でチェック結果を追加

DROP TABLE IF EXISTS `energy-env.prod_energy_data.data_quality_checks`;

CREATE TABLE `energy-env.prod_energy_data.data_quality_checks` (
  check_date DATE,           -- チェック実行日
  check_timestamp TIMESTAMP, -- チェック実行時刻
  data_type STRING,          -- 'power' or 'weather'
  check_type STRING,         -- 'missing'（レコード欠損）, 'null'（NULL値）, 'outlier'（異常値）
  check_target STRING,       -- 対象カラム or '全体'
  issue_count INT64,         -- 異常件数
  issue_detail STRING,       -- 詳細メッセージ
  check_period_start DATE,   -- チェック対象期間開始
  check_period_end DATE,     -- チェック対象期間終了
  status STRING              -- 'OK', 'WARNING', 'ERROR'
)
PARTITION BY check_date
OPTIONS(
  partition_expiration_days=730,
  description='データ品質チェック結果（電力・気象データの異常検知）'
);
