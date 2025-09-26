"""
東京電力でんき予報データダウンローダー

実行方法:
    python -m src.data_processing.data_downloader              # デフォルト: 過去5日分
    python -m src.data_processing.data_downloader --days 7     # 過去7日分
    python -m src.data_processing.data_downloader --month 202505  # 指定月
    python -m src.data_processing.data_downloader --date 20250501  # 特定日
"""

import os
import zipfile
import requests
import argparse
import uuid
import json
from datetime import datetime, timedelta
from pathlib import Path
from google.cloud import bigquery

class PowerDataDownloader:
    """東京電力でんき予報データダウンローダー"""
    
    BASE_URL = "https://www.tepco.co.jp/forecast/html/images"
    
    def __init__(self, base_dir=None):
        """
        初期化

        Args:
            base_dir (str): データ保存先のベースディレクトリ
                          Noneの場合は環境変数ENERGY_ENV_PATHから取得
        """
        if base_dir is None:
            energy_env_path = os.getenv('ENERGY_ENV_PATH')
            if energy_env_path is None:
                raise ValueError("ENERGY_ENV_PATH environment variable is not set")
            base_dir = os.path.join(energy_env_path, 'data', 'raw')
            self.log_dir = Path(energy_env_path) / 'logs' / 'tepco_api'
        else:
            self.log_dir = Path(base_dir).parent.parent / 'logs' / 'tepco_api'

        self.base_dir = Path(base_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # BigQuery設定
        self.bq_client = bigquery.Client()
        self.bq_table_id = "energy-env.prod_energy_data.process_execution_log"

        print(f"PowerDataDownloader initialized with base_dir: {self.base_dir}")

    def _write_log(self, log_data):
        """
        ログをローカルファイルとBigQueryに記録

        Args:
            log_data (dict): ログデータ
        """
        # ローカルファイルに記録
        log_date = log_data.get('date', datetime.now().strftime('%Y-%m-%d'))
        log_file = self.log_dir / f"{log_date}_tepco_execution.jsonl"

        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_data, ensure_ascii=False) + '\n')
        except Exception as e:
            print(f"Failed to write log file: {e}")

        # BigQueryに記録
        try:
            self.bq_client.insert_rows_json(self.bq_table_id, [log_data])
        except Exception as e:
            print(f"Failed to write to BigQuery (saved to file): {e}")

    def get_required_months(self, days=5):
        """
        指定日数分の日付から必要な月のセットを取得
        
        Args:
            days (int): 今日から遡る日数（デフォルト: 5）
            
        Returns:
            set: 必要な月の文字列セット (例: {'202504', '202505'})
        """
        today = datetime.today()
        dates = [today - timedelta(days=i) for i in range(days + 1)]
        months = {date.strftime('%Y%m') for date in dates}

        print(f"Required months for {days} days: {sorted(months)}")
        return months
    
    def get_months_from_date(self, date_str):
        """
        特定日から必要な月を取得
        
        Args:
            date_str (str): 日付文字列 (YYYYMMDD形式)
            
        Returns:
            set: 月の文字列セット
        """
        try:
            date = datetime.strptime(date_str, '%Y%m%d')
        except ValueError as e:
            print(f"Invalid date format {date_str}: {e}")
            raise ValueError(f"日付はYYYYMMDD形式で入力してください: {date_str}")

        # 未来日付チェック
        if date.date() > datetime.today().date():
            today_str = datetime.today().strftime('%Y%m%d')
            raise ValueError(f"未来の日付は指定できません: {date_str} (今日: {today_str})")

        month = date.strftime('%Y%m')
        print(f"Month for date {date_str}: {month}")
        return {month}
    
    def download_month_data(self, yyyymm, target_date=None):
        """
        指定月のデータをダウンロード・解凍

        Args:
            yyyymm (str): 年月 (YYYYMM形式)
            target_date (str): 対象日付 (YYYY-MM-DD形式、ログ用)

        Returns:
            bool: ダウンロード成功時True

        Raises:
            requests.exceptions.RequestException: ダウンロードエラー
        """
        execution_id = str(uuid.uuid4())
        started_at = datetime.now()
        url = f"{self.BASE_URL}/{yyyymm}_power_usage.zip"
        month_dir = self.base_dir / yyyymm
        zip_path = month_dir / f"{yyyymm}.zip"

        # 対象日付が指定されていない場合は今日を使用
        if target_date is None:
            target_date = datetime.now().strftime('%Y-%m-%d')

        print(f"Downloading: {url}")

        try:
            # ディレクトリ作成
            month_dir.mkdir(parents=True, exist_ok=True)

            # ZIPダウンロード
            response = requests.get(url, timeout=30)
            response.raise_for_status()

            # ZIP保存
            with open(zip_path, 'wb') as f:
                f.write(response.content)

            # ZIP解凍
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(month_dir)

            # 成功ログ記録
            completed_at = datetime.now()
            file_size_mb = round(zip_path.stat().st_size / 1024 / 1024, 2)
            duration_seconds = int((completed_at - started_at).total_seconds())

            log_data = {
                "execution_id": execution_id,
                "date": target_date,
                "process_type": "TEPCO_API",
                "status": "SUCCESS",
                "error_message": None,
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
                "duration_seconds": duration_seconds,
                "records_processed": None,
                "file_size_mb": file_size_mb,
                "additional_info": {"month": yyyymm, "url": url}
            }

            self._write_log(log_data)
            print(f"Successfully downloaded and extracted {yyyymm} data to {month_dir}")
            return True

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                # 404エラーは警告レベル（データ未公開）
                completed_at = datetime.now()
                duration_seconds = int((completed_at - started_at).total_seconds())

                log_data = {
                    "execution_id": execution_id,
                    "date": target_date,
                    "process_type": "TEPCO_API",
                    "status": "FAILED",
                    "error_message": f"Data for {yyyymm} not yet available (404)",
                    "started_at": started_at.isoformat(),
                    "completed_at": completed_at.isoformat(),
                    "duration_seconds": duration_seconds,
                    "records_processed": None,
                    "file_size_mb": None,
                    "additional_info": {"month": yyyymm, "url": url, "http_status": 404}
                }

                self._write_log(log_data)
                print(f"Data for {yyyymm} not yet available (404)")
                return False
            else:
                # その他のHTTPエラー
                completed_at = datetime.now()
                duration_seconds = int((completed_at - started_at).total_seconds())

                log_data = {
                    "execution_id": execution_id,
                    "date": target_date,
                    "process_type": "TEPCO_API",
                    "status": "FAILED",
                    "error_message": f"HTTP error downloading {yyyymm}: {e}",
                    "started_at": started_at.isoformat(),
                    "completed_at": completed_at.isoformat(),
                    "duration_seconds": duration_seconds,
                    "records_processed": None,
                    "file_size_mb": None,
                    "additional_info": {"month": yyyymm, "url": url, "http_status": e.response.status_code}
                }

                self._write_log(log_data)
                print(f"HTTP error downloading {yyyymm}: {e}")
                raise
        except Exception as e:
            # その他のエラー
            completed_at = datetime.now()
            duration_seconds = int((completed_at - started_at).total_seconds())

            log_data = {
                "execution_id": execution_id,
                "date": target_date,
                "process_type": "TEPCO_API",
                "status": "FAILED",
                "error_message": f"Error downloading {yyyymm}: {e}",
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
                "duration_seconds": duration_seconds,
                "records_processed": None,
                "file_size_mb": None,
                "additional_info": {"month": yyyymm, "url": url}
            }

            self._write_log(log_data)
            print(f"Error downloading {yyyymm}: {e}")
            raise
    
    def download_for_days(self, days=5):
        """
        指定日数分のデータをダウンロード
        
        Args:
            days (int): 今日から遡る日数
            
        Returns:
            dict: ダウンロード結果 {'success': [...], 'failed': [...]}
        """
        months = self.get_required_months(days)
        results = {'success': [], 'failed': []}
        
        for month in sorted(months):
            try:
                if self.download_month_data(month):
                    results['success'].append(month)
                else:
                    results['failed'].append(month)
            except Exception as e:
                print(f"Failed to download {month}: {e}")
                results['failed'].append(month)
        
        return results
    
    def download_for_month(self, yyyymm):
        """
        指定月のデータをダウンロード
        
        Args:
            yyyymm (str): 年月 (YYYYMM形式)
            
        Returns:
            dict: ダウンロード結果
        """
        # 月フォーマットの事前チェック
        try:
            month_date = datetime.strptime(yyyymm, '%Y%m')
        except ValueError:
            raise ValueError(f"月はYYYYMM形式で入力してください: {yyyymm}")
        
        # 未来月チェック
        current_month = datetime.today().replace(day=1)
        if month_date > current_month:
            current_month_str = current_month.strftime('%Y%m')
            raise ValueError(f"未来の月は指定できません: {yyyymm} (今月: {current_month_str})")

        results = {'success': [], 'failed': []}
        
        try:
            if self.download_month_data(yyyymm):
                results['success'].append(yyyymm)
            else:
                results['failed'].append(yyyymm)
        except Exception as e:
            print(f"Failed to download {yyyymm}: {e}")
            results['failed'].append(yyyymm)
        
        return results
    
    def download_for_date(self, date_str):
        """
        特定日のデータ（その日が含まれる月）をダウンロード
        
        Args:
            date_str (str): 日付文字列 (YYYYMMDD形式)
            
        Returns:
            dict: ダウンロード結果
        """
        months = self.get_months_from_date(date_str)
        results = {'success': [], 'failed': []}
        
        for month in months:
            try:
                if self.download_month_data(month):
                    results['success'].append(month)
                else:
                    results['failed'].append(month)
            except Exception as e:
                print(f"Failed to download {month}: {e}")
                results['failed'].append(month)
        
        return results


def print_results(results):
    """ダウンロード結果を表示"""
    if results['success']:
        print(f"✅ 成功: {', '.join(results['success'])}")
    
    if results['failed']:
        print(f"❌ 失敗: {', '.join(results['failed'])}")
    
    if not results['success'] and not results['failed']:
        print("📝 処理対象がありませんでした")


def main():
    """メイン関数"""
    
    # デフォルトのbase_dirを環境変数から取得
    energy_env_path = os.getenv('ENERGY_ENV_PATH')
    if energy_env_path is None:
        default_base_dir = 'data/raw'  # 環境変数が設定されていない場合のフォールバック
        print("⚠️  警告: ENERGY_ENV_PATH環境変数が設定されていません。相対パスを使用します。")
    else:
        default_base_dir = os.path.join(energy_env_path, 'data', 'raw')
    
    parser = argparse.ArgumentParser(description='東京電力でんき予報データダウンローダー')
    parser.add_argument('--days', type=int, default=5, 
                       help='今日から遡る日数 (デフォルト: 5)')
    parser.add_argument('--month', type=str, 
                       help='指定月をダウンロード (YYYYMM形式)')
    parser.add_argument('--date', type=str, 
                       help='特定日をダウンロード (YYYYMMDD形式)')
    parser.add_argument('--base-dir', type=str, default=default_base_dir,
                       help=f'保存先ディレクトリ (デフォルト: {default_base_dir})')
    
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
    
    # ダウンローダー初期化
    try:
        downloader = PowerDataDownloader(args.base_dir)
    except ValueError as e:
        print(f"❌ エラー: {e}")
        print("   ENERGY_ENV_PATH環境変数を設定してください")
        return
    
    print("🚀 東京電力でんき予報データダウンロード開始")
    print(f"📂 保存先: {downloader.base_dir}")
    
    # 実行モード判定とダウンロード実行
    if args.month:
        print(f"📅 指定月モード: {args.month}")
        results = downloader.download_for_month(args.month)
    elif args.date:
        print(f"📅 特定日モード: {args.date}")
        results = downloader.download_for_date(args.date)
    else:
        print(f"📅 日数指定モード: 過去{args.days}日分")
        results = downloader.download_for_days(args.days)
    
    # 結果表示
    print_results(results)
    print("🏁 ダウンロード完了")


if __name__ == "__main__":
    main()