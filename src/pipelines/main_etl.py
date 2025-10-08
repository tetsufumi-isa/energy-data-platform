"""
メインETLパイプライン - 日次データ取得・投入統合処理

日次自動実行用：電力データ（過去5日分）+ 気象データ（過去10日+予測16日）をダウンロードし、
GCS・BigQueryに投入する。

実行方法:
    python -m src.pipelines.main_etl

Note:
    個別の柔軟な実行（特定月・特定日・カスタムパラメータ）は各モジュールを直接実行してください：
    - 電力データ: src.data_processing.data_downloader
    - 気象データ: src.data_processing.weather_downloader
    - BQ投入: src.data_processing.power_bigquery_loader, weather_bigquery_loader
"""

import os
from pathlib import Path
from logging import getLogger

from src.data_processing.data_downloader import PowerDataDownloader
from src.data_processing.gcs_uploader import GCSUploader
from src.data_processing.weather_downloader import WeatherDownloader
from src.data_processing.weather_bigquery_loader import WeatherBigQueryLoader
from src.data_processing.power_bigquery_loader import PowerBigQueryLoader
from src.utils.logging_config import setup_logging

# モジュール専用のロガーを取得
logger = getLogger('energy_env.main_etl')

class MainETLPipeline:
    """メインETLパイプライン - Extract + Load統合処理"""
    
    def __init__(self, base_dir=None, bucket_name="energy-env-data", project_id="energy-env"):
        """
        初期化

        Args:
            base_dir (str): ローカルデータ保存先（電力データ用）
                          Noneの場合は環境変数ENERGY_ENV_PATHから取得
            bucket_name (str): GCSバケット名
            project_id (str): GCPプロジェクトID
        """
        if base_dir is None:
            energy_env_path = os.getenv('ENERGY_ENV_PATH')
            if energy_env_path is None:
                raise ValueError("ENERGY_ENV_PATH environment variable is not set")
            base_dir = os.path.join(energy_env_path, 'data', 'raw')

        self.base_dir = Path(base_dir)
        self.bucket_name = bucket_name
        self.project_id = project_id

        # 電力データコンポーネント
        self.power_downloader = PowerDataDownloader(str(self.base_dir))
        self.uploader = GCSUploader(bucket_name)
        self.power_bq_loader = PowerBigQueryLoader(project_id, str(self.base_dir))

        # 気象データコンポーネント
        self.weather_downloader = WeatherDownloader()
        self.weather_bq_loader = WeatherBigQueryLoader(project_id)

        logger.info(f"MainETLPipeline initialized: {base_dir} → gs://{bucket_name}")
    
    def run_etl_for_days(self, days=5):
        """
        日数指定でETLパイプラインを実行（電力+気象データ統合版）

        Args:
            days (int): 今日から遡る日数

        Returns:
            dict: 実行結果サマリー
        """
        logger.info(f"Starting ETL pipeline for {days} days")

        # Phase 1: Extract (データダウンロード)
        logger.info("Phase 1: Extracting data (Power + Weather)")

        # 1-1. 電力データダウンロード
        logger.info("Phase 1-1: Downloading power data from TEPCO website")
        power_download_results = self.power_downloader.download_for_days(days)

        # 1-2. 気象データダウンロード
        logger.info("Phase 1-2: Downloading weather data from Open-Meteo API")
        try:
            weather_download_results = self.weather_downloader.download_daily_weather_data()
            weather_download_success = True
        except Exception as e:
            logger.error(f"Weather data download failed: {e}")
            weather_download_results = None
            weather_download_success = False

        # Phase 2: Load to GCS (電力データのみ)
        logger.info("Phase 2: Loading power data to Google Cloud Storage")
        if power_download_results['success']:
            upload_results = self._upload_downloaded_data(power_download_results['success'])
        else:
            logger.warning("No power data downloaded. Skipping GCS upload.")
            upload_results = {'success': [], 'failed': []}

        # Phase 3: Load to BigQuery
        logger.info("Phase 3: Loading data to BigQuery (Power + Weather)")

        # 3-1. 電力データBQ投入
        logger.info("Phase 3-1: Loading power data to BigQuery")
        try:
            power_bq_results = self.power_bq_loader.load_power_data(days)
            power_bq_success = power_bq_results['status'] == 'success'
        except Exception as e:
            logger.error(f"Power data BQ load failed: {e}")
            power_bq_results = {'status': 'failed', 'message': str(e), 'files_processed': 0, 'rows_inserted': 0}
            power_bq_success = False

        # 3-2. 気象データBQ投入（historical + forecast）
        weather_bq_results = {'historical': None, 'forecast': None}
        weather_bq_success = False

        if weather_download_success:
            logger.info("Phase 3-2: Loading weather data to BigQuery")

            # Historical データ投入
            try:
                weather_bq_results['historical'] = self.weather_bq_loader.load_weather_data('historical')
                historical_success = weather_bq_results['historical']['status'] == 'success'
            except Exception as e:
                logger.error(f"Weather historical data BQ load failed: {e}")
                weather_bq_results['historical'] = {'status': 'failed', 'message': str(e), 'files_processed': 0, 'rows_inserted': 0}
                historical_success = False

            # Forecast データ投入
            try:
                weather_bq_results['forecast'] = self.weather_bq_loader.load_weather_data('forecast')
                forecast_success = weather_bq_results['forecast']['status'] == 'success'
            except Exception as e:
                logger.error(f"Weather forecast data BQ load failed: {e}")
                weather_bq_results['forecast'] = {'status': 'failed', 'message': str(e), 'files_processed': 0, 'rows_inserted': 0}
                forecast_success = False

            weather_bq_success = historical_success and forecast_success
        else:
            logger.warning("Weather data download failed. Skipping weather BQ load.")

        # 結果サマリー作成
        summary = self._create_summary_integrated(
            power_download_results,
            upload_results,
            power_bq_results,
            weather_download_success,
            weather_bq_success
        )
        logger.info(f"ETL pipeline completed: {summary}")

        return {
            'power_download_results': power_download_results,
            'weather_download_results': weather_download_results,
            'upload_results': upload_results,
            'power_bq_results': power_bq_results,
            'weather_bq_results': weather_bq_results,
            'summary': summary
        }
    
    def _upload_downloaded_data(self, successful_months):
        """
        ダウンロード済みデータをGCSにアップロード
        
        Args:
            successful_months (list): ダウンロード成功した月のリスト
            
        Returns:
            dict: アップロード結果
        """
        upload_results = {'success': [], 'failed': []}
        
        for month in successful_months:
            try:
                month_dir = self.base_dir / month
                
                # CSV ファイルを検索
                csv_files = list(month_dir.glob("*.csv"))
                
                if not csv_files:
                    logger.warning(f"No CSV files found in {month_dir}")
                    upload_results['failed'].append({
                        'month': month,
                        'error': 'No CSV files found'
                    })
                    continue
                
                # 各CSVファイルをアップロード
                month_success = True
                for csv_file in csv_files:
                    try:
                        gcs_file_name = f"raw_data/{month}/{csv_file.name}"
                        uri = self.uploader.upload_file(str(csv_file), gcs_file_name)
                        logger.info(f"Successfully uploaded {csv_file.name} to {uri}")
                    except Exception as e:
                        logger.error(f"Failed to upload {csv_file}: {e}")
                        month_success = False
                
                if month_success:
                    upload_results['success'].append(month)
                else:
                    upload_results['failed'].append({
                        'month': month,
                        'error': 'One or more CSV files failed to upload'
                    })
                    
            except Exception as e:
                logger.error(f"Failed to process month {month}: {e}")
                upload_results['failed'].append({
                    'month': month,
                    'error': str(e)
                })
        
        return upload_results
    
    def _create_summary_integrated(self, power_download_results, upload_results,
                                    power_bq_results, weather_download_success, weather_bq_success):
        """
        実行結果のサマリーを作成（電力+気象データ統合版）

        Args:
            power_download_results (dict): 電力データダウンロード結果
            upload_results (dict): GCSアップロード結果
            power_bq_results (dict): 電力データBQ投入結果
            weather_download_success (bool): 気象データダウンロード成功フラグ
            weather_bq_success (bool): 気象データBQ投入成功フラグ

        Returns:
            str: サマリー文字列
        """
        power_download_success = len(power_download_results['success']) > 0
        power_bq_success = power_bq_results['status'] == 'success'
        upload_success = len(upload_results['success']) > 0

        success_components = []
        failure_components = []

        # 電力データ
        if power_download_success and upload_success and power_bq_success:
            success_components.append("電力データ完了")
        else:
            if not power_download_success:
                failure_components.append("電力ダウンロード失敗")
            if not upload_success:
                failure_components.append("GCSアップロード失敗")
            if not power_bq_success:
                failure_components.append("電力BQ投入失敗")

        # 気象データ
        if weather_download_success and weather_bq_success:
            success_components.append("気象データ完了")
        else:
            if not weather_download_success:
                failure_components.append("気象ダウンロード失敗")
            if weather_download_success and not weather_bq_success:
                failure_components.append("気象BQ投入失敗")

        # サマリー文字列生成
        if not failure_components:
            return f"完全成功: {', '.join(success_components)}"
        elif success_components:
            return f"部分成功: {', '.join(success_components)} / {', '.join(failure_components)}"
        else:
            return f"失敗: {', '.join(failure_components)}"


def print_results(results):
    """実行結果を表示（電力+気象データ統合版）"""
    print(f"\n{'='*60}")
    print("📊 ETLパイプライン実行結果（電力+気象データ）")
    print('='*60)

    # 電力データダウンロード結果
    if 'power_download_results' in results:
        power_download_results = results['power_download_results']
        print("\n📥 電力データダウンロード結果:")
        if power_download_results['success']:
            print(f"  ✅ 成功: {', '.join(power_download_results['success'])}")
        if power_download_results['failed']:
            print(f"  ❌ 失敗: {', '.join(power_download_results['failed'])}")

    # 気象データダウンロード結果
    if 'weather_download_results' in results and results['weather_download_results']:
        print("\n🌤️ 気象データダウンロード結果:")
        weather_results = results['weather_download_results']
        if 'historical' in weather_results and weather_results['historical']:
            print(f"  ✅ 過去データ: {len(weather_results['historical'])}件")
        if 'forecast' in weather_results and weather_results['forecast']:
            print(f"  ✅ 予測データ: {len(weather_results['forecast'])}件")

    # GCSアップロード結果
    if 'upload_results' in results:
        upload_results = results['upload_results']
        print("\n📤 GCSアップロード結果（電力データ）:")
        if upload_results['success']:
            print(f"  ✅ 成功: {', '.join(upload_results['success'])}")
        if upload_results['failed']:
            print("  ❌ 失敗:")
            for item in upload_results['failed']:
                if isinstance(item, dict):
                    print(f"    {item['month']}: {item['error']}")
                else:
                    print(f"    {item}")

    # BigQuery投入結果（電力）
    if 'power_bq_results' in results and results['power_bq_results']:
        power_bq = results['power_bq_results']
        print("\n💾 BigQuery投入結果（電力データ）:")
        status_mark = '✅' if power_bq['status'] == 'success' else '❌'
        print(f"  {status_mark} ステータス: {power_bq['status']}")
        print(f"  📁 処理ファイル数: {power_bq['files_processed']}")
        print(f"  📊 投入レコード数: {power_bq['rows_inserted']}")

    # BigQuery投入結果（気象）
    if 'weather_bq_results' in results and results['weather_bq_results']:
        weather_bq = results['weather_bq_results']
        print("\n💾 BigQuery投入結果（気象データ）:")

        if weather_bq.get('historical'):
            hist = weather_bq['historical']
            status_mark = '✅' if hist['status'] == 'success' else '❌'
            print(f"  {status_mark} 過去データ: {hist['rows_inserted']}行投入")

        if weather_bq.get('forecast'):
            fore = weather_bq['forecast']
            status_mark = '✅' if fore['status'] == 'success' else '❌'
            print(f"  {status_mark} 予測データ: {fore['rows_inserted']}行投入")

    # サマリー
    print(f"\n📈 総合結果: {results['summary']}")
    print('='*60)


def main():
    """メイン関数 - 日次ETLパイプライン実行"""
    # ログ設定を初期化
    setup_logging()

    print("🚀 メインETLパイプライン開始（電力+気象データ統合版）")
    print("📊 処理内容: 電力データ（過去5日分）+ 気象データ（過去10日+予測16日）")

    # ETLパイプライン初期化
    try:
        pipeline = MainETLPipeline()
    except ValueError as e:
        print(f"❌ エラー: {e}")
        print("   ENERGY_ENV_PATH環境変数を設定してください")
        return

    print(f"📂 ローカル保存先: {pipeline.base_dir}")
    print(f"☁️  GCSバケット: gs://{pipeline.bucket_name}")
    print(f"🔧 GCPプロジェクト: {pipeline.project_id}")

    # 日次ETLパイプライン実行
    try:
        results = pipeline.run_etl_for_days(days=5)

        # 結果表示
        print_results(results)

    except Exception as e:
        logger.error(f"ETL pipeline failed: {e}")
        print(f"💥 ETLパイプライン実行エラー: {e}")
        return

    print("🏁 メインETLパイプライン完了")


if __name__ == "__main__":
    main()