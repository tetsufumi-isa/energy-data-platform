"""
気象データダウンローダー - Open-Meteo API統合（修正版）

Phase 10: 日次自動予測システム用
- Historical API: 過去データ取得（2日遅延考慮）
- Forecast API: 16日間の予測データ取得
- 基準日による取得ロジック分離

実行方法:
    # 日次自動実行用（過去10日+予測16日）
    python -m src.data_processing.weather_downloader

    # 過去データ分析用（指定日から30日前まで）
    python -m src.data_processing.weather_downloader --date 2025-08-01

    # ダウンロードディレクトリ指定
    python -m src.data_processing.weather_downloader --download-dir data/weather/raw/daily
"""

import os
import json
import requests
import argparse
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from google.cloud import bigquery

class WeatherDownloader:
    """Open-Meteo API気象データダウンローダー"""
    
    # API エンドポイント
    HISTORICAL_URL = "https://archive-api.open-meteo.com/v1/archive"
    FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
    
    # 千葉県座標（Phase 9で最重要地点として確定）
    CHIBA_COORDS = {
        'latitude': 35.6047,
        'longitude': 140.1233
    }
    
    # 取得する気象変数（WeatherProcessor互換）
    WEATHER_VARIABLES = [
        'temperature_2m',
        'relative_humidity_2m', 
        'precipitation',
        'weather_code'
    ]
    
    def __init__(self, download_dir=None):
        """
        初期化

        Args:
            download_dir (str): JSONダウンロード先ディレクトリ
        """
        # 環境変数から取得
        energy_env_path = os.getenv('ENERGY_ENV_PATH')
        if energy_env_path is None:
            raise ValueError("ENERGY_ENV_PATH環境変数が設定されていません")

        if download_dir is None:
            download_dir = os.path.join(energy_env_path, 'data', 'weather', 'raw', 'daily')
            self.log_dir = Path(energy_env_path) / 'logs' / 'weather_api'
        else:
            self.log_dir = Path(download_dir).parent.parent.parent / 'logs' / 'weather_api'

        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # BigQuery設定
        self.bq_client = bigquery.Client()
        self.bq_table_id = "energy-env.prod_energy_data.process_execution_log"

        print(f"WeatherDownloader初期化完了 ダウンロード先: {self.download_dir}")

    def _write_log(self, log_data):
        """
        ログをローカルファイルとBigQueryに記録

        Args:
            log_data (dict): ログデータ
        """
        # ローカルファイルに記録
        log_date = log_data.get('date', datetime.now().strftime('%Y-%m-%d'))
        log_file = self.log_dir / f"{log_date}_weather_execution.jsonl"

        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_data, ensure_ascii=False) + '\n')
        except Exception as e:
            print(f"ログファイル書き込み失敗: {e}")

        # BigQueryに記録
        try:
            self.bq_client.insert_rows_json(self.bq_table_id, [log_data])
        except Exception as e:
            # BQエラーをローカルログにも記録
            error_log = {
                'timestamp': datetime.now().isoformat(),
                'error_type': 'BQ_INSERT_FAILED',
                'error_message': str(e),
                'original_log_data': log_data
            }
            error_log_file = self.log_dir / f"{log_date}_bq_errors.jsonl"
            try:
                with open(error_log_file, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(error_log, ensure_ascii=False) + '\n')
            except Exception as file_error:
                print(f"エラーログファイル書き込み失敗: {file_error}")

            print(f"BigQuery書き込み失敗（ファイルには保存済み・エラーログ記録済み）: {e}")

    def download_with_retry(self, session, url, params, max_retries=3):
        """
        リトライ機能付きAPIリクエスト
        
        Args:
            session (requests.Session): HTTPセッション
            url (str): APIエンドポイントURL
            params (dict): リクエストパラメータ
            max_retries (int): 最大リトライ回数
            
        Returns:
            requests.Response: HTTPレスポンスオブジェクト
            
        Raises:
            Exception: リトライ回数超過時
        """
        for attempt in range(max_retries):
            try:
                response = session.get(url, params=params, timeout=30)
                
                if response.status_code == 200:
                    return response
                elif response.status_code == 429:  # Too Many Requests
                    wait_time = 2 ** attempt  # 指数バックオフ
                    print(f"レート制限検知、{wait_time}秒待機中... (試行 {attempt + 1}回目)")
                    time.sleep(wait_time)
                    continue
                else:
                    response.raise_for_status()

            except requests.exceptions.RequestException as e:
                print(f"リクエスト失敗 (試行 {attempt + 1}回目): {e}")
                if attempt == max_retries - 1:
                    raise
                time.sleep(1)
        
        raise Exception(f"Failed to get response after {max_retries} attempts")
    
    def get_historical_data(self, session, start_date, end_date):
        """
        Historical API で過去データ取得
        
        Args:
            session (requests.Session): HTTPセッション
            start_date (str): 開始日 (YYYY-MM-DD)
            end_date (str): 終了日 (YYYY-MM-DD)
            
        Returns:
            requests.Response: HTTPレスポンスオブジェクト
        """
        params = {
            'latitude': self.CHIBA_COORDS['latitude'],
            'longitude': self.CHIBA_COORDS['longitude'],
            'start_date': start_date,
            'end_date': end_date,
            'hourly': ','.join(self.WEATHER_VARIABLES),
            'timezone': 'Asia/Tokyo'
        }
        
        print(f"過去データダウンロード中: {start_date} ～ {end_date}")
        return self.download_with_retry(session, self.HISTORICAL_URL, params)
    
    def get_forecast_data(self, session, forecast_days=16):
        """
        Forecast API で予測データ取得
        
        Args:
            session (requests.Session): HTTPセッション
            forecast_days (int): 予測日数（最大16日）
            
        Returns:
            requests.Response: HTTPレスポンスオブジェクト
        """
        params = {
            'latitude': self.CHIBA_COORDS['latitude'],
            'longitude': self.CHIBA_COORDS['longitude'],
            'hourly': ','.join(self.WEATHER_VARIABLES),
            'forecast_days': min(forecast_days, 16),  # 制限対応
            'timezone': 'Asia/Tokyo'
        }
        
        print(f"予測データダウンロード中: {forecast_days}日分")
        return self.download_with_retry(session, self.FORECAST_URL, params)
    
    def save_json_response(self, response, filename):
        """
        APIレスポンスを直接JSONファイルとして保存（無駄な変換なし）

        Args:
            response (requests.Response): APIレスポンス
            filename (str): 出力ファイル名

        Returns:
            str: 保存されたファイルパス
        """
        output_path = self.download_dir / filename
        
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(response.text)  # APIレスポンスを直接保存

            print(f"気象データ保存完了: {output_path}")
            return str(output_path)

        except Exception as e:
            print(f"JSONファイル保存失敗 {output_path}: {e}")
            raise
    
    def validate_response(self, response):
        """
        APIレスポンスの基本検証（JSON形式チェック）
        
        Args:
            response (requests.Response): APIレスポンス
            
        Returns:
            dict: 検証結果
        """
        validation_result = {
            'valid': True,
            'issues': [],
            'stats': {}
        }
        
        try:
            # JSON形式チェック（必要時のみ変換）
            data = response.json()
            
            # 基本構造チェック
            if 'hourly' not in data:
                validation_result['valid'] = False
                validation_result['issues'].append("Missing 'hourly' data")
                return validation_result
            
            hourly_data = data['hourly']
            
            # 気象変数存在チェック
            missing_vars = []
            for var in self.WEATHER_VARIABLES:
                if var not in hourly_data:
                    missing_vars.append(var)
            
            if missing_vars:
                validation_result['valid'] = False
                validation_result['issues'].append(f"Missing variables: {missing_vars}")
            
            # データポイント数カウント
            if 'time' in hourly_data:
                validation_result['stats']['total_hours'] = len(hourly_data['time'])
            
        except json.JSONDecodeError as e:
            validation_result['valid'] = False
            validation_result['issues'].append(f"JSON decode error: {e}")
        except Exception as e:
            validation_result['valid'] = False
            validation_result['issues'].append(f"Validation error: {e}")
        
        return validation_result
    
    def download_daily_weather_data(self, target_date=None):
        """
        日次気象データダウンロード（修正版）
        
        Args:
            target_date (str): 基準日 (YYYY-MM-DD形式)
                             None: 日次自動実行用（過去10日+予測16日）
                             指定: 過去データ分析用（指定日から30日前まで）
        
        Returns:
            dict: ダウンロード結果
        """
        today = datetime.now()
        
        if target_date is None:
            # ケース1: 基準日無し（日次自動実行用）
            execution_id = str(uuid.uuid4())
            started_at = datetime.now()
            target_date_str = started_at.strftime('%Y-%m-%d')

            print("日次自動実行モード: 過去データ(10日前～3日前) + 予測データ(16日間)")

            # 過去データ: 10日前から3日前まで（API遅延考慮）
            historical_start = (today - timedelta(days=10)).strftime('%Y-%m-%d')
            historical_end = (today - timedelta(days=3)).strftime('%Y-%m-%d')

            # ファイル名用の日付（今日）
            date_part = today.strftime('%m%d')
            year = today.year

            # HTTPセッション作成・ヘッダー設定
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'energy-env-weather-downloader/1.0',
                'Accept': 'application/json'
            })
            results = {'historical': [], 'forecast': []}

            try:
                # 1. 過去データ取得
                historical_response = self.get_historical_data(session, historical_start, historical_end)
                
                # レスポンス検証
                validation = self.validate_response(historical_response)
                if not validation['valid']:
                        print(f"過去データ検証問題: {validation['issues']}")
                
                # ファイル名: chiba_2025_0818_historical.json
                historical_filename = f"chiba_{year}_{date_part}_historical.json"
                historical_path = self.save_json_response(historical_response, historical_filename)
                
                results['historical'].append({
                    'file': historical_path,
                    'period': f"{historical_start} to {historical_end}",
                    'data_points': validation['stats'].get('total_hours', 0) if validation['valid'] else 0,
                    'validation': validation
                })
                
                # 2. 予測データ取得
                forecast_response = self.get_forecast_data(session, forecast_days=16)
                
                # レスポンス検証
                validation = self.validate_response(forecast_response)
                if not validation['valid']:
                        print(f"予測データ検証問題: {validation['issues']}")
                
                # ファイル名: chiba_2025_0818_forecast.json
                forecast_filename = f"chiba_{year}_{date_part}_forecast.json"
                forecast_path = self.save_json_response(forecast_response, forecast_filename)
                
                results['forecast'].append({
                    'file': forecast_path,
                    'forecast_days': 16,
                    'data_points': validation['stats'].get('total_hours', 0) if validation['valid'] else 0,
                    'validation': validation
                })
                
                # 成功ログ記録
                completed_at = datetime.now()
                duration_seconds = int((completed_at - started_at).total_seconds())
                total_data_points = sum([item['data_points'] for item in results['historical']]) + \
                                   sum([item['data_points'] for item in results['forecast']])

                log_data = {
                    "execution_id": execution_id,
                    "date": target_date_str,
                    "process_type": "WEATHER_API",
                    "status": "SUCCESS",
                    "error_message": None,
                    "started_at": started_at.isoformat(),
                    "completed_at": completed_at.isoformat(),
                    "duration_seconds": duration_seconds,
                    "records_processed": total_data_points,
                    "file_size_mb": None,
                    "additional_info": {
                        "mode": "daily_automatic",
                        "historical_period": f"{historical_start} to {historical_end}",
                        "forecast_days": 16,
                        "historical_files": len(results['historical']),
                        "forecast_files": len(results['forecast'])
                    }
                }

                self._write_log(log_data)
                print("日次自動気象データダウンロード完了")
                return results

            except Exception as e:
                # エラーログ記録
                completed_at = datetime.now()
                duration_seconds = int((completed_at - started_at).total_seconds())

                log_data = {
                    "execution_id": execution_id,
                    "date": target_date_str,
                    "process_type": "WEATHER_API",
                    "status": "FAILED",
                    "error_message": str(e),
                    "started_at": started_at.isoformat(),
                    "completed_at": completed_at.isoformat(),
                    "duration_seconds": duration_seconds,
                    "records_processed": None,
                    "file_size_mb": None,
                    "additional_info": {
                        "mode": "daily_automatic",
                        "historical_period": f"{historical_start} to {historical_end}",
                        "forecast_days": 16
                    }
                }

                self._write_log(log_data)
                print(f"日次自動気象データダウンロード失敗: {e}")
                raise
            finally:
                session.close()
        
        else:
            # ケース2: 基準日指定（過去データ分析用）
            try:
                target_dt = datetime.strptime(target_date, '%Y-%m-%d')
            except ValueError:
                raise ValueError(f"Invalid date format. Use YYYY-MM-DD format.")

            execution_id = str(uuid.uuid4())
            started_at = datetime.now()
            target_date_str = target_date

            print(f"過去データ分析モード: {target_date} から30日前まで")
            
            # 過去データ: 指定日から30日前まで
            historical_start = (target_dt - timedelta(days=30)).strftime('%Y-%m-%d')
            historical_end = target_date
            
            # ファイル名用の日付（指定日）
            date_part = target_dt.strftime('%m%d')
            year = target_dt.year

            # HTTPセッション作成・ヘッダー設定
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'energy-env-weather-downloader/1.0',
                'Accept': 'application/json'
            })
            results = {'historical': [], 'forecast': []}
            
            try:
                # 過去データのみ取得
                historical_response = self.get_historical_data(session, historical_start, historical_end)
                
                # レスポンス検証
                validation = self.validate_response(historical_response)
                if not validation['valid']:
                        print(f"過去データ検証問題: {validation['issues']}")
                
                # ファイル名: chiba_2025_0801_historical_30days.json
                historical_filename = f"chiba_{year}_{date_part}_historical_30days.json"
                historical_path = self.save_json_response(historical_response, historical_filename)
                
                results['historical'].append({
                    'file': historical_path,
                    'period': f"{historical_start} to {historical_end}",
                    'data_points': validation['stats'].get('total_hours', 0) if validation['valid'] else 0,
                    'validation': validation
                })
                
                # 成功ログ記録
                completed_at = datetime.now()
                duration_seconds = int((completed_at - started_at).total_seconds())
                total_data_points = sum([item['data_points'] for item in results['historical']])

                log_data = {
                    "execution_id": execution_id,
                    "date": target_date_str,
                    "process_type": "WEATHER_API",
                    "status": "SUCCESS",
                    "error_message": None,
                    "started_at": started_at.isoformat(),
                    "completed_at": completed_at.isoformat(),
                    "duration_seconds": duration_seconds,
                    "records_processed": total_data_points,
                    "file_size_mb": None,
                    "additional_info": {
                        "mode": "historical_analysis",
                        "historical_period": f"{historical_start} to {historical_end}",
                        "historical_files": len(results['historical'])
                    }
                }

                self._write_log(log_data)
                print(f"過去データ分析用気象データダウンロード完了: {target_date}")
                return results

            except Exception as e:
                # エラーログ記録
                completed_at = datetime.now()
                duration_seconds = int((completed_at - started_at).total_seconds())

                log_data = {
                    "execution_id": execution_id,
                    "date": target_date_str,
                    "process_type": "WEATHER_API",
                    "status": "FAILED",
                    "error_message": str(e),
                    "started_at": started_at.isoformat(),
                    "completed_at": completed_at.isoformat(),
                    "duration_seconds": duration_seconds,
                    "records_processed": None,
                    "file_size_mb": None,
                    "additional_info": {
                        "mode": "historical_analysis",
                        "historical_period": f"{historical_start} to {historical_end}"
                    }
                }

                self._write_log(log_data)
                print(f"過去データ分析用気象データダウンロード失敗: {e}")
                raise
            finally:
                session.close()


def print_results(results):
    """処理結果を表示"""
    print(f"\n{'='*60}")
    print("🌤️ 気象データダウンロード結果")
    print('='*60)
    
    # Historical データ結果
    if results['historical']:
        print(f"\n✅ 過去データ: {len(results['historical'])}件")
        for item in results['historical']:
            print(f"  📁 {Path(item['file']).name}")
            print(f"     期間: {item['period']}")
            print(f"     データポイント: {item['data_points']}時間")
            if not item['validation']['valid']:
                print(f"     ⚠️ 検証問題: {item['validation']['issues']}")
    
    # Forecast データ結果
    if results['forecast']:
        print(f"\n✅ 予測データ: {len(results['forecast'])}件")
        for item in results['forecast']:
            print(f"  📁 {Path(item['file']).name}")
            print(f"     予測期間: {item['forecast_days']}日間")
            print(f"     データポイント: {item['data_points']}時間")
            if not item['validation']['valid']:
                print(f"     ⚠️ 検証問題: {item['validation']['issues']}")
    
    print(f"\n📈 総合結果: 過去{len(results['historical'])}件 / 予測{len(results['forecast'])}件")
    print('='*60)


def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(description='Open-Meteo気象データダウンローダー（修正版）')
    parser.add_argument('--date', type=str,
                       help='基準日 (YYYY-MM-DD形式) 指定なし:日次自動実行用、指定あり:過去データ分析用')
    parser.add_argument('--download-dir', type=str,
                       help='ダウンロードディレクトリパス')
    
    args = parser.parse_args()
    
    print("🚀 Open-Meteo気象データダウンロード開始")
    print(f"📍 対象地点: 千葉県 (lat: {WeatherDownloader.CHIBA_COORDS['latitude']}, "
          f"lon: {WeatherDownloader.CHIBA_COORDS['longitude']})")
    
    if args.date:
        print(f"📅 基準日指定: {args.date} (過去データ分析用)")
        print(f"📊 取得範囲: {args.date}から30日前までの過去データ")
    else:
        today = datetime.now()
        historical_start = (today - timedelta(days=10)).strftime('%Y-%m-%d')
        historical_end = (today - timedelta(days=3)).strftime('%Y-%m-%d')
        print(f"📅 日次自動実行モード")
        print(f"📊 取得範囲: 過去データ({historical_start}〜{historical_end}) + 予測データ(16日間)")
    
    try:
        # WeatherDownloader初期化
        downloader = WeatherDownloader(args.download_dir)
        
        # 気象データダウンロード実行
        results = downloader.download_daily_weather_data(args.date)
        
        # 結果表示
        print_results(results)
        
    except Exception as e:
        print(f"💥 ダウンロードエラー: {e}")
        return
    
    print("🏁 気象データダウンロード完了")


if __name__ == "__main__":
    main()