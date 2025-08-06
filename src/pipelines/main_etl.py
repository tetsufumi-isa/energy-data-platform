"""
メインETLパイプライン - データダウンロード→GCSアップロード統合処理

実行方法:
    python -m src.pipelines.main_etl                    # デフォルト: 過去5日分
    python -m src.pipelines.main_etl --days 7          # 過去7日分
    python -m src.pipelines.main_etl --month 202505    # 指定月
    python -m src.pipelines.main_etl --date 20250501   # 特定日
    python -m src.pipelines.main_etl --bucket my-bucket # カスタムバケット
"""

import os
import argparse
import calendar
from datetime import datetime, timedelta
from pathlib import Path
from logging import getLogger

from src.data_processing.data_downloader import PowerDataDownloader
from src.data_processing.gcs_uploader import GCSUploader
from src.utils.logging_config import setup_logging

# モジュール専用のロガーを取得
logger = getLogger('energy_env.main_etl')

class MainETLPipeline:
    """メインETLパイプライン - Extract + Load統合処理"""
    
    def __init__(self, base_dir=None, bucket_name="energy-env-data"):
        """
        初期化
        
        Args:
            base_dir (str): ローカルデータ保存先
                          Noneの場合は環境変数ENERGY_ENV_PATHから取得
            bucket_name (str): GCSバケット名
        """
        if base_dir is None:
            energy_env_path = os.getenv('ENERGY_ENV_PATH')
            if energy_env_path is None:
                raise ValueError("ENERGY_ENV_PATH environment variable is not set")
            base_dir = os.path.join(energy_env_path, 'data', 'raw')
        
        self.base_dir = Path(base_dir)
        self.bucket_name = bucket_name
        
        # 各コンポーネントを初期化
        self.downloader = PowerDataDownloader(str(self.base_dir))
        self.uploader = GCSUploader(bucket_name)
        
        logger.info(f"MainETLPipeline initialized: {base_dir} → gs://{bucket_name}")
    
    def run_etl_for_days(self, days=5):
        """
        日数指定でETLパイプラインを実行
        
        Args:
            days (int): 今日から遡る日数
            
        Returns:
            dict: 実行結果サマリー
        """
        logger.info(f"Starting ETL pipeline for {days} days")
        
        # Phase 1: Extract (データダウンロード)
        logger.info("Phase 1: Extracting data from TEPCO website")
        download_results = self.downloader.download_for_days(days)
        
        if not download_results['success']:
            logger.warning("No data downloaded successfully. Skipping upload phase.")
            return {
                'download_results': download_results,
                'upload_results': {'success': [], 'failed': []},
                'summary': 'Failed: No data downloaded'
            }
        
        # Phase 2: Load (GCSアップロード)
        logger.info("Phase 2: Loading data to Google Cloud Storage")
        upload_results = self._upload_downloaded_data(download_results['success'])
        
        # 結果サマリー作成
        summary = self._create_summary(download_results, upload_results)
        logger.info(f"ETL pipeline completed: {summary}")
        
        return {
            'download_results': download_results,
            'upload_results': upload_results,
            'summary': summary
        }
    
    def run_etl_for_month(self, yyyymm):
        """
        月指定でETLパイプラインを実行
        
        Args:
            yyyymm (str): 年月 (YYYYMM形式)
            
        Returns:
            dict: 実行結果サマリー
        """
        logger.info(f"Starting ETL pipeline for month {yyyymm}")
        
        # Phase 1: Extract
        logger.info("Phase 1: Extracting data from TEPCO website")
        download_results = self.downloader.download_for_month(yyyymm)
        
        if not download_results['success']:
            logger.warning(f"No data downloaded for month {yyyymm}. Skipping upload phase.")
            return {
                'download_results': download_results,
                'upload_results': {'success': [], 'failed': []},
                'summary': f'Failed: No data downloaded for {yyyymm}'
            }
        
        # Phase 2: Load
        logger.info("Phase 2: Loading data to Google Cloud Storage")
        upload_results = self._upload_downloaded_data(download_results['success'])
        
        # 結果サマリー作成
        summary = self._create_summary(download_results, upload_results)
        logger.info(f"ETL pipeline completed: {summary}")
        
        return {
            'download_results': download_results,
            'upload_results': upload_results,
            'summary': summary
        }
    
    def run_etl_for_date(self, date_str):
        """
        特定日でETLパイプラインを実行
        
        Args:
            date_str (str): 日付文字列 (YYYYMMDD形式)
            
        Returns:
            dict: 実行結果サマリー
        """
        logger.info(f"Starting ETL pipeline for date {date_str}")
        
        # Phase 1: Extract
        logger.info("Phase 1: Extracting data from TEPCO website")
        download_results = self.downloader.download_for_date(date_str)
        
        if not download_results['success']:
            logger.warning(f"No data downloaded for date {date_str}. Skipping upload phase.")
            return {
                'download_results': download_results,
                'upload_results': {'success': [], 'failed': []},
                'summary': f'Failed: No data downloaded for {date_str}'
            }
        
        # Phase 2: Load
        logger.info("Phase 2: Loading data to Google Cloud Storage")
        upload_results = self._upload_downloaded_data(download_results['success'])
        
        # 結果サマリー作成
        summary = self._create_summary(download_results, upload_results)
        logger.info(f"ETL pipeline completed: {summary}")
        
        return {
            'download_results': download_results,
            'upload_results': upload_results,
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
    
    def _create_summary(self, download_results, upload_results):
        """
        実行結果のサマリーを作成
        
        Args:
            download_results (dict): ダウンロード結果
            upload_results (dict): アップロード結果
            
        Returns:
            str: サマリー文字列
        """
        download_success = len(download_results['success'])
        download_failed = len(download_results['failed'])
        upload_success = len(upload_results['success'])
        upload_failed = len(upload_results['failed'])
        
        if download_failed == 0 and upload_failed == 0:
            return f"Success: {download_success} months downloaded and uploaded"
        elif download_failed > 0 and upload_failed == 0:
            return f"Partial Success: {download_success} downloaded, {download_failed} download failed"
        elif download_failed == 0 and upload_failed > 0:
            return f"Partial Success: {download_success} downloaded, {upload_failed} upload failed"
        else:
            return f"Partial Success: {download_success} completed, {download_failed} download failed, {upload_failed} upload failed"


def print_results(results):
    """実行結果を表示"""
    print(f"\n{'='*60}")
    print("📊 ETLパイプライン実行結果")
    print('='*60)
    
    # ダウンロード結果
    download_results = results['download_results']
    print("\n📥 データダウンロード結果:")
    if download_results['success']:
        print(f"  ✅ 成功: {', '.join(download_results['success'])}")
    if download_results['failed']:
        print(f"  ❌ 失敗: {', '.join(download_results['failed'])}")
    
    # アップロード結果
    upload_results = results['upload_results']
    print("\n📤 GCSアップロード結果:")
    if upload_results['success']:
        print(f"  ✅ 成功: {', '.join(upload_results['success'])}")
    if upload_results['failed']:
        print("  ❌ 失敗:")
        for item in upload_results['failed']:
            if isinstance(item, dict):
                print(f"    {item['month']}: {item['error']}")
            else:
                print(f"    {item}")
    
    # サマリー
    print(f"\n📈 総合結果: {results['summary']}")
    print('='*60)


def main():
    """メイン関数"""
    # ログ設定を初期化
    setup_logging()
    
    # デフォルトのbase_dirを環境変数から取得
    energy_env_path = os.getenv('ENERGY_ENV_PATH')
    if energy_env_path is None:
        default_base_dir = 'data/raw'  # 環境変数が設定されていない場合のフォールバック
        print("⚠️  警告: ENERGY_ENV_PATH環境変数が設定されていません。相対パスを使用します。")
    else:
        default_base_dir = os.path.join(energy_env_path, 'data', 'raw')
    
    parser = argparse.ArgumentParser(description='メインETLパイプライン')
    parser.add_argument('--days', type=int, default=5,
                       help='今日から遡る日数 (デフォルト: 5)')
    parser.add_argument('--month', type=str,
                       help='指定月を処理 (YYYYMM形式)')
    parser.add_argument('--date', type=str,
                       help='特定日を処理 (YYYYMMDD形式)')
    parser.add_argument('--base-dir', type=str, default=default_base_dir,
                       help=f'ローカルデータ保存先 (デフォルト: {default_base_dir})')
    parser.add_argument('--bucket', type=str, default='energy-env-data',
                       help='GCSバケット名 (デフォルト: energy-env-data)')
    
    args = parser.parse_args()
    
    # 引数の排他チェック
    specified_args = [
        bool(args.month),
        bool(args.date),
        args.days != 5  # デフォルト値以外が指定された場合
    ]
    
    if sum(specified_args) > 1:
        print("❌ エラー: --days, --month, --date は同時に指定できません")
        print("   1つの実行で1つの処理のみ可能です")
        return
    
    # ETLパイプライン初期化
    try:
        pipeline = MainETLPipeline(args.base_dir, args.bucket)
    except ValueError as e:
        print(f"❌ エラー: {e}")
        print("   ENERGY_ENV_PATH環境変数を設定してください")
        return
    
    print("🚀 メインETLパイプライン開始")
    print(f"📂 ローカル保存先: {pipeline.base_dir}")
    print(f"☁️  GCSバケット: gs://{pipeline.bucket_name}")
    
    # 実行モード判定と処理実行
    try:
        if args.month:
            print(f"📅 指定月モード: {args.month}")
            results = pipeline.run_etl_for_month(args.month)
        elif args.date:
            print(f"📅 特定日モード: {args.date}")
            results = pipeline.run_etl_for_date(args.date)
        else:
            print(f"📅 日数指定モード: 過去{args.days}日分")
            results = pipeline.run_etl_for_days(args.days)
        
        # 結果表示
        print_results(results)
        
    except Exception as e:
        logger.error(f"ETL pipeline failed: {e}")
        print(f"💥 ETLパイプライン実行エラー: {e}")
        return
    
    print("🏁 メインETLパイプライン完了")


if __name__ == "__main__":
    main()