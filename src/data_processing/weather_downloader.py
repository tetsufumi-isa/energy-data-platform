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
    
    # 出力ディレクトリ指定
    python -m src.data_processing.weather_downloader --output-dir data/weather/raw/daily
"""

import os
import json
import requests
import argparse
import time
from datetime import datetime, timedelta
from pathlib import Path
from logging import getLogger

from src.utils.logging_config import setup_logging

# モジュール専用のロガーを取得
logger = getLogger('energy_env.data_processing.weather_downloader')

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
    
    def __init__(self, output_dir=None):
        """
        初期化
        
        Args:
            output_dir (str): JSON出力先ディレクトリ
        """
        if output_dir is None:
            # 環境変数から取得
            energy_env_path = os.getenv('ENERGY_ENV_PATH')
            if energy_env_path:
                output_dir = os.path.join(energy_env_path, 'data', 'weather', 'raw', 'daily')
            else:
                output_dir = 'data/weather/raw/daily'
        
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"WeatherDownloader initialized with output_dir: {self.output_dir}")
    
    def create_robust_session(self):
        """
        レート制限・エラー対応のセッション作成
        
        Returns:
            requests.Session: リトライ設定済みセッション
        """
        session = requests.Session()
        
        # ヘッダー設定
        session.headers.update({
            'User-Agent': 'energy-env-weather-downloader/1.0',
            'Accept': 'application/json'
        })
        
        return session
    
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
                    logger.warning(f"Rate limited, waiting {wait_time}s... (attempt {attempt + 1})")
                    time.sleep(wait_time)
                    continue
                else:
                    response.raise_for_status()
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed (attempt {attempt + 1}): {e}")
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
        
        logger.info(f"Downloading historical data: {start_date} to {end_date}")
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
        
        logger.info(f"Downloading forecast data: {forecast_days} days")
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
        output_path = self.output_dir / filename
        
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(response.text)  # APIレスポンスを直接保存
            
            logger.info(f"Saved weather data: {output_path}")
            return str(output_path)
            
        except Exception as e:
            logger.error(f"Failed to save JSON file {output_path}: {e}")
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
            logger.info("Daily automatic execution mode: historical (10 days ago to 3 days ago) + forecast (16 days)")
            
            # 過去データ: 10日前から3日前まで（API遅延考慮）
            historical_start = (today - timedelta(days=10)).strftime('%Y-%m-%d')
            historical_end = (today - timedelta(days=3)).strftime('%Y-%m-%d')
            
            # ファイル名用の日付（今日）
            date_part = today.strftime('%m%d')
            year = today.year
            
            session = self.create_robust_session()
            results = {'historical': [], 'forecast': []}
            
            try:
                # 1. 過去データ取得
                historical_response = self.get_historical_data(session, historical_start, historical_end)
                
                # レスポンス検証
                validation = self.validate_response(historical_response)
                if not validation['valid']:
                    logger.warning(f"Historical data validation issues: {validation['issues']}")
                
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
                    logger.warning(f"Forecast data validation issues: {validation['issues']}")
                
                # ファイル名: chiba_2025_0818_forecast.json
                forecast_filename = f"chiba_{year}_{date_part}_forecast.json"
                forecast_path = self.save_json_response(forecast_response, forecast_filename)
                
                results['forecast'].append({
                    'file': forecast_path,
                    'forecast_days': 16,
                    'data_points': validation['stats'].get('total_hours', 0) if validation['valid'] else 0,
                    'validation': validation
                })
                
                logger.info("Daily automatic weather data download completed successfully")
                return results
                
            except Exception as e:
                logger.error(f"Daily automatic weather data download failed: {e}")
                raise
            finally:
                session.close()
        
        else:
            # ケース2: 基準日指定（過去データ分析用）
            try:
                target_dt = datetime.strptime(target_date, '%Y-%m-%d')
            except ValueError:
                raise ValueError(f"Invalid date format. Use YYYY-MM-DD format.")
            
            logger.info(f"Historical analysis mode: {target_date} and 30 days before")
            
            # 過去データ: 指定日から30日前まで
            historical_start = (target_dt - timedelta(days=30)).strftime('%Y-%m-%d')
            historical_end = target_date
            
            # ファイル名用の日付（指定日）
            date_part = target_dt.strftime('%m%d')
            year = target_dt.year
            
            session = self.create_robust_session()
            results = {'historical': [], 'forecast': []}
            
            try:
                # 過去データのみ取得
                historical_response = self.get_historical_data(session, historical_start, historical_end)
                
                # レスポンス検証
                validation = self.validate_response(historical_response)
                if not validation['valid']:
                    logger.warning(f"Historical data validation issues: {validation['issues']}")
                
                # ファイル名: chiba_2025_0801_historical_30days.json
                historical_filename = f"chiba_{year}_{date_part}_historical_30days.json"
                historical_path = self.save_json_response(historical_response, historical_filename)
                
                results['historical'].append({
                    'file': historical_path,
                    'period': f"{historical_start} to {historical_end}",
                    'data_points': validation['stats'].get('total_hours', 0) if validation['valid'] else 0,
                    'validation': validation
                })
                
                logger.info(f"Historical analysis weather data download completed for {target_date}")
                return results
                
            except Exception as e:
                logger.error(f"Historical analysis weather data download failed: {e}")
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
    # ログ設定を初期化
    setup_logging()
    
    parser = argparse.ArgumentParser(description='Open-Meteo気象データダウンローダー（修正版）')
    parser.add_argument('--date', type=str,
                       help='基準日 (YYYY-MM-DD形式) 指定なし:日次自動実行用、指定あり:過去データ分析用')
    parser.add_argument('--output-dir', type=str,
                       help='出力ディレクトリパス')
    
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
        downloader = WeatherDownloader(args.output_dir)
        
        # 気象データダウンロード実行
        results = downloader.download_daily_weather_data(args.date)
        
        # 結果表示
        print_results(results)
        
    except Exception as e:
        logger.error(f"Weather download failed: {e}")
        print(f"💥 ダウンロードエラー: {e}")
        return
    
    print("🏁 気象データダウンロード完了")


if __name__ == "__main__":
    main()