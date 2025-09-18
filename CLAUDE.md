# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## プロジェクト概要

**目的**: Google Cloudベースの電力使用量予測パイプラインの構築（データエンジニアポートフォリオ用）  
**目標**: 年収700万円以上のフルリモートデータエンジニア／データアナリスト職への就職  
**アプローチ**: 実務に近い開発環境とワークフローの実装、クラウドネイティブソリューションの実証

## プロジェクト現在地

**Phase**: 11実装中（Looker Studio 時間別分析ダッシュボード完成・日別分析実装準備中）  
**予測精度**: MAPE 3.43%（段階的予測・実用レベル達成）  
**技術スタック**: Python 3.12 + XGBoost + GCP + Looker Studio  
**環境変数**: `ENERGY_ENV_PATH=C:\Users\tetsu\dev\energy-env`

## 実行コマンド

### 前提条件: 仮想環境の有効化
```bash
# Windows
source venv/Scripts/activate

# または
venv\Scripts\activate
```

### Phase 11で使用するコマンド
```bash
# 予測実行+CSV出力（Phase 11メイン）
python -m src.prediction.prediction_iterative_with_export

# データ取得（メンテナンス時）
python -m src.pipelines.main_etl --days 7
```

### テスト・確認用
```bash
python -m tests.test_main_etl
python -m src.utils.check_ml_features_missing
```

## 質問別参照ガイド

**まず確認**: `learning_memos/INDEX.md` - 全ファイル構成とClaude推奨参照順

**最新セッション**: `learning_memos/20250918_Phase11_時間別分析ダッシュボード実装完了.md` - 時間別分析ダッシュボード完成・技術制約解決

| 質問タイプ | 参照先 |
|-----------|--------|
| 進捗・次ステップ | INDEX.mdの「最優先参照」→現在地ファイル |
| Phase詳細・技術概要 | INDEX.mdの「Phase別学習記録」 |
| システム設計・フロー | INDEX.mdの「全体設計」→システムフロー.md |
| 技術実装詳細 | INDEX.mdの「技術実装メモ」 |
| コード実装・エラー | `src/` ディレクトリ直接参照 |

## 主要ファイル位置

- **予測実行**: `src/prediction/prediction_iterative_with_export.py`
- **データ取得**: `src/data_processing/data_downloader.py` 
- **GCSアップロード**: `src/data_processing/gcs_uploader.py`
- **ログ設定**: `src/utils/logging_config.py`

## Phase 11次ステップ

1. ✅ 概要ページ・監視システム実装完了
2. ✅ 時間別分析ダッシュボード実装完了（技術制約解決・動的計算フィールド実装）
3. 日別分析ダッシュボード実装（日次トレンド・曜日パターン分析）
4. 月別分析ダッシュボード実装（季節変動・年間推移分析）
5. 予測特化ダッシュボード実装（精度監視・異常検知・予測vs実績比較）

# important-instruction-reminders
Do what has been asked; nothing more, nothing less.
NEVER create files unless they're absolutely necessary for achieving your goal.
ALWAYS prefer editing an existing file to creating a new one.
NEVER proactively create documentation files (*.md) or README files. Only create documentation files if explicitly requested by the User.

## コーディング方針
- コード内に絵文字使わない
- コード内で絵文字見つけたら修正する

## コミュニケーション方針
- **必ず日本語で対応する** - プロジェクト概要・技術説明・進捗報告など全て日本語
- 英語での説明・表記は行わない（コード内コメント・変数名は除く）