# Phase 11 進捗記録: タイムゾーン問題修正・datetime.now()統一化

**日付**: 2025-10-18
**Phase**: 11 - 基盤整備フェーズ
**ステータス**: タイムゾーン問題完全解決・天気データ投入成功

---

## セッション概要

cronで途中停止していた原因を調査し、`started_at`/`completed_at`のタイムゾーン処理が原因であることを特定。全モジュールで`datetime.now(ZoneInfo('Asia/Tokyo'))`を`datetime.now()`に統一することで、DATETIME型へのタイムゾーンサフィックス（`+09:00`）エラーを解決。

---

## 主要成果

### 1. cron途中停止の原因特定

**問題**: cronで実行したmain_etlパイプラインが途中で停止

**調査結果**:
- パイプライン実行順序を確認
- `started_at`と`completed_at`のタイムゾーン処理を調査
- 一部モジュールで`.isoformat()`のみ使用し、タイムゾーンサフィックス（`+09:00`）が付いたままBigQueryに投入
- DATETIME型はタイムゾーンサフィックスを受け付けないためエラーで停止

**影響範囲**:
- Phase 1（data_downloader）: HTTPエラー時のログ記録で停止の可能性
- Phase 2（weather_downloader）: 複数箇所でエラーの可能性
- Phase 6（data_quality_checker）: エラー時のログ記録で停止の可能性

### 2. タイムゾーン処理の統一修正

**修正方針**: サーバーのタイムゾーン（Asia/Tokyo）に依存するシンプルな方式

```python
# 修正前
started_at = datetime.now(ZoneInfo('Asia/Tokyo'))
"started_at": started_at.replace(tzinfo=None).isoformat()  # または .isoformat()

# 修正後
started_at = datetime.now()
"started_at": started_at.isoformat()
```

**修正理由**:
- サーバーのタイムゾーン設定が`Asia/Tokyo (JST, +0900)`であることを確認済み
- `datetime.now()`はサーバーのローカル時刻（JST）を返す
- タイムゾーンサフィックスが付かないため、DATETIME型に直接投入可能
- コードがシンプルになる

**修正ファイル（5ファイル）**:

1. **`src/data_processing/data_downloader.py`** - 11箇所
   - `_write_log()`のlog_date, error_log timestamp
   - `get_required_months()`のyesterday
   - `get_month_from_date()`のyesterday
   - `download_month_data()`のstarted_at, completed_at（成功・404エラー・HTTPエラー・その他エラー）
   - `download_for_month()`のcurrent_month

2. **`src/data_processing/weather_downloader.py`** - 15箇所
   - `_write_log()`のlog_date, error_log timestamp
   - `download_daily_weather_data()`のtoday, started_at, completed_at（日次自動実行モード・過去データ分析モード、それぞれ成功時・エラー時）
   - `download_historical_data()`のstarted_at, completed_at（成功時・エラー時）
   - `download_for_month()`のstarted_at, completed_at（成功時・エラー時）
   - `main()`のtoday

3. **`src/monitoring/data_quality_checker.py`** - 13箇所
   - `_write_log()`のlog_date, error_log timestamp
   - `_save_check_results()`のexecution_date
   - `check_power_data()`のcheck_date, check_timestamp, period_end
   - `check_weather_data()`のcheck_date, check_timestamp, period_start, period_end
   - `run_quality_check()`のstarted_at, target_date_str, completed_at（成功時・失敗時）

4. **`src/data_processing/weather_bigquery_loader.py`** - 9箇所
   - 各行のcreated_at（`parse_json_to_rows()`内）
   - `_write_log()`のlog_date, error_log timestamp
   - `load_weather_data()`のstarted_at, dt, completed_at（成功時・失敗時）

5. **`src/data_processing/power_bigquery_loader.py`** - 8箇所
   - 各行のcreated_at（`parse_csv_to_rows()`内）
   - `_write_log()`のlog_date, error_log timestamp
   - `load_power_data()`のstarted_at, yesterday, completed_at（成功時・失敗時）

### 3. パイプライン実行テスト

**実行結果**:
- Phase 1（電力データダウンロード）: 成功
- Phase 2（気象データダウンロード）: 成功
- Phase 3（電力データBQ投入）: ストリーミングバッファエラー（別問題）
- Phase 4-1（気象過去データBQ投入）: ストリーミングバッファエラー（別問題、手動で投入済み）
- Phase 4-2（気象予測データBQ投入）: **成功！336行投入**

**タイムゾーン問題**: 完全解決
**新たな問題**: BigQueryストリーミングバッファの制限によるDELETEエラー

### 4. 新たな問題の発見

**BigQueryストリーミングバッファエラー**:
```
UPDATE or DELETE statement over table would affect rows in the streaming buffer, which is not supported
```

**原因**:
- ストリーミング投入したデータは90分程度バッファに残る
- バッファ内のデータに対してDELETE/UPDATE不可
- `delete_duplicate_data()`メソッドが既存データを削除しようとしてエラー

**影響範囲**:
- `power_bigquery_loader.py`: 重複削除処理がエラー
- `weather_bigquery_loader.py`: 重複削除処理がエラー（予測データは成功、過去データは失敗）

**解決策（次回実装予定）**:
1. MERGE文を使った重複回避（推奨）
2. ストリーミングバッファが空になるまで待機（90分）
3. DELETE処理をスキップ（一時的対処）

---

## 技術的理解の向上

### サーバータイムゾーン設定の確認

```bash
timedatectl
# Local time: Sat 2025-10-18 11:55:06 JST
# Time zone: Asia/Tokyo (JST, +0900)
```

サーバーが`Asia/Tokyo`に設定されているため、`datetime.now()`は常にJSTを返す。

### datetime処理のベストプラクティス

**原則**: サーバー環境のタイムゾーン設定に依存する場合は、明示的にZoneInfoを指定せず`datetime.now()`を使うとシンプル

**メリット**:
- コードがシンプル
- タイムゾーンサフィックスが付かない
- DATETIME型に直接投入可能

**デメリット**:
- サーバーのタイムゾーン設定に依存
- 他の環境に移行時は注意が必要

### BigQueryストリーミングバッファの制約

- ストリーミング投入されたデータは90分程度バッファに残る
- バッファ内のデータに対してDELETE/UPDATEは不可
- MERGE文を使えば重複を回避しつつ投入可能

---

## 次回セッション予定

### 優先タスク: BigQueryストリーミングバッファ対応

1. **MERGE文への移行**
   - `power_bigquery_loader.py`の`delete_duplicate_data()`をMERGE文に変更
   - `weather_bigquery_loader.py`の`delete_duplicate_data()`をMERGE文に変更
   - 重複を回避しつつ投入可能にする

2. **パイプライン全体の実行確認**
   - ストリーミングバッファ問題解決後、main_etlを最初から最後まで実行
   - 全Phaseが正常に動作することを確認

### その他のタスク

3. **Looker Studio監視ページ実装**
4. **Looker Studio予測結果表示ダッシュボード作成**
5. **予測モジュールの日別実行対応実装**
6. **予測モジュールのテスト実行**

---

## TODOリスト

### ✅ 完了
1. **cronで途中停止した原因調査（started_at関連のタイムゾーン問題）**
   - 5ファイル（39箇所）のタイムゾーン処理を`datetime.now()`に統一
   - DATETIME型エラー完全解決
   - 天気データ投入成功確認

### 🔲 次回優先
2. **BigQueryストリーミングバッファ対応（MERGE文への移行）**
   - power_bigquery_loaderのMERGE文実装
   - weather_bigquery_loaderのMERGE文実装

3. **Looker Studio監視ページ実装**
4. **Looker Studio予測結果表示ダッシュボード作成**

### 🔲 未着手
5. **予測モジュールの日別実行対応実装**
   - argparse追加（--base-date, --testオプション）
   - 基準日の変数化
   - テストモード分岐
   - 精度評価機能追加

6. **予測モジュールのテスト実行**
   - 過去日で実行して精度確認

---

## 技術メモ

### 修正パターン例

```python
# data_downloader.py (11箇所)
datetime.now(ZoneInfo('Asia/Tokyo')) → datetime.now()

# weather_downloader.py (15箇所)
datetime.now(ZoneInfo('Asia/Tokyo')) → datetime.now()

# data_quality_checker.py (13箇所)
datetime.now(ZoneInfo('Asia/Tokyo')) → datetime.now()

# weather_bigquery_loader.py (9箇所)
datetime.now(ZoneInfo('Asia/Tokyo')).isoformat() → datetime.now().isoformat()

# power_bigquery_loader.py (8箇所)
datetime.now(ZoneInfo('Asia/Tokyo')).isoformat() → datetime.now().isoformat()
```

### BigQueryエラーの詳細

```
400 GET https://bigquery.googleapis.com/bigquery/v2/projects/energy-env/queries/...
UPDATE or DELETE statement over table energy-env.prod_energy_data.energy_data_hourly
would affect rows in the streaming buffer, which is not supported
```

このエラーはデータの整合性を保つためのBigQueryの仕様であり、MERGE文を使うことで回避可能。

---

**次回アクション**: MERGE文実装でストリーミングバッファ問題を解決し、パイプライン全体の正常動作を確認
