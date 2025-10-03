# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## プロジェクト概要

**目的**: Google Cloudベースの電力使用量予測パイプラインの構築（データエンジニアポートフォリオ用）
**目標**: 年収700万円以上のフルリモートデータエンジニア／データアナリスト職への就職
**アプローチ**: 実務に近い開発環境とワークフローの実装、クラウドネイティブソリューションの実証

## GCP環境設定

**BigQueryロケーション**: `us-central1`
**プロジェクトID**: （環境変数から取得）
**データセット**: `energy_data`

## プロジェクト概要（固定情報）

**Phase**: 11（基盤整備→日次運用→予測精度分析）
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

| 質問タイプ | 参照先 |
|-----------|--------|
| 進捗・次ステップ | `learning_memos/INDEX.md`の「最優先参照」→最新進捗ファイル |
| Phase詳細・技術概要 | `learning_memos/INDEX.md`の「Phase別学習記録」 |
| システム設計・フロー | `learning_memos/INDEX.md`の「全体設計」→システムフロー.md |
| 技術実装詳細 | `learning_memos/INDEX.md`の「技術実装メモ」 |
| コード実装・エラー | `src/` ディレクトリ直接参照 |

## 主要ファイル位置

- **予測実行**: `src/prediction/prediction_iterative_with_export.py`
- **データ取得**: `src/data_processing/data_downloader.py` 
- **GCSアップロード**: `src/data_processing/gcs_uploader.py`
- **ログ設定**: `src/utils/logging_config.py`

## Phase 11実装方針（固定）

Phase 11は「基盤整備→日次運用→予測精度分析」の3段階で進行。

### 大まかな実装フェーズ
1. **基盤修正フェーズ**
   - ログ・ステータステーブル・エラーハンドリング
   - 曜日判定修正・本番環境対応・日次実行設定

2. **日次運用開始後**
   - Looker Studio指標修正・実データ反映

3. **予測精度分析実装**
   - 16日に1回の検証テーブル・精度ダッシュボード

**詳細な進捗・次回TODO**: `learning_memos/INDEX.md`の「最優先参照」から最新進捗ファイルを確認

## セッション開始時の動作

**重要**: チャット立ち上げ時は以下の手順で進捗を確認してください：

1. **INDEX.mdを読み込み**
   - `learning_memos/INDEX.md`の「最優先参照」セクションを確認
   - 最新進捗ファイルのパスを特定

2. **最新進捗ファイルを読み込み**
   - ファイル内のTODOセクションを確認

3. **TodoWriteツールでTODOを記録**
   - 最新進捗ファイルから抽出したTODOをTodoWriteツールに登録
   - 全てのTODOを`pending`ステータスで記録

4. **ユーザーに進捗を報告**
   - チャット開始時に「今回のTODOです」として一覧を表示
   - 現在のフェーズと次に取り組むタスクを明示

# important-instruction-reminders
Do what has been asked; nothing more, nothing less.
NEVER create files unless they're absolutely necessary for achieving your goal.
ALWAYS prefer editing an existing file to creating a new one.
NEVER proactively create documentation files (*.md) or README files. Only create documentation files if explicitly requested by the User.

## コーディング方針
- コード内に絵文字使わない
- コード内で絵文字見つけたら修正する
- **ログとprint文は日本語で記述**
  - `print()`による出力は原則日本語
  - ログファイルへの記録も日本語
  - エラーメッセージも日本語（例外の`str(e)`は除く）

## コミュニケーション方針
- **必ず日本語で対応する** - プロジェクト概要・技術説明・進捗報告など全て日本語
- 英語での説明・表記は行わない（コード内コメント・変数名は除く）

## 進捗管理ルール

### セッション実行中のTODO管理
- **作業開始時**: `pending` → `in_progress`に変更
- **実装完了時**: `in_progress`のまま保持（ユーザーレビュー待ち）
- **ユーザー承認時**: `in_progress` → `completed`に変更
- **中断時**: `in_progress` → `pending`に戻す

### セッション終了時の更新作業

**トリガーワード**: ユーザーが「**進捗管理更新**」と言ったら以下を実行：

1. **最新進捗mdファイル作成**
   - ファイル名形式: `YYYYMMDD_Phase11_[セッション内容サマリー].md`
   - 内容構成:
     - セッション概要
     - 主要成果
     - 技術的理解の向上
     - 次回セッション予定
     - **TODOリスト全体**（末尾に記載、ステータス含む）

2. **INDEX.md更新**
   - `learning_memos/INDEX.md`の「最優先参照」セクションを新ファイルに更新
   - 「進捗・成果記録」セクションに新ファイルを追加