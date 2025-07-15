"""
気象データ変換プロセッサー - JSON→CSV変換・BigQuery投入準備

実行方法:
    python -m src.data_processing.weather_processor --input-dir data/weather/raw/historical
    python -m src.data_processing.weather_processor --input-dir data/weather/raw/historical --date 2025-07-13
"""

import os
import json
import csv
import argparse
from datetime import datetime
from pathlib import Path
from logging import getLogger

from src.utils.logging_config import setup_logging

# モジュール専用のロガーを取得
logger = getLogger('energy_env.data_processing.weather_processor')

class WeatherProcessor:
    """気象データ変換プロセッサー"""
    
    # 有効な都県リスト
    VALID_PREFECTURES = [
        'tokyo', 'kanagawa', 'saitama', 'chiba', 'ibaraki', 
        'tochigi', 'gunma', 'yamanashi', 'shizuoka'
    ]
    
    def __init__(self, output_dir="data/weather/processed/forecast"):
        """
        初期化
        
        Args:
            output_dir (str): CSV出力先ディレクトリ
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"WeatherProcessor initialized with output_dir: {self.output_dir}")
    
    def convert_json_to_csv(self, json_file_path, date_filter=None):
        """
        JSONファイルをCSVに変換
        
        Args:
            json_file_path (str): 入力JSONファイルパス
            date_filter (str, optional): 日付フィルタ (YYYY-MM-DD形式)
            
        Returns:
            str: 出力CSVファイルパス（データがない場合はNone）
        """
        json_path = Path(json_file_path)
        
        # ファイル名から都県名と年を抽出・検証
        file_stem = json_path.stem  # tokyo_2023 or tokyo_2025_0715
        parts = file_stem.split('_')
        
        # 基本チェック: 最低2要素必要
        if len(parts) < 2:
            raise ValueError(f"Invalid filename format (need prefecture_year): {json_path.name}")
        
        # 都県名チェック
        prefecture = parts[0]
        if prefecture not in self.VALID_PREFECTURES:
            raise ValueError(f"Invalid prefecture '{prefecture}'. Valid: {self.VALID_PREFECTURES}")
        
        # 年チェック
        year_str = parts[1]
        try:
            year = int(year_str)
            if not (2010 <= year <= 2100):
                raise ValueError(f"Year must be between 2010-2100: {year}")
        except ValueError:
            raise ValueError(f"Invalid year format '{year_str}': {json_path.name}")
        
        # 日付チェック（オプション）
        date_part = None
        if len(parts) == 3:
            date_part = parts[2]
            # MMDD形式チェック
            if len(date_part) != 4 or not date_part.isdigit():
                raise ValueError(f"Date must be MMDD format: {date_part}")
            
            # 実在日付チェック
            try:
                month = int(date_part[:2])
                day = int(date_part[2:])
                datetime(year, month, day)  # 実在日付かチェック
            except ValueError:
                raise ValueError(f"Invalid date {year}-{date_part}: not a real date")
        elif len(parts) > 3:
            raise ValueError(f"Too many parts in filename: {json_path.name}")
        
        # 出力ファイル名生成
        if date_part:
            output_filename = f"{prefecture}_{year}_{date_part}.csv"
        else:
            output_filename = f"{prefecture}_{year}.csv"
        output_path = self.output_dir / output_filename
        
        logger.info(f"Converting {json_path.name} to {output_filename}")
        
        # JSONデータ読み込み
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        hourly_data = data['hourly']
        times = hourly_data['time']
        temperatures = hourly_data['temperature_2m']
        humidity = hourly_data['relative_humidity_2m']
        precipitation = hourly_data['precipitation']
        weather_codes = hourly_data['weather_code']
        
        # 事前にデータ存在チェック
        has_matching_data = False
        for i in range(len(times)):
            time_str = times[i]
            dt = datetime.fromisoformat(time_str)
            date_str = dt.strftime('%Y-%m-%d')
            if not date_filter or date_str == date_filter:
                has_matching_data = True
                break
        
        # データがない場合は処理終了
        if not has_matching_data:
            logger.info(f"No matching data found for date filter {date_filter} in {json_path.name}")
            return None
        
        # CSV出力
        converted_count = 0
        with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            
            # ヘッダー行
            writer.writerow([
                'prefecture', 'date', 'hour', 'temperature_2m', 
                'relative_humidity_2m', 'precipitation', 'weather_code'
            ])
            
            # データ行
            for i in range(len(times)):
                # 時刻解析 (例: 2023-01-01T00:00 -> 2023-01-01, 00)
                time_str = times[i]
                dt = datetime.fromisoformat(time_str)
                date_str = dt.strftime('%Y-%m-%d')
                hour_str = dt.strftime('%H')
                
                # 日付フィルタ適用（事前チェック済みなので必要な行のみ処理）
                if date_filter and date_str != date_filter:
                    continue
                
                # CSV行出力
                writer.writerow([
                    prefecture,
                    date_str,
                    hour_str,
                    temperatures[i],
                    humidity[i],
                    precipitation[i],
                    weather_codes[i]
                ])
                converted_count += 1
        
        logger.info(f"Converted {converted_count} records to {output_path}")
        return str(output_path)
    
    def process_directory(self, input_dir, date_filter=None):
        """
        ディレクトリ内のJSONファイルを一括変換
        
        Args:
            input_dir (str): 入力ディレクトリパス
            date_filter (str, optional): 日付フィルタ (YYYY-MM-DD形式)
            
        Returns:
            dict: 処理結果 {'success': [...], 'failed': [...]}
        """
        input_path = Path(input_dir)
        if not input_path.exists():
            raise FileNotFoundError(f"Input directory not found: {input_dir}")
        
        # JSONファイル検索
        json_files = list(input_path.glob("*.json"))
        if not json_files:
            logger.warning(f"No JSON files found in {input_dir}")
            return {'success': [], 'failed': []}
        
        logger.info(f"Found {len(json_files)} JSON files in {input_dir}")
        
        results = {'success': [], 'failed': []}
        
        for json_file in sorted(json_files):
            try:
                output_path = self.convert_json_to_csv(str(json_file), date_filter)
                if output_path:  # Noneでない場合のみ成功として記録
                    results['success'].append({
                        'input': str(json_file),
                        'output': output_path
                    })
                # output_pathがNoneの場合は何も記録しない（空ファイル作成されない）
            except Exception as e:
                logger.error(f"Failed to convert {json_file}: {e}")
                results['failed'].append({
                    'input': str(json_file),
                    'error': str(e)
                })
        
        return results


def print_results(results):
    """処理結果を表示"""
    success_count = len(results['success'])
    failed_count = len(results['failed'])
    
    print(f"\n{'='*60}")
    print("📊 気象データ変換結果")
    print('='*60)
    
    if results['success']:
        print(f"\n✅ 成功: {success_count}ファイル")
        for item in results['success']:
            input_name = Path(item['input']).name
            output_name = Path(item['output']).name
            print(f"  {input_name} → {output_name}")
    
    if results['failed']:
        print(f"\n❌ 失敗: {failed_count}ファイル")
        for item in results['failed']:
            input_name = Path(item['input']).name
            print(f"  {input_name}: {item['error']}")
    
    if success_count == 0 and failed_count == 0:
        print("📝 処理対象がありませんでした")
    
    print(f"\n📈 総合結果: 成功{success_count}件 / 失敗{failed_count}件")
    print('='*60)


def main():
    """メイン関数"""
    # ログ設定を初期化
    setup_logging()
    
    parser = argparse.ArgumentParser(description='気象データ変換プロセッサー (JSON→CSV)')
    parser.add_argument('--input-dir', type=str, 
                       default='data/weather/raw/forecast',
                       help='入力ディレクトリパス (デフォルト: data/weather/raw/forecast)')
    parser.add_argument('--date', type=str,
                       help='特定日付のみ処理 (YYYY-MM-DD形式)')
    parser.add_argument('--output-dir', type=str, default='data/weather/processed/forecast',
                       help='出力ディレクトリパス (デフォルト: data/weather/processed/forecast)')
    
    args = parser.parse_args()
    
    # 日付フォーマット検証
    if args.date:
        try:
            datetime.strptime(args.date, '%Y-%m-%d')
        except ValueError:
            print("❌ エラー: 日付はYYYY-MM-DD形式で入力してください")
            return
    
    # プロセッサー初期化
    processor = WeatherProcessor(args.output_dir)
    
    print("🚀 気象データ変換処理開始")
    print(f"📂 入力ディレクトリ: {args.input_dir}")
    print(f"📂 出力ディレクトリ: {args.output_dir}")
    if args.date:
        print(f"📅 日付フィルタ: {args.date}")
    
    try:
        # 変換処理実行
        results = processor.process_directory(args.input_dir, args.date)
        
        # 結果表示
        print_results(results)
        
    except Exception as e:
        logger.error(f"Weather processing failed: {e}")
        print(f"💥 処理エラー: {e}")
        return
    
    print("🏁 気象データ変換完了")


if __name__ == "__main__":
    main()