# Phase 11 進捗記録: system_status監視テーブル・更新モジュール実装

**日付**: 2025-10-20
**Phase**: 11 - 基盤整備フェーズ
**ステータス**: system_status監視テーブル設計・updater実装完了（レビュー待ち）

---

## セッション概要

Looker Studio監視ページ用の`system_status`テーブルとその更新モジュール`system_status_updater.py`を実装。4つの監視項目（東電API・天気API・BQ処理・ML予測・データ品質）を1レコードで管理する設計を採用し、パフォーマンスとコストを最適化。

---

## 主要成果

### 1. system_statusテーブル設計

**目的**: Looker Studio監視ページで最新のシステム状態を即座に表示

**設計方針**:
- **1レコードテーブル**: 最新状態のみを保持（全削除→再投入方式）
- **集計不要**: ステータスを直接表示するだけ
- **パフォーマンス最適化**: 集計関数を使わず即座に表示可能
- **コスト削減**: BigQueryスキャン量を最小化

**テーブル構造**:
```sql
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
```

**監視項目（4つ）**:
1. 東電APIデータ取得
2. 天気APIデータ取得
3. BigQuery処理
4. 機械学習予測
5. データ品質チェック

### 2. system_status_updater.py実装

**ファイル**: `src/data_processing/system_status_updater.py`

**処理フロー**:
1. **全レコード削除**: `DELETE WHERE TRUE`
2. **最新ステータス投入**:
   - `process_execution_log`から各プロセスの最新ステータス取得
   - `data_quality_checks`から最新のデータ品質チェック結果取得
   - SUCCESS→OK, FAILED→ERROR, その他→WARNINGに変換
   - 1レコードに集約してINSERT

**ログ記録**:
- process_type: 'SYSTEM_STATUS_UPDATE'
- records_processed: 1（常に1レコード）
- status: SUCCESS/FAILED（クエリ実行の成否のみ）

**主要メソッド**:
```python
class SystemStatusUpdater:
    def delete_all_records(self):
        """全レコード削除"""

    def insert_latest_status(self):
        """最新ステータスを1レコード投入"""

    def update_system_status(self):
        """メイン処理：削除→投入"""
```

### 3. 不要テーブル・ビューの削除

**削除対象**（SQL修正完了）:
1. **data_anomaly_log**: 定義のみで実装なし（data_quality_checksと重複）
2. **daily_process_summary**: ビューはあるが、system_statusで代替可能

**修正ファイル**: `sql/create_processing_status_table.sql`
- `process_execution_log`テーブルのみ残す
- `CREATE TABLE IF NOT EXISTS` → `CREATE OR REPLACE TABLE`に変更

### 4. SQLファイル作成

**ファイル**: `sql/create_system_status_table.sql`
- `CREATE OR REPLACE TABLE`構文を使用
- 1文でテーブル作成可能

---

## 技術的理解の向上

### 1レコードテーブルのメリット

**パフォーマンス**:
- Looker Studioは表示のたびにクエリ実行
- 集計関数だと`process_execution_log`全体をスキャン
- 1レコードテーブルなら即座に表示可能

**コスト**:
- BigQueryはスキャン量で課金
- 最新1レコードのみ = 最小限のスキャン量

**シンプル**:
- Looker Studioで集計不要
- ステータスを直接表示するだけ

### 既存の類似実装

**dashboard_data_updater.py**:
- 7日分のデータを洗い替え（部分更新）
- 過去データは保持（最大3年間）
- トレンド分析・長期分析が可能

**system_status_updater.py**:
- 全削除→1レコード投入（完全洗い替え）
- 過去データは不要（最新状態のみ）
- 監視目的に特化

### データソースの整理

**process_execution_log**:
- 各プロセスの実行履歴
- process_type: 'TEPCO_API', 'WEATHER_API', 'BQ_PROCESSING', 'ML_PREDICTION'
- パーティション: date（3年間保持）

**data_quality_checks**:
- データ品質チェック結果
- check_type: 'missing', 'null', 'outlier'
- status: 'OK', 'WARNING', 'ERROR'
- パーティション: check_date（2年間保持）

**system_status**（新規）:
- 最新システム状態（1レコード）
- パーティションなし
- 更新方式: 全削除→再投入

---

## 次回セッション予定

### 直近タスク

1. **system_status_updater.pyレビュー・修正**
2. **system_statusテーブル作成・updater動作確認**
3. **system_status_updaterをmain_etlに組み込み**
4. **Looker Studio監視ページ作成**

### その後のタスク

5. **Looker Studio予測結果表示ダッシュボード作成**
6. **予測モジュールの日別実行対応実装**
7. **予測モジュールのテスト実行**

---

## TODOリスト

### 🔲 未着手（直近）
1. **system_status_updater.pyレビュー・修正**
2. **system_statusテーブル作成・updater動作確認**
3. **system_status_updaterをmain_etlに組み込み**
4. **Looker Studio監視ページ作成**

### 🔲 未着手（その後）
5. **Looker Studio予測結果表示ダッシュボード作成**
6. **予測モジュールの日別実行対応実装**（argparse追加・基準日の変数化・テストモード分岐・精度評価機能追加）
7. **予測モジュールのテスト実行**（過去日で実行して精度確認）

---

## 技術メモ

### system_statusテーブルの更新ロジック

**SQL構造**:
```sql
WITH latest_process_status AS (
  -- process_execution_logから各プロセスの最新ステータスを取得
  SELECT process_type, status, error_message,
    ROW_NUMBER() OVER (PARTITION BY process_type ORDER BY started_at DESC) as rn
  FROM process_execution_log
  WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 7 DAY)
),
latest_quality_check AS (
  -- data_quality_checksから最新のチェック結果を取得
  SELECT status, issue_detail,
    ROW_NUMBER() OVER (ORDER BY check_timestamp DESC) as rn
  FROM data_quality_checks
  WHERE check_date >= DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 7 DAY)
)
SELECT
  CURRENT_DATETIME('Asia/Tokyo') AS updated_at,
  CASE WHEN status = 'SUCCESS' THEN 'OK'
       WHEN status = 'FAILED' THEN 'ERROR'
       ELSE 'WARNING' END AS tepco_api_status,
  ...
FROM latest_process_status
```

### ステータス変換ルール

**process_execution_log**:
- SUCCESS → OK
- FAILED → ERROR
- その他（データなし） → WARNING

**data_quality_checks**:
- そのまま使用（OK/WARNING/ERROR）

### 更新タイミング

**main_etl実行時**に自動更新（予定）:
1. データ取得（東電API・天気API）
2. BQ処理
3. ML予測
4. データ品質チェック
5. **system_status更新**（最後に実行）

---

## 実装済みファイル

### SQLファイル
- `sql/create_system_status_table.sql`（新規作成）
- `sql/create_processing_status_table.sql`（修正：不要部分削除）

### Pythonファイル
- `src/data_processing/system_status_updater.py`（新規作成・レビュー待ち）

---

**次回アクション**: system_status_updater.pyのレビュー実施、修正後に動作確認
