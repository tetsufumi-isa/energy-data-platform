"""
メインETLパイプライン - データダウンロード→GCSアップロード統合処理

実行方法:
    python -m src.main_etl                    # デフォルト: 過去5日分
    python -m src.main_etl --days 7          # 過去7日分
    python -m src.main_etl --month 202505    # 指定月
    python -m src.main_etl --date 20250501   # 特定日
    python -m src.main_etl --bucket my-bucket # カスタムバケット
"""

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
    
    def __init__(self, base_dir="data/raw", bucket_name="energy-env-data"):
        """
        初期化
        
        Args:
            base_dir (str): ローカルデータ保存先
            bucket_name (str): GCSバケット名
        """
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
                'overall_status': 'failed',
                'message': 'ダウンロードに失敗したため、アップロードをスキップしました'
            }
        
        # Phase 2: Load (GCSアップロード)
        logger.info("Phase 2: Loading data to Google Cloud Storage")
        upload_results = self._upload_downloaded_data(download_results['success'])
        
        # 結果サマリー作成
        overall_status = 'success' if download_results['success'] and upload_results['success'] else 'partial'
        
        return {
            'download_results': download_results,
            'upload_results': upload_results,
            'overall_status': overall_status,
            'message': self._create_summary_message(download_results, upload_results)
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
                'overall_status': 'failed',
                'message': f'月{yyyymm}のダウンロードに失敗したため、アップロードをスキップしました'
            }
        
        # Phase 2: Load
        logger.info("Phase 2: Loading data to Google Cloud Storage")
        upload_results = self._upload_downloaded_data(download_results['success'])
        
        # 結果サマリー作成
        overall_status = 'success' if download_results['success'] and upload_results['success'] else 'partial'
        
        return {
            'download_results': download_results,
            'upload_results': upload_results,
            'overall_status': overall_status,
            'message': self._create_summary_message(download_results, upload_results)
        }
    
    def run_etl_for_date(self, date_str):
        """
        日付指定でETLパイプラインを実行
        
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
                'overall_status': 'failed',
                'message': f'日付{date_str}のダウンロードに失敗したため、アップロードをスキップしました'
            }
        
        # Phase 2: Load
        logger.info("Phase 2: Loading data to Google Cloud Storage")
        upload_results = self._upload_downloaded_data(download_results['success'])
        
        # 結果サマリー作成
        overall_status = 'success' if download_results['success'] and upload_results['success'] else 'partial'
        
        return {
            'download_results': download_results,
            'upload_results': upload_results,
            'overall_status': overall_status,
            'message': self._create_summary_message(download_results, upload_results)
        }
    
    def _upload_downloaded_data(self, successful_months):
        """
        ダウンロードされたデータをGCSにアップロード
        
        Args:
            successful_months (list): ダウンロード成功した月のリスト
            
        Returns:
            dict: アップロード結果
        """
        upload_results = {'success': [], 'failed': []}
        
        for month in successful_months:
            month_dir = self.base_dir / month
            
            if not month_dir.exists():
                logger.warning(f"Directory not found: {month_dir}")
                upload_results['failed'].append(month)
                continue
            
            try:
                # 月ディレクトリ内のCSVとZIPをアップロード
                destination_prefix = f"raw_data/{month}"
                
                # CSVファイルをアップロード
                csv_uris = self.uploader.upload_directory(
                    str(month_dir), 
                    destination_prefix,
                    file_extension=".csv"
                )
                
                # ZIPファイルを日付付きでバックアップアップロード
                today_str = datetime.today().strftime('%Y-%m-%d')
                zip_uris = self.uploader.upload_directory(
                    str(month_dir),
                    f"archives/{month}/{today_str}",  # 日付付きパス
                    file_extension=".zip"
                )
                
                uploaded_uris = csv_uris + zip_uris
                
                # 古いZIPバージョンをクリーンアップ
                self._cleanup_old_zip_versions()
                
                logger.info(f"Uploaded {len(uploaded_uris)} files for month {month}")
                upload_results['success'].append(month)
                
            except Exception as e:
                logger.error(f"Failed to upload data for month {month}: {e}")
                upload_results['failed'].append(month)
        
        return upload_results
    
    def _cleanup_old_zip_versions(self):
        """
        古いZIPバージョンをクリーンアップ
        今月と先月のアーカイブから2週間より古い（月末除く）ZIPファイルを削除
        """
        try:
            execution_date = datetime.today()
            cutoff_date = execution_date - timedelta(days=14)
            
            # 今月と先月をチェック
            current_month = execution_date.strftime('%Y%m')
            previous_month = (execution_date.replace(day=1) - timedelta(days=1)).strftime('%Y%m')
            
            months_to_check = {current_month, previous_month}
            
            logger.info(f"Starting ZIP cleanup for months: {sorted(months_to_check)}")
            
            total_deleted = 0
            total_kept = 0
            
            for month in months_to_check:
                # GCS上のZIPファイル一覧を取得
                archive_prefix = f"archives/{month}/"
                blobs = list(self.uploader.client.list_blobs(
                    self.uploader.bucket, 
                    prefix=archive_prefix
                ))
                
                if not blobs:
                    continue
                    
                deleted_count = 0
                kept_count = 0
                
                for blob in blobs:
                    if not blob.name.endswith('.zip'):
                        continue
                        
                    # ファイルパスから日付を抽出: archives/202506/2025-06-01/202506.zip
                    path_parts = blob.name.split('/')
                    if len(path_parts) < 3:
                        continue
                        
                    date_str = path_parts[2]  # "2025-06-01"
                    
                    try:
                        file_date = datetime.strptime(date_str, '%Y-%m-%d')
                    except ValueError:
                        continue  # 日付形式でない場合はスキップ
                    
                    # 削除判定と実行
                    # 基準日より古く、かつ月末日でない場合は削除
                    last_day_of_month = calendar.monthrange(file_date.year, file_date.month)[1]
                    if (file_date < cutoff_date and file_date.day != last_day_of_month):
                        blob.delete()
                        logger.info(f"Deleted old ZIP: {blob.name}")
                        deleted_count += 1
                    else:
                        kept_count += 1
                
                if deleted_count > 0:
                    logger.info(f"Month {month}: deleted {deleted_count} old ZIPs, kept {kept_count} ZIPs")
                
                total_deleted += deleted_count
                total_kept += kept_count
            
            if total_deleted > 0:
                logger.info(f"ZIP cleanup completed: deleted {total_deleted} files, kept {total_kept} files")
                
        except Exception as e:
            logger.warning(f"ZIP cleanup failed: {e}")
            # クリーンアップ失敗は全体の処理を止めない
    
    def _create_summary_message(self, download_results, upload_results):
        """
        実行結果のサマリーメッセージを作成
        
        Args:
            download_results (dict): ダウンロード結果
            upload_results (dict): アップロード結果
            
        Returns:
            str: サマリーメッセージ
        """
        dl_success = len(download_results['success'])
        dl_failed = len(download_results['failed'])
        up_success = len(upload_results['success'])
        up_failed = len(upload_results['failed'])
        
        if dl_success == 0:
            return "すべてのダウンロードに失敗しました"
        elif up_success == dl_success:
            return f"ETL完全成功: {dl_success}月分のデータを処理しました"
        elif up_success > 0:
            return f"ETL部分成功: ダウンロード{dl_success}月, アップロード{up_success}月"
        else:
            return f"ダウンロード成功({dl_success}月)、アップロード失敗"


def print_etl_results(results):
    """ETL実行結果を表示"""
    print(f"\n{'='*60}")
    print("📊 ETLパイプライン実行結果")
    print('='*60)
    
    # ダウンロード結果
    print("\n🔽 Extract (ダウンロード)")
    dl_results = results['download_results']
    if dl_results['success']:
        print(f"✅ 成功: {', '.join(dl_results['success'])}")
    if dl_results['failed']:
        print(f"❌ 失敗: {', '.join(dl_results['failed'])}")
    
    # アップロード結果
    print("\n🔼 Load (アップロード)")
    up_results = results['upload_results']
    if up_results['success']:
        print(f"✅ 成功: {', '.join(up_results['success'])}")
    if up_results['failed']:
        print(f"❌ 失敗: {', '.join(up_results['failed'])}")
    
    # 総合結果
    status_emoji = {
        'success': '🎉',
        'partial': '⚠️',
        'failed': '💥'
    }
    
    print(f"\n📋 総合結果")
    print(f"{status_emoji[results['overall_status']]} {results['message']}")
    print('='*60)


def main():
    """メイン関数"""
    # ログ設定を初期化
    setup_logging()
    
    parser = argparse.ArgumentParser(description='メインETLパイプライン - データダウンロード→GCSアップロード')
    parser.add_argument('--days', type=int, default=5,
                       help='今日から遡る日数 (デフォルト: 5)')
    parser.add_argument('--month', type=str,
                       help='指定月をダウンロード (YYYYMM形式)')
    parser.add_argument('--date', type=str,
                       help='特定日をダウンロード (YYYYMMDD形式)')
    parser.add_argument('--base-dir', type=str, default='data/raw',
                       help='ローカル保存先ディレクトリ (デフォルト: data/raw)')
    parser.add_argument('--bucket', type=str, default='energy-env-data',
                       help='GCSバケット名 (デフォルト: energy-env-data)')
    
    args = parser.parse_args()
    
    # 実行モード判定と排他チェックを一括処理
    if args.month and args.date:
        print("❌ エラー: --month と --date は同時に指定できません")
        return
    elif args.month and (args.days != 5):
        print("❌ エラー: --month と --days は同時に指定できません")
        return
    elif args.date and (args.days != 5):
        print("❌ エラー: --date と --days は同時に指定できません")
        return
    
    # ETLパイプライン初期化
    pipeline = MainETLPipeline(args.base_dir, args.bucket)
    
    print("🚀 メインETLパイプライン開始")
    print(f"📂 ローカル保存先: {args.base_dir}")
    print(f"☁️  GCSバケット: gs://{args.bucket}")
    
    try:
        # 実行モード判定とETL実行
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
        print_etl_results(results)
        
    except Exception as e:
        logger.error(f"ETL pipeline failed: {e}")
        print(f"💥 ETLパイプライン実行エラー: {e}")
        return
    
    print("🏁 ETLパイプライン完了")


if __name__ == "__main__":
    main()