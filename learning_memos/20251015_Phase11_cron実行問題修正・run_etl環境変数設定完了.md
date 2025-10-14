# 20251015_Phase11_cron実行問題修正・run_etl環境変数設定完了

## セッション概要

**日時**: 2025年10月15日
**Phase**: Phase 11（基盤整備→日次運用→予測精度分析）
**主な作業**: cron実行失敗原因調査・run_etl.sh環境変数設定修正

## 主要成果

### 1. cron実行失敗の原因特定

**症状**:
- 10/15 4:00のcron実行が失敗
- ログに出力がなく、処理が開始されていない様子

**調査プロセス**:
1. cronログ確認 → 10/14 7:33が最終更新（10/14 4:00実行）
2. syslog確認 → 10/15 4:00にrun_etl.shは起動されている
3. しかしログに何も出力されていない

**原因判明**:
run_etl.shの先頭で`source ~/.bashrc`を実行していたが、**cronはnon-interactive shellなので、bashrcの以下のコードでreturnしてしまう**：

```bash
# ~/.bashrcの6-8行目
case $- in
    *i*) ;;
      *) return;;  # interactive shellじゃない場合はreturn
esac
```

その結果：
1. `ENERGY_ENV_PATH`環境変数が設定されない
2. `cd "$ENERGY_ENV_PATH"` が失敗
3. スクリプトが停止
4. ログに何も出力されない

### 2. run_etl.sh修正

**修正内容**:
bashrcを読み込む代わりに、環境変数を直接設定するよう変更。

```bash
# 修正前
source ~/.bashrc
cd "$ENERGY_ENV_PATH"

# 修正後
export ENERGY_ENV_PATH=/home/teisa/dev/energy-prediction-pipeline
export GOOGLE_APPLICATION_CREDENTIALS=/home/teisa/dev/energy-prediction-pipeline/key/energy-data-processor-key.json
cd "$ENERGY_ENV_PATH"
```

**ファイル**: `scripts/run_etl.sh`

### 3. テスト実行の試み

**結果**: streaming buffer問題で失敗

直前に手動でmain_etl.pyを実行していたため、BigQueryのstreaming bufferにデータが残っており、DELETEができずPhase 3で失敗。

**エラー内容**:
```
UPDATE or DELETE statement over table energy-env.prod_energy_data.energy_data_hourly
would affect rows in the streaming buffer, which is not supported
```

**影響範囲**:
- テスト実行失敗は一時的な問題（streaming bufferは90分～数時間で消える）
- **run_etl.shの修正自体は完了している**
- 明日朝4時のcron実行では正常に動作するはず

### 4. データ品質チェック動作確認（手動実行時）

**Phase 5の実行結果**:
- ERROR: 1件（天気データのレコード欠損24件）
- WARNING: 2件（temperature_2m, relative_humidity_2m のNULL値各2件）
- OK: 8件

**確認できたこと**:
- データ品質チェックが正常に動作
- ローカルログ保存: `/home/teisa/dev/energy-prediction-pipeline/logs/data_quality_checker/2025-10-15_quality_check_results.jsonl`
- BQ保存: 完了
- エラートレーサビリティが正しく機能

## 技術的理解の向上

### 1. cronとshellの種類

**interactive shell vs non-interactive shell**:
- **Interactive shell**: ユーザーがターミナルで直接操作するshell
  - bashrcが読み込まれる
  - プロンプトが表示される

- **Non-interactive shell**: cronやスクリプトから実行されるshell
  - bashrcは読み込まれない（デフォルト設定）
  - 多くのbashrcは先頭で`return`して処理をスキップ

**判定方法**:
```bash
case $- in
    *i*) ;;      # interactive shellならここ
      *) return;; # non-interactive shellならreturn
esac
```

**cron環境での対策**:
1. bashrcに依存しない（今回の修正方法）
2. `/etc/profile`を使う
3. crontabで直接環境変数を設定

### 2. BigQuery streaming bufferの制約

**streaming bufferとは**:
- `insert_rows_json()`などでストリーミング挿入したデータは、一時的にstreaming bufferに保存される
- 通常90分～数時間でテーブル本体に統合される
- **streaming buffer内のデータはDELETE/UPDATE不可**

**回避方法**:
1. 時間を置いてから実行（streaming bufferが消えるまで待つ）
2. バッチロードを使う（`load_table_from_file()`など）
3. パーティション単位で削除（streaming bufferと無関係）

**今回の影響**:
- 手動テスト実行が連続したため発生
- 本番のcron実行（24時間間隔）では問題なし

### 3. cronのログ調査方法

**syslogの活用**:
```bash
# 特定ユーザーのcron実行履歴
grep "CRON.*teisa" /var/log/syslog

# 特定時刻のcron実行
grep "Oct 15 04:" /var/log/syslog | grep CRON
```

**cronの実行確認ポイント**:
1. cronサービスが動作しているか（`systemctl status cron`）
2. crontabが正しく設定されているか（`crontab -l`）
3. syslogにcron実行ログがあるか
4. アプリケーションログに出力があるか

**今回のケース**:
- cronサービス: 動作中 ✓
- crontab設定: 正常 ✓
- syslogに実行ログあり: ✓
- アプリケーションログなし: ✗ → bashrc問題発見

## 次回セッション予定

### 明日（10/16）朝の確認事項

**cron実行結果の検証**:
1. `/home/teisa/dev/energy-prediction-pipeline/logs/cron_etl.log`
   - 10/16 4:00の実行ログが記録されているか
   - 全Phase（1-6）が正常完了しているか

2. データ品質チェック結果
   - ERROR/WARNING/OKの内訳
   - 具体的な問題内容

3. 予測実行結果
   - Phase 6が成功しているか
   - エラーがある場合は内容確認

### 次のステップ

**パターンA: cron実行成功時**
→ 過去5回分の予測実行（10/4、10/3、10/2、10/1、9/30）へ進む

**パターンB: cron実行失敗時**
→ エラー内容に応じて修正・再実行

## TODOリスト

- [ ] 過去5回分の予測実行（10/4、10/3、10/2、10/1、9/30）
- [ ] 予測精度検証モジュール実装（1日目～16日目の精度を5回分平均で算出）
- [ ] BQ修正・作成（精度検証結果反映）
- [ ] 日次実行セット（予測+精度検証の自動運用開始）
- [ ] Looker Studio予測結果表示ダッシュボード作成
- [ ] Looker Studio監視ページ作成（プロセス実行ログ・エラー監視・データ品質）

## 補足: cronとshellの環境変数

### cron実行時の環境

**cron環境の特徴**:
- 最小限の環境変数のみ設定される
- PATHも限定的（通常`/usr/bin:/bin`程度）
- ユーザーのログインシェル設定は読み込まれない

**crontabでの環境変数設定**:
```bash
# crontabの先頭で設定可能
ENERGY_ENV_PATH=/home/teisa/dev/energy-prediction-pipeline
GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json

0 4 * * * /path/to/script.sh
```

**スクリプトでの環境変数設定**（今回の方法）:
```bash
#!/bin/bash
export ENERGY_ENV_PATH=/home/teisa/dev/energy-prediction-pipeline
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json
# ... 以下処理
```

**メリット・デメリット**:
- crontabで設定: 複数スクリプトで共通化しやすい
- スクリプトで設定: スクリプト単体で完結、可搬性が高い（今回採用）

---

**今日の成果**: cron実行失敗の原因特定・run_etl.sh修正完了
**次回**: 明日朝のcron実行結果確認 → 過去5回分予測実行へ
