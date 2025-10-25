# 電力データ分析基盤（Energy Data Platform）

Google Cloud Platformを活用したデータ分析基盤です。データ収集、ETL処理、機械学習予測、Looker Studioによる可視化・監視までを統合した自動化パイプラインを実装しています。データの上流（収集）から下流（可視化）まで一気通貫で実装し、さらに機械学習による予測まで対応できるスキル実証を目的とし個人開発にて構築しています。

## プロジェクト概要

**目的**: データエンジニアリング × MLエンジニアリングの統合スキル実証
**アプローチ**: データの上流（収集）から下流（可視化）まで一気通貫で構築
**技術要素**: データ収集（東電API・気象API）→ ETL処理（BigQuery）→ 機械学習（XGBoost）→ BI可視化（Looker Studio）
**予測機能**: 14日間（336時間）の時系列予測、MAPE 7%程度
**ダッシュボード**: [Looker Studioで可視化](https://lookerstudio.google.com/reporting/c99e4784-b17e-431f-97cb-0a624ecd97e0)

## 主要機能

### 1. 自動データ収集パイプライン
- **電力データ**: 東京電力APIから実績データを自動取得
- **気象データ**: Open-Meteo APIから関東全域の気象データを取得
- **データ品質チェック**: 欠損値・異常値の自動検知とログ記録

### 2. 機械学習による予測
- **XGBoostモデル**: 時系列パターンを重視した12特徴量による予測
- **特徴量エンジニアリング**:
  - ラグ特徴量（1日前・7日前・1営業日前）
  - カレンダー特徴量（曜日・祝日・時間帯・循環特徴量）
  - 気象特徴量（気温・湿度・降水量）
- **段階的予測**: 実運用を想定した14日間の段階的予測

### 3. データ基盤（Google Cloud Platform）
- **BigQuery**: データウェアハウス（8テーブル構成）
  - 電力・気象の統合データ
  - 予測結果の履歴管理
  - システム監視ログ
- **Cloud Storage**: 生データの永続化

### 4. 運用監視システム
- **7プロセス監視**: ETLパイプライン全体の実行状況を監視
- **データ品質チェック**: 自動品質検証とアラート
- **予測精度検証**: 14日ごとの精度検証と分析
- **実行ログ管理**:
  - ローカルファイルとBigQueryへの二重記録
  - 処理時間・成功/失敗ステータスの自動記録
  - Looker Studioでの可視化
- **統合ダッシュボード**: [Looker Studioで可視化](https://lookerstudio.google.com/reporting/c99e4784-b17e-431f-97cb-0a624ecd97e0)

## システムアーキテクチャ

```mermaid
%%{
  init: {
    'theme':'dark',
    'themeVariables': {
      'fontSize':'17px',
      'fontFamily':'Arial',
      'clusterBkg':'#1f2937',
      'clusterBorder':'#0b163a',
      'labelTextColor':'#ffffff'
    }
  }
}%%
graph TB
    subgraph データ収集層
        A1["<b>東京電力API</b>"]
        A2["<b>Open-Meteo API</b>"]
        A1 --> B1["<b>PowerDataDownloader</b>"]
        A2 --> B2["<b>WeatherDownloader</b>"]
    end

    subgraph ETL処理層
        C1["<b>データクレンジング</b>"]
        C2["<b>特徴量生成</b><br/><i>12特徴量</i>"]
        C3["<b>BigQueryロード</b>"]
        C1 --> C2
        C2 --> C3
    end

    B1 --> C1
    B2 --> C1

    subgraph データ基盤層GCP
        D1["<b>BigQuery</b><br/>━━━━━━━━━━━<br/>• power_weather_integrated<br/>• ml_features<br/>• prediction_results<br/>• prediction_accuracy<br/>• system_status<br/>• process_execution_log<br/>• data_quality_checks<br/>• dashboard_data"]
        D2["<b>Cloud Storage</b><br/><i>バックアップ・履歴管理</i>"]
    end

    C3 --> D1
    C3 --> D2

    subgraph 機械学習層
        E1["<b>XGBoostモデル</b><br/><i>MAPE 7%程度</i>"]
        E2["<b>14日間段階的予測</b><br/><i>336時間予測</i>"]
        E1 --> E2
        E2 --> D1
    end

    D1 --> E1

    subgraph 可視化監視層
        F1["<b>Looker Studio</b><br/>━━━━━━━━━━━<br/>• システム監視(7プロセス)<br/>• 予測結果表示<br/>• 予測精度分析<br/>• データ品質チェック結果"]
    end

    D1 --> F1

    classDef defaultStyle fill:#1a223d,stroke:#9fa8da,stroke-width:0.5px,color:#fff,rx:10,ry:10
    classDef clusterStyle rx:15,ry:15

    class A1,A2,B1,B2,C1,C2,C3,D1,D2,E1,E2,F1 defaultStyle

    style データ収集層 rx:15,ry:15
    style ETL処理層 rx:15,ry:15
    style データ基盤層GCP rx:15,ry:15
    style 機械学習層 rx:15,ry:15
    style 可視化監視層 rx:15,ry:15
```

## 技術スタック

| カテゴリ | 技術 |
|---------|------|
| **言語** | Python 3.12 |
| **機械学習** | XGBoost, scikit-learn |
| **データ処理** | pandas, numpy |
| **クラウド** | Google Cloud Platform (BigQuery, Cloud Storage) |
| **BI/可視化** | Looker Studio, matplotlib, seaborn |
| **API** | 東京電力API, Open-Meteo API |
| **その他** | python-dotenv, requests |

## 予測精度と成果

### 予測精度（MAPE: Mean Absolute Percentage Error）

| モデル | MAPE | 説明 |
|--------|------|------|
| **カレンダー特徴量のみ** | 7%程度 | ベースライン（曜日・時間帯・祝日） |
| **全特徴量（1週間予測）** | 2-3%程度 | 実測値ラグを使用した短期予測 |
| **段階的予測（14日間）** | **7%程度** | 予測値ラグを使用した実運用想定 |

### 技術的成果

1. **段階的予測による実運用対応**
   - 短期予測（1週間）: MAPE 2-3%程度
   - 長期予測（14日間）: MAPE 7%程度

2. **完全自動化パイプライン**
   - データ収集からBigQuery投入まで完全自動化
   - cron + Pythonスクリプトにより日次自動実行を実現
   - 失敗時はリトライ処理を実装し、BigQueryログ経由で監視可能
   - システム監視とアラート

3. **データ可視化・BI実装**
   - Looker Studioダッシュボードを設計・実装
   - 7プロセス監視、予測結果、精度分析、データ品質を統合
   - BigQueryとの連携による日次自動更新

4. **実運用対応**
   - 土日祝日の欠損値自動処理
   - API制限への対応
   - パーティション設計による大規模データ管理

5. **データ品質管理**
   - 自動品質チェック（欠損値・外れ値検出）
   - 実行ログの完全記録
   - 予測精度の継続的検証

### AI支援による開発プロセス

**Claude Code**:
- 初期コード生成にClaude Codeを活用
- AI出力をそのまま用いるのではなく全コードを精査し、構造設計・リファクタリング・機能追加を開発者が主導し最適化
- ペアプログラミング的な活用により開発効率を向上

## プロジェクト構成

```
energy-env/
├── src/
│   ├── data_processing/          # データ収集・処理
│   │   ├── data_downloader.py    # 東京電力APIからデータ取得
│   │   ├── weather_downloader.py # 気象データ取得
│   │   ├── weather_bigquery_loader.py # 気象データBigQuery投入
│   │   ├── power_bigquery_loader.py   # 電力データBigQuery投入
│   │   ├── ml_features_updater.py     # ML用特徴量生成・更新
│   │   ├── dashboard_data_updater.py  # ダッシュボード用データ更新
│   │   ├── prediction_accuracy_updater.py # 予測精度検証データ更新
│   │   └── system_status_updater.py   # システムステータス更新
│   ├── pipelines/
│   │   └── main_etl.py           # 統合ETLパイプライン
│   ├── prediction/
│   │   └── prediction_iterative_with_export.py # 段階的予測実行
│   ├── monitoring/
│   │   └── data_quality_checker.py # データ品質チェック
│   └── utils/
│       └── logging_config.py      # ログ設定
├── sql/                           # BigQueryテーブル定義
├── scripts/                       # 運用スクリプト
├── requirements.txt               # Python依存パッケージ
└── SETUP.md                       # セットアップ手順
```

## セットアップ

### 前提条件

- Python 3.12以上
- Google Cloud Platformアカウント
- BigQueryプロジェクト

### インストール手順

1. **リポジトリのクローン**
```bash
git clone https://github.com/yourusername/energy-data-platform.git
cd energy-data-platform
```

2. **仮想環境の作成と有効化**
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

3. **依存パッケージのインストール**
```bash
pip install -r requirements.txt
```

4. **環境変数の設定**
```bash
# .envファイルを作成（.env.templateを参考に）
cp .env.template .env

# 必要な環境変数を設定
ENERGY_ENV_PATH=/path/to/energy-env
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
GCP_PROJECT_ID=your-project-id
```

5. **BigQueryテーブルの作成**
```bash
# sqlディレクトリ内のSQLファイルを実行
```

詳細なセットアップ手順は [SETUP.md](./SETUP.md) を参照してください。

## 使用方法

### 日次データ収集と予測実行

```bash
# 仮想環境の有効化
# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate

# データ収集（過去7日分）
python -m src.pipelines.main_etl --days 7

# 予測実行（14日間予測 + CSV出力）
python -m src.prediction.prediction_iterative_with_export
```

### データ品質チェック

```bash
# ML特徴量の欠損値チェック
python -m src.utils.check_ml_features_missing
```

## 開発プロセス

このプロジェクトは11のフェーズで段階的に開発されました：

| Phase | 内容 | 主要成果 |
|-------|------|---------|
| **Phase 1-2** | 電力データ基盤 | 東京電力API統合、30ヶ月分データ取得 |
| **Phase 3-4** | 気象データ基盤 | Open-Meteo API統合、BigQuery自動投入 |
| **Phase 5-6** | 特徴量エンジニアリング | 190特徴量設計、時系列分析基盤構築 |
| **Phase 7** | 機械学習モデル構築 | 特徴量選択、XGBoost実装、MAPE 2.33%達成 |
| **Phase 8** | モデル評価・改善 | 評価指標深層理解、残差分析 |
| **Phase 9** | 品質向上 | 12特徴量に絞り込み、MAPE 2.15%達成 |
| **Phase 10** | 自動化システム | 日次自動予測、土日祝日対応 |
| **Phase 11** | 監視・可視化 | Looker Studio、7プロセス監視 |

## 技術的ハイライト

### 1. 特徴量エンジニアリング

**試行錯誤による最適化**:
- Phase 5-6で190特徴量を設計（営業日・全日ベースのラグ特徴量、移動平均、変化率など）
- 気象データは関東全域平均・各都道府県を試行し、千葉県単独が最も精度が高いことを確認
- Phase 7-9で段階的な実験を実施
- 直前の使用量パターンが予測精度の鍵であることを発見
- 最終的に12特徴量に絞り込み、短期予測でMAPE 2-3%程度を達成

**最終的な12特徴量**:
```python
# 時系列特徴量（3個）- 特に1営業日前が重要
'lag_1_day',              # 1日前同時刻
'lag_7_day',              # 7日前同時刻
'lag_1_business_day',     # 1営業日前同時刻

# カレンダー特徴量（6個）
'hour',                   # 時間（0-23）
'is_weekend',             # 週末フラグ
'is_holiday',             # 祝日フラグ
'month',                  # 月（1-12）
'hour_sin',               # 時間周期性（sin）
'hour_cos',               # 時間周期性（cos）

# 気象特徴量（3個）
'temperature_2m',         # 気温
'relative_humidity_2m',   # 湿度
'precipitation'           # 降水量
```

### 2. 段階的予測ロジック

予測には「前日の使用量」が重要な特徴量だが、未来を予測する際にはその前日自体も未来である。そのため、予測値を使って次の日を予測する段階的なプロセスを実装。

```python
# 例: 10月25日時点で10月26日～11月8日（14日間）を予測

# 1日目（10月26日）: 前日（10月25日）は実測値
predict(10月26日) → 実測値ベースで予測

# 7日目（11月1日）: 前日（10月31日）は予測値
predict(11月1日) → 10月26日から10月31日の予測値を使って予測

# 14日目（11月8日）: 前日（11月7日）も予測値
predict(11月8日) → 10月26日から11月7日の予測値を使って予測

# 結果: 14日間全体でMAPE 7%程度
```

### 3. BigQueryテーブル設計

**パーティション戦略**:
- `process_execution_log`: 処理実行日でパーティション
- `prediction_results`: 予測実行日でパーティション
- `prediction_accuracy`: 検証実行日でパーティション

テーブル設計では、処理日ベースのパーティション分割を採用し、増分処理・再計算・監視分析の効率化を実現しています。

### 4. システム監視

**7プロセス監視**:
1. DATA_DOWNLOAD - 電力データ取得
2. WEATHER_DOWNLOAD - 気象データ取得
3. WEATHER_BQ_LOAD - 気象データBigQuery投入
4. POWER_BQ_LOAD - 電力データBigQuery投入
5. ML_FEATURES_UPDATE - 特徴量更新
6. DATA_QUALITY_CHECK - データ品質チェック
7. PREDICTION - 予測実行

各プロセスの実行状態、所要時間、エラー情報をLooker Studioで可視化しています。

## 今後の展望

- Apache Airflowによるワークフロー管理・スケジューリング
- Web UIでのパイプライン監視・制御機能

## スキルセット
- データエンジニアリング（ETL、データパイプライン、BigQuery）
- 機械学習（XGBoost、特徴量エンジニアリング、時系列予測）
- Google Cloud Platform（BigQuery、Cloud Storage、Looker Studio）
- Python開発（pandas、numpy、scikit-learn）
- システム設計（自動化、監視、エラーハンドリング）

## ライセンス

このプロジェクトは個人の学習・ポートフォリオ目的で作成されています。

---

**お問い合わせ**: プロジェクトに関するご質問やフィードバックは、GitHubのIssuesまでお願いします。
