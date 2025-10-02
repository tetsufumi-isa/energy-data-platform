# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## プロジェクト概要

**目的**: Google Cloudベースの電力使用量予測パイプラインの構築（データエンジニアポートフォリオ用）  
**目標**: 年収700万円以上のフルリモートデータエンジニア／データアナリスト職への就職  
**アプローチ**: 実務に近い開発環境とワークフローの実装、クラウドネイティブソリューションの実証

## プロジェクト現在地

**Phase**: 11実装中（予測コードBQ対応完了・ログシステムリファクタリング完了）  
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

**最新セッション**: `learning_memos/20251002_Phase11_予測コード日次実行対応・コードレビュー前半完了.md` - 日次予測スクリプト化・データ取得最適化・営業日判定リファクタリング完了（1～454行目レビュー完了）

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

## Phase 11実装方針

Phase 11は「基盤整備→日次運用→予測精度分析」の3段階で進行中。

**詳細な進捗・次回TODO**: 最新セッションファイル（`learning_memos/20251002_Phase11_*.md`）を参照

### 大まかな実装フェーズ
1. **基盤修正フェーズ**
   - ログ・ステータステーブル・エラーハンドリング
   - 曜日判定修正・本番環境対応・日次実行設定

2. **日次運用開始後**
   - Looker Studio指標修正・実データ反映

3. **予測精度分析実装**
   - 16日に1回の検証テーブル・精度ダッシュボード

**完了状況**: 予測コードBQ対応・統合ログシステム実装・ML_PREDICTIONステータスログ保存・日次実行対応（検証分離・データ最適化）

**進捗管理ルール**: セッション終了時に最新進捗mdファイルを作成し、このCLAUDE.mdの「最新セッション」と「完了状況」を更新する

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