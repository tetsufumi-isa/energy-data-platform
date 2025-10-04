"""
気象データBigQuery投入システム（JSON対応版）

実行方法:
    python -m src.data_processing.weather_bigquery_loader                    # デフォルト: forecast
    python -m src.data_processing.weather_bigquery_loader --data-type historical  # 過去データ
    python -m src.data_processing.weather_bigquery_loader --data-type forecast    # 予測データ
"""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from logging import getLogger
from google.cloud import bigquery

from src.utils.logging_config import setup_logging

# モジュール専用のロガーを取得
logger = getLogger('energy_env.data_processing.weather_bigquery_loader')

class WeatherBigQueryLoader:
    """気象データをBigQueryに投入するクラス（JSON対応）"""

    def __init__(self, project_id="energy-env", json_dir=None):
        """
        初期化

        Args:
            project_id (str): GCPプロジェクトID
            json_dir (str): JSONファイル格納ディレクトリ
        """
        self.project_id = project_id
        self.dataset_id = "dev_energy_data"
        self.table_id = "weather_data"

        # JSONディレクトリ設定
        energy_env_path = os.getenv('ENERGY_ENV_PATH')
        if energy_env_path is None:
            raise ValueError("ENERGY_ENV_PATH環境変数が設定されていません")

        if json_dir is None:
            self.json_dir = Path(energy_env_path) / 'data' / 'weather' / 'raw' / 'daily'
        else:
            self.json_dir = Path(json_dir)

        # BigQueryクライアントの初期化
        self.bq_client = bigquery.Client(project=project_id)

        logger.info(f"WeatherBigQueryLoader初期化完了: {project_id}, JSONディレクトリ: {self.json_dir}")
    
    def get_unprocessed_json_files(self, data_type="forecast"):
        """
        未処理JSONファイルの一覧を取得

        Args:
            data_type (str): "historical" | "forecast"

        Returns:
            list: 未処理JSONファイルのパスリスト
        """
        pattern = f"*_{data_type}.json"
        json_files = list(self.json_dir.glob(pattern))

        logger.info(f"{data_type}タイプのJSONファイル {len(json_files)}個を検出")
        return json_files
    
    def parse_json_to_rows(self, json_file_path):
        """
        JSONファイルを解析してBQインサート用の行データに変換

        Args:
            json_file_path (Path): JSONファイルパス

        Returns:
            list: BQインサート用の辞書のリスト
        """
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        hourly_data = data.get('hourly', {})
        times = hourly_data.get('time', [])
        temps = hourly_data.get('temperature_2m', [])
        humidity = hourly_data.get('relative_humidity_2m', [])
        precip = hourly_data.get('precipitation', [])
        weather_codes = hourly_data.get('weather_code', [])

        rows = []
        for i, time_str in enumerate(times):
            # time: "2024-10-01T00:00" → date: "2024-10-01", hour: "00"
            dt = datetime.fromisoformat(time_str)
            date_str = dt.strftime('%Y-%m-%d')
            hour_str = dt.strftime('%H')

            row = {
                'prefecture': '千葉県',
                'date': date_str,
                'hour': hour_str,
                'temperature_2m': temps[i] if i < len(temps) else None,
                'relative_humidity_2m': humidity[i] if i < len(humidity) else None,
                'precipitation': precip[i] if i < len(precip) else None,
                'weather_code': weather_codes[i] if i < len(weather_codes) else None,
                'created_at': datetime.now().isoformat()
            }
            rows.append(row)

        logger.info(f"JSONファイル解析完了: {json_file_path.name}, {len(rows)}行")
        return rows
    
    def delete_duplicate_data(self, rows):
        """
        重複データを削除（インサート予定データと重複する既存データを削除）

        Args:
            rows (list): インサート予定のデータ行
        """
        if not rows:
            logger.info("削除対象データなし")
            return

        # インサート予定データから日付範囲を取得
        dates = [row['date'] for row in rows]
        min_date = min(dates)
        max_date = max(dates)

        delete_query = f"""
        DELETE FROM `{self.project_id}.{self.dataset_id}.{self.table_id}`
        WHERE date >= '{min_date}'
          AND date <= '{max_date}'
          AND prefecture = '千葉県'
        """

        job = self.bq_client.query(delete_query)
        result = job.result()

        logger.info(f"重複データ削除完了: {job.num_dml_affected_rows}行削除（期間: {min_date}～{max_date}）")
    
    def insert_weather_data(self, rows):
        """
        気象データをBigQueryに投入

        Args:
            rows (list): BQインサート用のデータ行

        Returns:
            int: インサート行数
        """
        if not rows:
            logger.info("インサート対象データなし")
            return 0

        table_ref = f"{self.project_id}.{self.dataset_id}.{self.table_id}"
        errors = self.bq_client.insert_rows_json(table_ref, rows)

        if errors:
            error_msg = f"BQインサートエラー: {errors}"
            logger.error(error_msg)
            raise Exception(error_msg)

        logger.info(f"気象データインサート完了: {len(rows)}行")
        return len(rows)
    
    def move_processed_files(self, json_files):
        """
        処理済みJSONファイルをアーカイブディレクトリに移動

        Args:
            json_files (list): 処理済みJSONファイルのパスリスト
        """
        archive_dir = self.json_dir / 'archive'
        archive_dir.mkdir(exist_ok=True)

        moved_count = 0
        for json_file in json_files:
            try:
                archive_path = archive_dir / json_file.name
                json_file.rename(archive_path)
                moved_count += 1
                logger.info(f"処理済みファイル移動: {json_file.name} → archive/")
            except Exception as e:
                logger.error(f"ファイル移動失敗 {json_file.name}: {e}")

        logger.info(f"処理済みファイル {moved_count}個をarchive/に移動")
    
    def load_weather_data(self, data_type="forecast"):
        """
        気象データをBigQueryに投入するメイン処理

        Args:
            data_type (str): "historical" | "forecast"

        Returns:
            dict: 処理結果
        """
        logger.info(f"気象データBQ投入開始: {data_type}")

        try:
            # 1. 未処理JSONファイルを取得
            json_files = self.get_unprocessed_json_files(data_type)

            if not json_files:
                logger.info("未処理ファイルなし")
                return {
                    'status': 'success',
                    'message': '処理対象ファイルなし',
                    'files_processed': 0,
                    'rows_inserted': 0
                }

            # 2. JSONファイルを解析してBQ用データに変換
            all_rows = []
            for json_file in json_files:
                rows = self.parse_json_to_rows(json_file)
                all_rows.extend(rows)

            # 3. 重複データ削除
            self.delete_duplicate_data(all_rows)

            # 4. データ投入
            rows_inserted = self.insert_weather_data(all_rows)

            # 5. 成功時のみファイル移動
            self.move_processed_files(json_files)

            logger.info(f"気象データBQ投入完了: {len(json_files)}ファイル, {rows_inserted}行")

            return {
                'status': 'success',
                'message': f'{len(json_files)}ファイルの投入成功',
                'files_processed': len(json_files),
                'rows_inserted': rows_inserted
            }

        except Exception as e:
            logger.error(f"気象データBQ投入失敗: {e}")

            return {
                'status': 'failed',
                'message': f'投入失敗: {str(e)}',
                'files_processed': 0,
                'rows_inserted': 0
            }


def print_load_results(results):
    """投入結果を表示"""
    print(f"\n{'='*60}")
    print("気象データBigQuery投入結果")
    print('='*60)

    status_mark = '成功' if results['status'] == 'success' else '失敗'

    print(f"\n処理結果: {status_mark}")
    print(f"メッセージ: {results['message']}")
    print(f"処理ファイル数: {results['files_processed']}")
    print(f"投入レコード数: {results['rows_inserted']}")
    print('='*60)


def main():
    """メイン関数"""
    # ログ設定を初期化
    setup_logging()

    parser = argparse.ArgumentParser(description='気象データBigQuery投入システム（JSON対応）')
    parser.add_argument('--data-type', type=str, default='forecast',
                       choices=['historical', 'forecast'],
                       help='データタイプ (historical: 過去データ, forecast: 予測データ)')
    parser.add_argument('--project-id', type=str, default='energy-env',
                       help='GCPプロジェクトID')
    parser.add_argument('--json-dir', type=str, default=None,
                       help='JSONファイル格納ディレクトリ')

    args = parser.parse_args()

    print("気象データBigQuery投入システム開始")
    print(f"データタイプ: {args.data_type}")
    print(f"プロジェクト: {args.project_id}")

    # 投入処理実行
    loader = WeatherBigQueryLoader(args.project_id, args.json_dir)
    results = loader.load_weather_data(args.data_type)

    # 結果表示
    print_load_results(results)

    print("処理完了")


if __name__ == "__main__":
    main()