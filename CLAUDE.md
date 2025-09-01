# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## プロジェクト概要

**目的**: Google Cloudベースの電力使用量予測パイプラインの構築（データエンジニアポートフォリオ用）  
**目標**: 年収700万円以上のフルリモートデータエンジニア／データアナリスト職への就職  
**アプローチ**: 実務に近い開発環境とワークフローの実装、クラウドネイティブソリューションの実証

## プロジェクト現在地

**Phase**: 11準備完了（Looker Studio ダッシュボード構築準備）  
**予測精度**: MAPE 3.13%（段階的予測・実用レベル達成）  
**技術スタック**: Python 3.12 + XGBoost + GCP + Looker Studio  
**環境変数**: `ENERGY_ENV_PATH=C:\Users\tetsu\dev\energy-env`

## 実行コマンド

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

1. 予測結果CSV生成実行
2. GCSUploader使用してアップロード  
3. BigQuery投入・Looker Studio構築開始

# important-instruction-reminders
Do what has been asked; nothing more, nothing less.
NEVER create files unless they're absolutely necessary for achieving your goal.
ALWAYS prefer editing an existing file to creating a new one.
NEVER proactively create documentation files (*.md) or README files. Only create documentation files if explicitly requested by the User.