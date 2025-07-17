"""
気象データBigQuery投入システム

実行方法:
    python -m src.data_processing.weather_bigquery_loader                    # デフォルト: forecast
    python -m src.data_processing.weather_bigquery_loader --data-type historical  # 過去データ
    python -m src.data_processing.weather_bigquery_loader --data-type forecast    # 予測データ
"""

import argparse
from datetime import datetime
from pathlib import Path
from logging import getLogger
from google.cloud import bigquery
from google.cloud import storage

from src.utils.logging_config import setup_logging

# モジュール専用のロガーを取得
logger = getLogger('energy_env.data_processing.weather_bigquery_loader')

class WeatherBigQueryLoader:
    """気象データをBigQueryに投入するクラス"""
    
    def __init__(self, project_id="energy-env", bucket_name="energy-env-data"):
        """
        初期化
        
        Args:
            project_id (str): GCPプロジェクトID
            bucket_name (str): GCSバケット名
        """
        self.project_id = project_id
        self.bucket_name = bucket_name
        self.dataset_id = "dev_energy_data"
        self.table_id = "weather_data"
        
        # BigQueryとGCSクライアントの初期化
        self.bq_client = bigquery.Client(project=project_id)
        self.gcs_client = storage.Client(project=project_id)
        self.bucket = self.gcs_client.bucket(bucket_name)
        
        logger.info(f"WeatherBigQueryLoader initialized: {project_id}")
    
    def get_unprocessed_files(self, data_type="forecast"):
        """
        未処理ファイルの一覧を取得
        
        Args:
            data_type (str): "historical" | "forecast"
            
        Returns:
            list: 未処理ファイルのGCS URIリスト
            
        Raises:
            ValueError: CSV以外のファイルが存在する場合
        """
        prefix = f"weather_processed/{data_type}/"
        
        # delimiter="/" で直下のファイルのみ取得
        blobs = self.gcs_client.list_blobs(
            self.bucket_name, 
            prefix=prefix, 
            delimiter="/"
        )
        
        unprocessed_files = []
        for blob in blobs:
            # CSV以外のファイルがあればエラー
            if not blob.name.endswith('.csv'):
                raise ValueError(f"Unexpected non-CSV file found: {blob.name}")
            
            unprocessed_files.append(f"gs://{self.bucket_name}/{blob.name}")
        
        logger.info(f"Found {len(unprocessed_files)} unprocessed files in {data_type}")
        return unprocessed_files
    
    def create_external_table(self, file_uris):
        """
        EXTERNAL TABLEを作成（生SQL実行）
        
        Args:
            file_uris (list): 処理対象ファイルのGCS URIリスト
        """
        if not file_uris:
            logger.warning("No files to process")
            return
        
        # GCS URIをSQL配列形式に変換
        uris_str = "', '".join(file_uris)
        
        create_sql = f"""
        CREATE OR REPLACE EXTERNAL TABLE `{self.project_id}.{self.dataset_id}.temp_weather_external`
        (
            prefecture STRING,
            date STRING,
            hour STRING,
            temperature_2m FLOAT64,
            relative_humidity_2m FLOAT64,
            precipitation FLOAT64,
            weather_code INT64
        )
        OPTIONS (
            format = 'CSV',
            uris = ['{uris_str}'],
            skip_leading_rows = 1
        );
        """
        
        # 直接SQL文を実行
        job = self.bq_client.query(create_sql)
        job.result()  # 完了まで待機
        
        logger.info(f"Created external table: {self.project_id}.{self.dataset_id}.temp_weather_external with {len(file_uris)} files")
    
    def delete_duplicate_data(self):
        """
        重複データを削除（パーティション絞り込み + CONCAT方式）
        """
        delete_query = f"""
        DELETE FROM `{self.project_id}.{self.dataset_id}.{self.table_id}` 
        WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
          AND date <= CURRENT_DATE()
          AND CONCAT(prefecture, '|', CAST(date AS STRING), '|', hour) IN (
              SELECT CONCAT(prefecture, '|', CAST(PARSE_DATE('%Y-%m-%d', date) AS STRING), '|', hour)
              FROM `{self.project_id}.{self.dataset_id}.temp_weather_external`
              WHERE PARSE_DATE('%Y-%m-%d', date) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
          )
        """
        
        job = self.bq_client.query(delete_query)
        result = job.result()
        
        logger.info(f"Deleted duplicate data: {job.num_dml_affected_rows} rows")
    
    def insert_weather_data(self):
        """
        気象データをBigQueryに投入
        """
        insert_query = f"""
        INSERT INTO `{self.project_id}.{self.dataset_id}.{self.table_id}`
        (prefecture, date, hour, temperature_2m, relative_humidity_2m, precipitation, weather_code, created_at)
        SELECT 
            prefecture,
            PARSE_DATE('%Y-%m-%d', date) as date,
            hour,
            temperature_2m,
            relative_humidity_2m,
            precipitation,
            weather_code,
            CURRENT_TIMESTAMP() as created_at
        FROM `{self.project_id}.{self.dataset_id}.temp_weather_external`
        """
        
        job = self.bq_client.query(insert_query)
        result = job.result()
        
        logger.info(f"Inserted weather data: {job.num_dml_affected_rows} rows")
        return job.num_dml_affected_rows
    
    def drop_external_table(self):
        """
        EXTERNAL TABLEを削除
        """
        external_table_id = f"{self.project_id}.{self.dataset_id}.temp_weather_external"
        
        try:
            self.bq_client.delete_table(external_table_id)
            logger.info(f"Dropped external table: {external_table_id}")
        except Exception as e:
            logger.warning(f"Failed to drop external table: {e}")
    
    def move_processed_files(self, processed_uris, data_type="forecast"):
        """
        処理済みファイルを移動
        
        Args:
            processed_uris (list): 処理済みファイルのGCS URIリスト
            data_type (str): "historical" | "forecast"
        """
        moved_count = 0
        
        for uri in processed_uris:
            try:
                # GCS URIからファイルパスを抽出
                file_path = uri.replace(f"gs://{self.bucket_name}/", "")
                file_name = Path(file_path).name
                
                # 移動先パス
                destination_path = f"weather_processed/{data_type}/insert_completed/{file_name}"
                
                # ファイルをコピー
                source_blob = self.bucket.blob(file_path)
                destination_blob = self.bucket.blob(destination_path)
                
                # コピー実行
                destination_blob.upload_from_string(source_blob.download_as_text())
                
                # 元ファイルを削除
                source_blob.delete()
                
                moved_count += 1
                logger.info(f"Moved processed file: {file_name}")
                
            except Exception as e:
                logger.error(f"Failed to move file {uri}: {e}")
        
        logger.info(f"Moved {moved_count} processed files to insert_completed/")
    
    def load_weather_data(self, data_type="forecast"):
        """
        気象データをBigQueryに投入するメイン処理
        
        Args:
            data_type (str): "historical" | "forecast"
            
        Returns:
            dict: 処理結果
        """
        logger.info(f"Starting weather data load: {data_type}")
        
        try:
            # 1. 未処理ファイルを取得
            unprocessed_files = self.get_unprocessed_files(data_type)
            
            if not unprocessed_files:
                logger.info("No unprocessed files found")
                return {
                    'status': 'success',
                    'message': 'No files to process',
                    'files_processed': 0,
                    'rows_inserted': 0
                }
            
            # 2. EXTERNAL TABLE作成
            self.create_external_table(unprocessed_files)
            
            # 3. 重複データ削除
            self.delete_duplicate_data()
            
            # 4. データ投入
            rows_inserted = self.insert_weather_data()
            
            # 5. EXTERNAL TABLE削除
            self.drop_external_table()
            
            # 6. 成功時のみファイル移動
            self.move_processed_files(unprocessed_files, data_type)
            
            logger.info(f"Weather data load completed: {len(unprocessed_files)} files, {rows_inserted} rows")
            
            return {
                'status': 'success',
                'message': f'Successfully loaded {len(unprocessed_files)} files',
                'files_processed': len(unprocessed_files),
                'rows_inserted': rows_inserted
            }
            
        except Exception as e:
            logger.error(f"Weather data load failed: {e}")
            
            # エラー時はEXTERNAL TABLEを削除
            try:
                self.drop_external_table()
            except:
                pass
            
            return {
                'status': 'failed',
                'message': f'Load failed: {str(e)}',
                'files_processed': 0,
                'rows_inserted': 0
            }


def print_load_results(results):
    """投入結果を表示"""
    print(f"\n{'='*60}")
    print("📊 気象データBigQuery投入結果")
    print('='*60)
    
    status_emoji = {
        'success': '✅',
        'failed': '❌'
    }
    
    print(f"\n{status_emoji[results['status']]} 処理結果")
    print(f"メッセージ: {results['message']}")
    print(f"処理ファイル数: {results['files_processed']}")
    print(f"投入レコード数: {results['rows_inserted']}")
    print('='*60)


def main():
    """メイン関数"""
    # ログ設定を初期化
    setup_logging()
    
    parser = argparse.ArgumentParser(description='気象データBigQuery投入システム')
    parser.add_argument('--data-type', type=str, default='forecast',
                       choices=['historical', 'forecast'],
                       help='データタイプ (historical: 過去データ, forecast: 予測データ)')
    parser.add_argument('--project-id', type=str, default='energy-env',
                       help='GCPプロジェクトID')
    parser.add_argument('--bucket', type=str, default='energy-env-data',
                       help='GCSバケット名')
    
    args = parser.parse_args()
    
    print("🚀 気象データBigQuery投入システム開始")
    print(f"📊 データタイプ: {args.data_type}")
    print(f"☁️  プロジェクト: {args.project_id}")
    print(f"📂 バケット: {args.bucket}")
    
    # 投入処理実行
    loader = WeatherBigQueryLoader(args.project_id, args.bucket)
    results = loader.load_weather_data(args.data_type)
    
    # 結果表示
    print_load_results(results)
    
    print("🏁 処理完了")


if __name__ == "__main__":
    main()