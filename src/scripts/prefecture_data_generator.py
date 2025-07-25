"""
都県別電力×気象データ自動生成スクリプト（調査用・書き捨て）

用途: 気温×祝日×都県別分析のための一時的データ生成
実行: python src/scripts/prefecture_data_generator.py

注意: 探索的データ分析用の使い捨てスクリプトです
"""

import os
import pandas as pd
from google.cloud import bigquery
from pathlib import Path
from logging import getLogger

# ログ設定
logger = getLogger(__name__)

class PrefectureDataGenerator:
    """都県別データ生成クラス"""
    
    def __init__(self, project_id="energy-env"):
        """初期化"""
        self.project_id = project_id
        self.client = bigquery.Client(project=project_id)
        # 絶対パス指定
        self.output_dir = Path(r"C:/Users/tetsu/dev/energy-env/data/exploration")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 関東9都県
        self.prefectures = [
            'tokyo', 'kanagawa', 'saitama', 'chiba',
            'ibaraki', 'tochigi', 'gunma', 'yamanashi', 'shizuoka'
        ]
        
        logger.info(f"Prefecture data generator initialized for {len(self.prefectures)} prefectures")
    
    def create_prefecture_query(self, prefecture):
        """都県別統合クエリ生成"""
        query = f"""
        SELECT 
            -- 電力データ
            energy.date,
            energy.hour,
            energy.actual_power,
            energy.supply_capacity,
            
            -- 気象データ
            weather.prefecture,
            weather.temperature_2m,
            weather.relative_humidity_2m,
            weather.precipitation,
            weather.weather_code,
            
            -- カレンダーデータ
            calendar.day_of_week,
            calendar.is_weekend,
            calendar.is_holiday,
            
            -- 派生項目
            EXTRACT(MONTH FROM energy.date) as month
            
        FROM `{self.project_id}.dev_energy_data.energy_data_hourly` energy
        LEFT JOIN `{self.project_id}.dev_energy_data.weather_data` weather 
            ON energy.date = weather.date 
            AND energy.hour = CAST(weather.hour AS INTEGER)
            AND weather.prefecture = '{prefecture}'
        LEFT JOIN `{self.project_id}.dev_energy_data.calendar_data` calendar
            ON energy.date = calendar.date
        WHERE weather.prefecture IS NOT NULL
        ORDER BY energy.date, energy.hour
        """
        return query
    
    def generate_prefecture_data(self, prefecture):
        """都県別データ生成・保存"""
        try:
            logger.info(f"Generating data for {prefecture}...")
            
            # クエリ実行
            query = self.create_prefecture_query(prefecture)
            df = self.client.query(query).to_dataframe()
            
            # データ確認
            logger.info(f"{prefecture}: {len(df)} records retrieved")
            if len(df) == 0:
                logger.warning(f"No data found for {prefecture}")
                return None
            
            # CSV保存
            csv_filename = f"{prefecture}_power_weather.csv"
            csv_path = self.output_dir / csv_filename
            df.to_csv(csv_path, index=False, encoding='utf-8')
            
            logger.info(f"{prefecture}: Saved to {csv_path}")
            return csv_path
            
        except Exception as e:
            logger.error(f"Error generating data for {prefecture}: {e}")
            return None
    
    def generate_all_prefectures(self):
        """全都県データ自動生成"""
        results = {'success': [], 'failed': []}
        
        print(f"🚀 Starting data generation for {len(self.prefectures)} prefectures...")
        
        for i, prefecture in enumerate(self.prefectures, 1):
            print(f"📊 Processing {prefecture} ({i}/{len(self.prefectures)})...")
            
            csv_path = self.generate_prefecture_data(prefecture)
            
            if csv_path:
                results['success'].append({
                    'prefecture': prefecture,
                    'csv_path': str(csv_path)
                })
                print(f"✅ {prefecture}: Success")
            else:
                results['failed'].append(prefecture)
                print(f"❌ {prefecture}: Failed")
        
        return results
    



def print_results(results):
    """結果表示"""
    success_count = len(results['success'])
    failed_count = len(results['failed'])
    
    print(f"\n{'='*60}")
    print("📊 都県別データ生成結果")
    print('='*60)
    
    if results['success']:
        print(f"\n✅ 成功: {success_count}都県")
        for item in results['success']:
            print(f"  {item['prefecture']}: {Path(item['csv_path']).name}")
    
    if results['failed']:
        print(f"\n❌ 失敗: {failed_count}都県")
        for prefecture in results['failed']:
            print(f"  {prefecture}")
    
    print(f"\n📈 総合結果: 成功{success_count}件 / 失敗{failed_count}件")
    print(f"📂 保存先: C:/Users/tetsu/dev/energy-env/data/exploration/")
    print('='*60)


def main():
    """メイン実行"""
    # データ生成器初期化
    generator = PrefectureDataGenerator()
    
    # 全都県データ生成実行
    results = generator.generate_all_prefectures()
    
    # 結果表示
    print_results(results)
    
    # 成功したファイル一覧表示
    if results['success']:
        print("\n📋 生成されたファイル:")
        for item in results['success']:
            csv_path = Path(item['csv_path'])
            file_size = csv_path.stat().st_size / 1024 / 1024  # MB
            print(f"  {csv_path.name}: {file_size:.1f}MB")


if __name__ == "__main__":
    main()