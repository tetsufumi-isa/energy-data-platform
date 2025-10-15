"""
気象データダウンローダー - Open-Meteo API統合（修正版）

Phase 11: 柔軟な過去データ取得対応
- Historical API: 過去データ取得（2日遅延考慮）
- Forecast API: 14日間の予測データ取得（実行時刻による欠損防止）
- 期間指定・月指定による柔軟な過去データ取得

実行方法:
    # 日次自動実行用（過去10日+予測14日）
    python -m src.data_processing.weather_downloader

    # 過去データ分析用（指定日から30日前まで）
    python -m src.data_processing.weather_downloader --date 2025-08-01

    # 期間指定取得
    python -m src.data_processing.weather_downloader --start-date 2025-07-01 --end-date 2025-07-31

    # 月指定取得（1日～月末）
    python -m src.data_processing.weather_downloader --month 202507

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
        # ローカルファイルに記録（実行日の日付を使用）
        log_date = datetime.now().strftime('%Y-%m-%d')
        log_file = self.log_dir / f"{log_date}_weather_execution.jsonl"

        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_data, ensure_ascii=False) + '\n')
        except Exception as e:
            print(f"ログファイル書き込み失敗: {e}")

        # BigQueryに記録
        try:
            errors = self.bq_client.insert_rows_json(self.bq_table_id, [log_data])
            if errors:
                raise Exception(f"BigQuery insert errors: {errors}")
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
                    raise  # 最後の試行で失敗した場合は元の例外を投げる
                time.sleep(1)

        # forループが正常終了（全試行で429レート制限のみ発生）した場合にここに到達
        raise Exception(f"{max_retries}回の試行後もレート制限が続き、応答取得に失敗しました")
    
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
    
    def get_forecast_data(self, session, forecast_days=14):
        """
        Forecast API で予測データ取得

        Args:
            session (requests.Session): HTTPセッション
            forecast_days (int): 予測日数（最大14日・安定動作保証）

        Returns:
            requests.Response: HTTPレスポンスオブジェクト
        """
        params = {
            'latitude': self.CHIBA_COORDS['latitude'],
            'longitude': self.CHIBA_COORDS['longitude'],
            'hourly': ','.join(self.WEATHER_VARIABLES),
            'forecast_days': min(forecast_days, 14),  # 実行時刻による欠損を防ぐため14日に制限
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
        APIレスポンスの基本検証（JSON形式チェック + データ長一致検証）

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
                validation_result['issues'].append("'hourly'データが見つかりません")
                return validation_result

            hourly_data = data['hourly']

            # 気象変数存在チェック
            missing_vars = []
            for var in self.WEATHER_VARIABLES:
                if var not in hourly_data:
                    missing_vars.append(var)

            if missing_vars:
                validation_result['valid'] = False
                validation_result['issues'].append(f"欠けている変数: {missing_vars}")
                return validation_result

            # データポイント数カウント
            if 'time' not in hourly_data:
                validation_result['valid'] = False
                validation_result['issues'].append("'time'データが見つかりません")
                return validation_result

            expected_length = len(hourly_data['time'])
            validation_result['stats']['total_hours'] = expected_length

            # データ長一致検証（全変数が同じ長さか）
            data_lengths = {
                'time': len(hourly_data['time'])
            }

            for var in self.WEATHER_VARIABLES:
                data_lengths[var] = len(hourly_data[var])

            mismatched = {key: length for key, length in data_lengths.items() if length != expected_length}

            if mismatched:
                validation_result['valid'] = False
                error_msg = f"気象データの長さ不一致を検出:\n"
                error_msg += f"  期待される長さ: {expected_length}時間分\n"
                for key, length in mismatched.items():
                    error_msg += f"  {key}: {length}時間分（差分: {length - expected_length}時間）\n"
                validation_result['issues'].append(error_msg)

        except json.JSONDecodeError as e:
            validation_result['valid'] = False
            validation_result['issues'].append(f"JSONデコードエラー: {e}")
        except Exception as e:
            validation_result['valid'] = False
            validation_result['issues'].append(f"検証エラー: {e}")

        return validation_result
    
    def download_daily_weather_data(self, target_date=None):
        """
        日次気象データダウンロード（修正版）
        
        Args:
            target_date (str): 基準日 (YYYY-MM-DD形式)
                             None: 日次自動実行用（過去10日+予測14日）
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

            print("日次自動実行モード: 過去データ(10日前～3日前) + 予測データ(14日間)")

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
                        raise ValueError(f"過去データ検証失敗: {validation['issues']}")
                
                # ファイル名
                historical_filename = f"chiba_{year}_{date_part}_historical.json"
                historical_path = self.save_json_response(historical_response, historical_filename)
                
                results['historical'].append({
                    'file': historical_path,
                    'period': f"{historical_start} to {historical_end}",
                    'data_points': validation['stats'].get('total_hours', 0) if validation['valid'] else 0,
                    'validation': validation
                })
                
                # 2. 予測データ取得
                forecast_response = self.get_forecast_data(session, forecast_days=14)

                # レスポンス検証
                validation = self.validate_response(forecast_response)
                if not validation['valid']:
                        print(f"予測データ検証問題: {validation['issues']}")
                        raise ValueError(f"予測データ検証失敗: {validation['issues']}")

                # ファイル名
                forecast_filename = f"chiba_{year}_{date_part}_forecast.json"
                forecast_path = self.save_json_response(forecast_response, forecast_filename)

                results['forecast'].append({
                    'file': forecast_path,
                    'forecast_days': 14,
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
                    "additional_info": json.dumps({
                        "mode": "daily_automatic",
                        "historical_period": f"{historical_start} to {historical_end}",
                        "forecast_days": 14,
                        "historical_files": len(results['historical']),
                        "forecast_files": len(results['forecast'])
                    })
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
                    "additional_info": json.dumps({
                        "mode": "daily_automatic",
                        "historical_period": f"{historical_start} to {historical_end}",
                        "forecast_days": 14
                    })
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
                raise ValueError(f"日付形式が不正です。YYYY-MM-DD形式を使用してください。")

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
                    "additional_info": json.dumps({
                        "mode": "historical_analysis",
                        "historical_period": f"{historical_start} to {historical_end}",
                        "historical_files": len(results['historical'])
                    })
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
                    "additional_info": json.dumps({
                        "mode": "historical_analysis",
                        "historical_period": f"{historical_start} to {historical_end}"
                    })
                }

                self._write_log(log_data)
                print(f"過去データ分析用気象データダウンロード失敗: {e}")
                raise
            finally:
                session.close()

    def download_historical_data(self, start_date, end_date):
        """
        期間指定での過去データ取得

        Args:
            start_date (str): 開始日 (YYYY-MM-DD)
            end_date (str): 終了日 (YYYY-MM-DD)

        Returns:
            dict: ダウンロード結果
        """
        # 日付検証
        try:
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        except ValueError:
            raise ValueError(f"日付形式が不正です。YYYY-MM-DD形式を使用してください。")

        if start_dt > end_dt:
            raise ValueError(f"開始日が終了日より後になっています: {start_date} > {end_date}")

        execution_id = str(uuid.uuid4())
        started_at = datetime.now()
        target_date_str = start_date

        print(f"期間指定取得モード: {start_date} ～ {end_date}")

        # ファイル名用（開始日の年月を使用）
        year = start_dt.year
        month = start_dt.strftime('%m')

        # HTTPセッション作成・ヘッダー設定
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'energy-env-weather-downloader/1.0',
            'Accept': 'application/json'
        })
        results = {'historical': [], 'forecast': []}

        try:
            # 過去データ取得
            historical_response = self.get_historical_data(session, start_date, end_date)

            # レスポンス検証
            validation = self.validate_response(historical_response)
            if not validation['valid']:
                print(f"過去データ検証問題: {validation['issues']}")
                raise ValueError(f"過去データ検証失敗: {validation['issues']}")

            # ファイル名: chiba_2025_07_historical_range.json
            historical_filename = f"chiba_{year}_{month}_historical_range.json"
            historical_path = self.save_json_response(historical_response, historical_filename)

            results['historical'].append({
                'file': historical_path,
                'period': f"{start_date} to {end_date}",
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
                "additional_info": json.dumps({
                    "mode": "historical_range",
                    "historical_period": f"{start_date} to {end_date}",
                    "historical_files": len(results['historical'])
                })
            }

            self._write_log(log_data)
            print(f"期間指定取得完了: {start_date} ～ {end_date}")
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
                "additional_info": json.dumps({
                    "mode": "historical_range",
                    "historical_period": f"{start_date} to {end_date}"
                })
            }

            self._write_log(log_data)
            print(f"期間指定取得失敗: {e}")
            raise
        finally:
            session.close()

    def download_for_month(self, yyyymm):
        """
        月指定での過去データ取得（1日～月末）

        Args:
            yyyymm (str): 対象月 (YYYYMM形式、例: 202507)

        Returns:
            dict: ダウンロード結果
        """
        # 月形式検証
        try:
            year = int(yyyymm[:4])
            month = int(yyyymm[4:6])
            if len(yyyymm) != 6 or month < 1 or month > 12:
                raise ValueError()
        except (ValueError, IndexError):
            raise ValueError(f"月形式が不正です。YYYYMM形式を使用してください（例: 202507）")

        # 月初と月末を計算
        from calendar import monthrange
        start_date = f"{year:04d}-{month:02d}-01"
        last_day = monthrange(year, month)[1]
        end_date = f"{year:04d}-{month:02d}-{last_day:02d}"

        execution_id = str(uuid.uuid4())
        started_at = datetime.now()
        target_date_str = start_date

        print(f"月指定取得モード: {yyyymm} ({start_date} ～ {end_date})")

        # HTTPセッション作成・ヘッダー設定
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'energy-env-weather-downloader/1.0',
            'Accept': 'application/json'
        })
        results = {'historical': [], 'forecast': []}

        try:
            # 過去データ取得
            historical_response = self.get_historical_data(session, start_date, end_date)

            # レスポンス検証
            validation = self.validate_response(historical_response)
            if not validation['valid']:
                print(f"過去データ検証問題: {validation['issues']}")
                raise ValueError(f"過去データ検証失敗: {validation['issues']}")

            # ファイル名: chiba_2025_07_historical_month.json
            historical_filename = f"chiba_{year}_{month:02d}_historical_month.json"
            historical_path = self.save_json_response(historical_response, historical_filename)

            results['historical'].append({
                'file': historical_path,
                'period': f"{start_date} to {end_date}",
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
                "additional_info": json.dumps({
                    "mode": "historical_month",
                    "target_month": yyyymm,
                    "historical_period": f"{start_date} to {end_date}",
                    "historical_files": len(results['historical'])
                })
            }

            self._write_log(log_data)
            print(f"月指定取得完了: {yyyymm}")
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
                "additional_info": json.dumps({
                    "mode": "historical_month",
                    "target_month": yyyymm,
                    "historical_period": f"{start_date} to {end_date}"
                })
            }

            self._write_log(log_data)
            print(f"月指定取得失敗: {e}")
            raise
        finally:
            session.close()


def print_results(results):
    """処理結果を表示"""
    print(f"\n{'='*60}")
    print("気象データダウンロード結果")
    print('='*60)

    # Historical データ結果
    if results['historical']:
        print(f"\n過去データ: {len(results['historical'])}件")
        for item in results['historical']:
            print(f"  {Path(item['file']).name}")
            print(f"     期間: {item['period']}")
            print(f"     データポイント: {item['data_points']}時間")
            if not item['validation']['valid']:
                print(f"     検証問題: {item['validation']['issues']}")

    # Forecast データ結果
    if results['forecast']:
        print(f"\n予測データ: {len(results['forecast'])}件")
        for item in results['forecast']:
            print(f"  {Path(item['file']).name}")
            print(f"     予測期間: {item['forecast_days']}日間")
            print(f"     データポイント: {item['data_points']}時間")
            if not item['validation']['valid']:
                print(f"     検証問題: {item['validation']['issues']}")

    print(f"\n総合結果: 過去{len(results['historical'])}件 / 予測{len(results['forecast'])}件")
    print('='*60)


def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(description='Open-Meteo気象データダウンローダー（Phase 11対応版）')
    parser.add_argument('--date', type=str,
                       help='基準日 (YYYY-MM-DD形式) 指定なし:日次自動実行用、指定あり:過去データ分析用')
    parser.add_argument('--start-date', type=str,
                       help='期間指定の開始日 (YYYY-MM-DD形式、--end-dateと併用)')
    parser.add_argument('--end-date', type=str,
                       help='期間指定の終了日 (YYYY-MM-DD形式、--start-dateと併用)')
    parser.add_argument('--month', type=str,
                       help='月指定 (YYYYMM形式、例: 202507)')
    parser.add_argument('--download-dir', type=str,
                       help='ダウンロードディレクトリパス')

    args = parser.parse_args()

    # 引数の排他チェック
    modes = sum([
        args.date is not None,
        (args.start_date is not None or args.end_date is not None),
        args.month is not None
    ])

    if modes > 1:
        print("エラー: --date, --start-date/--end-date, --month は同時に指定できません")
        return

    if (args.start_date is None) != (args.end_date is None):
        print("エラー: --start-date と --end-date は両方指定する必要があります")
        return

    print("Open-Meteo気象データダウンロード開始")
    print(f"対象地点: 千葉県 (lat: {WeatherDownloader.CHIBA_COORDS['latitude']}, "
          f"lon: {WeatherDownloader.CHIBA_COORDS['longitude']})")

    try:
        # WeatherDownloader初期化
        downloader = WeatherDownloader(args.download_dir)

        # モードに応じた実行
        if args.month:
            # 月指定モード
            print(f"月指定モード: {args.month}")
            results = downloader.download_for_month(args.month)

        elif args.start_date and args.end_date:
            # 期間指定モード
            print(f"期間指定モード: {args.start_date} ～ {args.end_date}")
            results = downloader.download_historical_data(args.start_date, args.end_date)

        elif args.date:
            # 過去データ分析モード（指定日から30日前まで）
            print(f"基準日指定: {args.date} (過去データ分析用)")
            print(f"取得範囲: {args.date}から30日前までの過去データ")
            results = downloader.download_daily_weather_data(args.date)

        else:
            # 日次自動実行モード
            today = datetime.now()
            historical_start = (today - timedelta(days=10)).strftime('%Y-%m-%d')
            historical_end = (today - timedelta(days=3)).strftime('%Y-%m-%d')
            print(f"日次自動実行モード")
            print(f"取得範囲: 過去データ({historical_start}〜{historical_end}) + 予測データ(14日間)")
            results = downloader.download_daily_weather_data()

        # 結果表示
        print_results(results)

    except Exception as e:
        print(f"ダウンロードエラー: {e}")
        import sys
        sys.exit(1)

    print("気象データダウンロード完了")


if __name__ == "__main__":
    main()