"""
メインETLパイプライン - 日次データ取得・投入・予測統合処理

日次自動実行用：
1. 電力データ（過去5日分）取得・BigQuery投入
2. 気象データ（過去10日+予測14日）取得・BigQuery投入
3. ml_features更新（過去7日分の学習データ再構築）
4. データ品質チェック（直近7日分）
5. 予測実行（今日から14日間）・CSV/BigQuery保存
6. prediction_accuracy更新（予測精度分析テーブル更新）
7. ダッシュボードデータ更新（Looker Studio用統合テーブル）
8. システム監視ステータス更新（Looker Studio監視ページ用）

実行方法:
    python -m src.pipelines.main_etl

Note:
    個別の柔軟な実行（特定月・特定日・カスタムパラメータ）は各モジュールを直接実行してください：
    - 電力データ: src.data_processing.data_downloader
    - 気象データ: src.data_processing.weather_downloader
    - BQ投入: src.data_processing.power_bigquery_loader, weather_bigquery_loader
    - ml_features更新: src.data_processing.ml_features_updater
    - 品質チェック: src.monitoring.data_quality_checker
    - 予測実行: src.prediction.prediction_iterative_with_export
    - 予測精度更新: src.data_processing.prediction_accuracy_updater
    - ダッシュボード更新: src.data_processing.dashboard_data_updater
    - システム監視更新: src.data_processing.system_status_updater
"""

import subprocess
import sys


def main():
    """メイン関数 - 日次ETLパイプライン実行（CLI実行方式）"""
    print("メインETLパイプライン開始（電力+気象+ml_features+品質チェック+予測+精度分析+ダッシュボード更新+監視ステータス更新統合版）")
    print("処理内容:")
    print("  - 電力データ（過去5日分）取得・BQ投入")
    print("  - 気象データ（過去10日+予測14日）取得・BQ投入")
    print("  - ml_features更新（過去7日分の学習データ再構築）")
    print("  - データ品質チェック（直近7日分）")
    print("  - 予測実行（今日から14日間）・結果保存")
    print("  - prediction_accuracy更新（予測精度分析テーブル更新）")
    print("  - ダッシュボードデータ更新（Looker Studio用）")
    print("  - システム監視ステータス更新（Looker Studio監視ページ用）")
    print()

    # Phase 1: 電力データダウンロード
    print("Phase 1: 電力データダウンロード")
    result = subprocess.run([sys.executable, '-m', 'src.data_processing.data_downloader', '--days', '5'])
    if result.returncode != 0:
        print("Phase 1 失敗: 電力データダウンロードエラー")
        sys.exit(1)
    print()

    # Phase 2: 気象データダウンロード
    print("Phase 2: 気象データダウンロード")
    result = subprocess.run([sys.executable, '-m', 'src.data_processing.weather_downloader'])
    if result.returncode != 0:
        print("Phase 2 失敗: 気象データダウンロードエラー")
        sys.exit(1)
    print()

    # Phase 3: 電力データBigQuery投入
    print("Phase 3: 電力データBigQuery投入")
    result = subprocess.run([sys.executable, '-m', 'src.data_processing.power_bigquery_loader', '--days', '5'])
    if result.returncode != 0:
        print("Phase 3 失敗: 電力データBQ投入エラー")
        sys.exit(1)
    print()

    # Phase 4-1: 気象データBigQuery投入（過去データ）
    print("Phase 4-1: 気象データBigQuery投入（過去データ）")
    result = subprocess.run([sys.executable, '-m', 'src.data_processing.weather_bigquery_loader', '--data-type', 'historical'])
    if result.returncode != 0:
        print("Phase 4-1 失敗: 気象過去データBQ投入エラー")
        sys.exit(1)
    print()

    # Phase 4-2: 気象データBigQuery投入（予測データ）
    print("Phase 4-2: 気象データBigQuery投入（予測データ）")
    result = subprocess.run([sys.executable, '-m', 'src.data_processing.weather_bigquery_loader', '--data-type', 'forecast'])
    if result.returncode != 0:
        print("Phase 4-2 失敗: 気象予測データBQ投入エラー")
        sys.exit(1)
    print()

    # Phase 5: ml_features更新
    print("Phase 5: ml_features更新（過去7日分の学習データ再構築）")
    result = subprocess.run([sys.executable, '-m', 'src.data_processing.ml_features_updater'])
    if result.returncode != 0:
        print("Phase 5 失敗: ml_features更新エラー")
        sys.exit(1)
    print()

    # Phase 6: データ品質チェック
    print("Phase 6: データ品質チェック（直近7日分）")
    result = subprocess.run([sys.executable, '-m', 'src.monitoring.data_quality_checker', '--days', '7'])
    if result.returncode != 0:
        print("Phase 6 失敗: データ品質チェックエラー")
        sys.exit(1)
    print()

    # Phase 7: 予測実行
    print("Phase 7: 予測実行（今日から14日間）")
    result = subprocess.run([sys.executable, '-m', 'src.prediction.prediction_iterative_with_export'])
    if result.returncode != 0:
        print("Phase 7 失敗: 予測実行エラー")
        sys.exit(1)
    print()

    # Phase 8: prediction_accuracy更新
    print("Phase 8: prediction_accuracy更新（予測精度分析テーブル更新）")
    result = subprocess.run([sys.executable, '-m', 'src.data_processing.prediction_accuracy_updater'])
    if result.returncode != 0:
        print("Phase 8 失敗: prediction_accuracy更新エラー")
        sys.exit(1)
    print()

    # Phase 9: ダッシュボードデータ更新
    print("Phase 9: ダッシュボードデータ更新（Looker Studio用）")
    result = subprocess.run([sys.executable, '-m', 'src.data_processing.dashboard_data_updater'])
    if result.returncode != 0:
        print("Phase 9 失敗: ダッシュボードデータ更新エラー")
        sys.exit(1)
    print()

    # Phase 10: システム監視ステータス更新
    print("Phase 10: システム監視ステータス更新（Looker Studio監視ページ用）")
    result = subprocess.run([sys.executable, '-m', 'src.data_processing.system_status_updater'])
    if result.returncode != 0:
        print("Phase 10 失敗: システム監視ステータス更新エラー")
        sys.exit(1)
    print()

    print("メインETLパイプライン完了 - 全Phase成功")
    print("詳細ログはBigQuery process_execution_log テーブルを参照")
    print("処理完了")


if __name__ == "__main__":
    main()
