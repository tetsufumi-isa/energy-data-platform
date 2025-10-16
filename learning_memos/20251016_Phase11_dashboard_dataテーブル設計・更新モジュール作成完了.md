# Phase 11 進捗記録 - dashboard_dataテーブル設計・更新モジュール作成完了

**日付**: 2025年10月16日
**フェーズ**: Phase 11（基盤整備→日次運用→予測精度分析）
**セッション内容**: Looker Studio用dashboard_dataテーブル設計・更新モジュール作成

---

## セッション概要

Looker Studio用のダッシュボードデータテーブルの設計・実装を完了：
1. **dashboard_dataテーブル設計**: 電力・天気・カレンダー・予測データを統合したテーブル
2. **テーブル作成SQL**: パーティション・クラスタリング設定完了
3. **データ更新モジュール作成**: 今日以降のデータを削除→再挿入する仕組み
4. **昨日までのデータ投入SQL**: 1回切りの履歴データ投入クエリ
5. **予測モデルロジック確認**: 学習・予測期間が正しく動作していることを確認

**所要時間**: 約1.5時間
**成果**: dashboard_dataテーブル設計完了・更新モジュール作成完了

---

## 主要成果

### 1. dashboard_dataテーブル設計完了

**テーブル構成（16カラム）**:

| カテゴリ | カラム名 | 型 | 説明 | データソース |
|---------|---------|-----|------|------------|
| 日時 | date | DATE | 日付 | energy_data_hourly |
| | hour | INTEGER | 時刻（0-23） | energy_data_hourly |
| 電力 | actual_power | FLOAT | 実績電力使用量 | energy_data_hourly |
| | supply_capacity | FLOAT | 供給能力 | energy_data_hourly |
| | predicted_power | FLOAT | 予測電力使用量 | prediction_results（最新execution_id） |
| 誤差 | error_absolute | FLOAT | 絶対誤差（計算） | `|predicted - actual|` |
| | error_percentage | FLOAT | 誤差率（計算） | `(|predicted - actual| / actual) * 100` |
| 天気 | temperature_2m | FLOAT | 気温 | weather_data（千葉県） |
| | relative_humidity_2m | FLOAT | 湿度 | weather_data（千葉県） |
| | precipitation | FLOAT | 降水量 | weather_data（千葉県） |
| | weather_code | INTEGER | 天気コード | weather_data（千葉県） |
| カレンダー | day_of_week | STRING | 曜日（英語） | calendar_data |
| | is_weekend | BOOLEAN | 週末フラグ | calendar_data |
| | is_holiday | BOOLEAN | 祝日フラグ | calendar_data |
| 計算 | usage_rate | FLOAT | 使用率％（計算） | `(actual / supply) * 100` |
| | weekday_jp | STRING | 曜日（日本語） | day_of_weekを変換 |

**テーブル設定**:
- パーティション: date列（DAY）
- クラスタリング: hour列
- 保持期間: 3年（1095日）

**作成ファイル**: `sql/create_dashboard_data_table.sql`

---

### 2. データ更新モジュール作成完了

**ファイル**: `src/data_processing/dashboard_data_updater.py`

**更新ロジック（案A採用）**:
1. **今日以降のデータを全削除**
   ```sql
   DELETE FROM dashboard_data WHERE date >= CURRENT_DATE('Asia/Tokyo')
   ```
   - 東電の修正対応も含めてシンプルで確実
   - 当日の実績データも削除→再挿入

2. **統合データ取得**
   - 電力・天気・カレンダー・予測（最新execution_id）を結合
   - 誤差・使用率・曜日日本語表記を計算

3. **dashboard_dataに投入**
   - 重複なし（削除→挿入で確実）

**実行方法**:
```bash
python -m src.data_processing.dashboard_data_updater
```

**ログ記録**:
- ローカルファイル: `logs/dashboard_updater/YYYYMMDD_dashboard_update_execution.jsonl`
- BigQuery: `process_execution_log`テーブル

---

### 3. 昨日までのデータ投入SQL作成

**ファイル**: `sql/insert_historical_dashboard_data.sql`

**用途**: 1回切りの履歴データ投入
- 昨日まで（`WHERE date < CURRENT_DATE('Asia/Tokyo')`）のデータを投入
- 電力・天気・カレンダー・予測を統合

**実行方法**:
```bash
# テーブル作成
bq query --use_legacy_sql=false < sql/create_dashboard_data_table.sql

# 昨日までのデータ投入
bq query --use_legacy_sql=false < sql/insert_historical_dashboard_data.sql
```

---

### 4. 予測モデルロジック確認

**確認内容**:
ユーザーから「予測精度が落ちている」との指摘があり、予測モデルの学習・予測期間が正しいか確認。

**確認結果**:
- **学習データ**: 昨日まで（`WHERE date <= '{yesterday}'`） ✅
- **予測期間**: 今日から14日分（`today` ～ `today + 13days`） ✅
- **天気データ**: 今日から14日分の予測データを使用 ✅

**結論**: コードは正しく動作している。精度低下の原因は以下の可能性:
1. 天気予測データの精度（Open-Meteo）
2. 予測期間が長くなるほど累積誤差が増加
3. 季節変動・パターン変化

→ 次のステップで「予測精度検証モジュール」を実装して詳細分析予定

---

## 技術的理解の向上

### テーブル設計の方針決定

**ビュー vs テーブル**:
- ❌ ビュー: JOIN処理がLooker Studio実行時に走る→遅い
- ✅ テーブル: JOIN済みでマテリアライズ→高速

**データ更新方針**:
- ❌ MERGE/UPDATE: 複雑・重複リスク
- ✅ DELETE + INSERT: シンプル・確実・重複なし

### 予測データの管理方針

**dashboard_data**: 可視化用の最新状態のみ
- 最新execution_idの予測のみ保持
- 段階的予測で毎日変わるため「今日以降全削除→再挿入」

**prediction_results**: 全履歴保持
- execution_id付きで全予測履歴を保存
- 予測精度検証時に過去の予測を参照

### データ削除範囲の決定

**案A（採用）**: 今日以降を全削除
```sql
WHERE date >= CURRENT_DATE('Asia/Tokyo')
```
- メリット: シンプル・確実・東電の修正にも対応
- デメリット: 当日の実績も削除（すぐ再挿入するため問題なし）

**案B**: 予測データのみ削除
- 複雑な条件（実績は保持・予測は削除）
- 不採用

**案C**: 明日以降のみ削除
- 当日データが二重管理になる可能性
- 不採用

---

## 作成ファイル一覧

| ファイル | 内容 |
|---------|------|
| `sql/create_dashboard_data_table.sql` | dashboard_dataテーブル作成SQL |
| `sql/insert_historical_dashboard_data.sql` | 昨日までのデータ投入SQL（1回切り） |
| `src/data_processing/dashboard_data_updater.py` | dashboard_data更新モジュール |

---

## 次回セッション予定

### 実施予定タスク（優先順）

1. **dashboard_data_updater.pyのコードレビュー**（ユーザー担当）
   - ロジック確認
   - エラーハンドリング確認

2. **main_etl.pyにdashboard_data_updater組み込み**
   - 予測実行後に自動でdashboard_data更新
   - エラー時のハンドリング

3. **予測モジュールの日別実行対応（基準日指定機能追加）**
   - 現在: 「今日」から14日間を予測
   - 改善後: 「指定した日」から14日間を予測
   - 用途: 過去の特定日時点でのデータで予測→実績と比較して精度測定

4. **予測精度検証モジュール実装**
   - 1日目～14日目の精度を5回分平均で算出
   - 日次実行での自動精度測定

5. **予測精度向上（特徴量・モデル改善）**
   - 精度検証結果をもとに改善

6. **BQ修正・作成（精度検証結果テーブル作成）**

7. **Looker Studio監視ページ実装**

8. **Looker Studio予測結果表示ダッシュボード作成**

---

## TODOリスト

### 完了済み
- [x] dashboard_dataテーブル設計
- [x] テーブル作成SQL作成
- [x] 昨日までのデータ投入SQL作成
- [x] dashboard_data_updater.py作成
- [x] 予測モデルロジック確認
- [x] テーブル作成実行
- [x] 昨日までのデータ投入実行

### 未完了
- [ ] dashboard_data_updater.pyのコードレビュー（ユーザー担当）
- [ ] main_etl.pyにdashboard_data_updater組み込み
- [ ] 予測モジュールの日別実行対応（基準日指定機能追加）
- [ ] 予測精度検証モジュール実装（1日目～14日目の精度を5回分平均で算出）
- [ ] 予測精度向上（特徴量・モデル改善）
- [ ] BQ修正・作成（精度検証結果テーブル作成）
- [ ] Looker Studio監視ページ実装（BigQueryビュー作成 → Looker Studio接続）
- [ ] Looker Studio予測結果表示ダッシュボード作成

---

## 備考

### dashboard_dataテーブルの役割

**Looker Studioパフォーマンス最適化**:
- JOIN処理を事前実行（マテリアライズド）
- Looker Studio側はSELECTのみで高速表示

**データ一元管理**:
- 実績・予測・天気・カレンダーを1テーブルで管理
- 分析・ダッシュボード作成が容易

### 今後の運用フロー

**日次実行時（cron 6:30）**:
1. 電力データダウンロード
2. 電力データBQ投入
3. 予測実行
4. **dashboard_data更新（今回実装）** ← NEW!
5. データ品質チェック

### 学んだこと

**テーブル設計の重要性**:
- ビューではなくテーブルにすることでパフォーマンスが劇的に向上
- Looker Studioではマテリアライズドデータが必須

**シンプルなロジックの価値**:
- DELETE + INSERT のシンプルな方式が最も確実
- 複雑なMERGE/UPDATEは避ける

**予測データの二重管理**:
- dashboard_data: 可視化用（最新のみ）
- prediction_results: 検証用（全履歴）
- 目的別に明確に分離
