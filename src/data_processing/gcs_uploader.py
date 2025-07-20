# src/data/gcs_uploader.py

import os
from google.cloud import storage
from logging import getLogger

# モジュール専用のロガーを取得
logger = getLogger('energy_env.data.gcs_uploader')

class GCSUploader:
    """Google Cloud Storageへのファイルアップロードを管理するクラス"""
    
    def __init__(self, bucket_name, project_id=None):
        """
        初期化
        
        Args:
            bucket_name (str): GCSバケット名
            project_id (str, optional): GCPプロジェクトID
        """
        self.bucket_name = bucket_name
        self.project_id = project_id
        self.client = storage.Client(project=project_id)
        self.bucket = self.client.bucket(bucket_name)
        logger.info(f"GCSUploader initialized with bucket: {bucket_name}")
    
    def upload_file(self, local_file_path, destination_blob_name=None):
        """
        ローカルファイルをGCSにアップロードする
        
        Args:
            local_file_path (str): アップロードするローカルファイルのパス
            destination_blob_name (str, optional): GCS上での保存先パス。
                                                 未指定の場合はファイル名のみを使用
        
        Returns:
            str: アップロードされたファイルのGCS上のURI
            
        Raises:
            FileNotFoundError: ローカルファイルが存在しない場合
        """
        if not os.path.exists(local_file_path):
            raise FileNotFoundError(f"Local file not found: {local_file_path}")
        
        # 保存先パスが指定されていない場合は、ファイル名のみを使用
        if destination_blob_name is None:
            destination_blob_name = os.path.basename(local_file_path)
        
        # Blobオブジェクトを作成
        blob = self.bucket.blob(destination_blob_name)
        
        # ファイルをアップロード
        blob.upload_from_filename(local_file_path)
        
        logger.info(f"File {local_file_path} uploaded to {destination_blob_name}")
        
        # GCS URIを返す
        return f"gs://{self.bucket_name}/{destination_blob_name}"
    
    def upload_directory(self, local_dir_path, destination_prefix="", file_extension=None):
        """
        ローカルディレクトリ内のファイルをGCSにアップロードする
        CSVファイルは1時間データに加工してからアップロード
        
        Args:
            local_dir_path (str): アップロードするローカルディレクトリのパス
            destination_prefix (str, optional): GCS上でのプレフィックス（フォルダ構造）
            file_extension (str, optional): 特定の拡張子を持つファイルのみをアップロード
        
        Returns:
            list: アップロードされたファイルのGCS上のURIのリスト
        
        Raises:
            NotADirectoryError: 指定されたパスがディレクトリでない場合
        """
        if not os.path.isdir(local_dir_path):
            raise NotADirectoryError(f"Not a directory: {local_dir_path}")
        
        uploaded_uris = []
        
        # ディレクトリ内のファイルをリストアップ
        for root, _, files in os.walk(local_dir_path):
            for file in files:
                # 拡張子フィルタリング
                if file_extension and not file.endswith(file_extension):
                    continue
                
                # ローカルファイルパスを作成
                local_file_path = os.path.join(root, file)
                
                # GCS上の保存先パスを作成（相対パスを維持）
                rel_path = os.path.relpath(local_file_path, local_dir_path)
                gcs_path = os.path.join(destination_prefix, rel_path).replace("\\", "/")
                
                # CSVファイルの場合は加工処理を行う
                if file.endswith('.csv'):
                    try:
                        # CSVファイルを1時間データに加工
                        processed_file_path = self._process_raw_csv_to_hourly(local_file_path)
                        
                        # GCS上でも _hourly ファイル名に統一
                        gcs_filename = file.replace('_power_usage.csv', '_hourly.csv')
                        processed_gcs_path = gcs_path.replace(file, gcs_filename)
                        
                        # 加工済みファイルをアップロード
                        uri = self.upload_file(processed_file_path, processed_gcs_path)
                        uploaded_uris.append(uri)
                        
                        # 加工済み一時ファイルを削除
                        os.remove(processed_file_path)
                        
                        # 原形CSVファイルを削除
                        os.remove(local_file_path)
                        logger.info(f"Processed and uploaded CSV: {file} -> {gcs_filename}")
                        
                    except Exception as e:
                        logger.error(f"Failed to process CSV file {file}: {e}")
                        # 加工に失敗した場合は原形ファイルをそのままアップロード
                        uri = self.upload_file(local_file_path, gcs_path)
                        uploaded_uris.append(uri)
                        
                else:
                    # CSV以外（ZIPファイル等）はそのままアップロード
                    uri = self.upload_file(local_file_path, gcs_path)
                    uploaded_uris.append(uri)
        
        logger.info(f"Uploaded {len(uploaded_uris)} files from {local_dir_path} to GCS")
        return uploaded_uris
    
    def _process_raw_csv_to_hourly(self, input_csv_path):
        """
        東電の原形CSVから1時間データのみを抽出してBigQuery用フォーマットに変換
        
        Args:
            input_csv_path (str): 入力CSVファイルパス
            
        Returns:
            str: 加工済みCSVファイルのパス
            
        Raises:
            ValueError: CSVの構造が期待と異なる場合
        """
        # 加工済みファイルのパスを生成
        base_name = os.path.basename(input_csv_path)
        dir_name = os.path.dirname(input_csv_path)
        processed_filename = base_name.replace('_power_usage.csv', '_hourly_temp.csv')
        output_csv_path = os.path.join(dir_name, processed_filename)
        
        try:
            logger.info(f"Processing CSV to hourly data: {input_csv_path}")
            
            # Shift-JISエンコーディングでCSV読み込み
            with open(input_csv_path, 'r', encoding='shift-jis') as f:
                content = f.read()
            
            # メインデータ部分を特定
            lines = content.split('\n')
            
            # 出力用データを準備
            output_lines = []
            output_lines.append('date,hour,actual_power,supply_capacity')  # ヘッダー
            
            # ヘッダー行（DATE,TIME...）を見つける
            header_line_index = -1
            for i, line in enumerate(lines):
                if 'DATE,TIME,当日実績(万kW)' in line:
                    header_line_index = i
                    break
            
            if header_line_index == -1:
                raise ValueError("Header line not found in CSV")
            
            # ヘッダーの次行から24行処理
            processed_count = 0
            for i in range(header_line_index + 1, min(header_line_index + 25, len(lines))):
                line = lines[i].strip()
                if not line:
                    continue
                    
                parts = line.split(',')
                if len(parts) >= 6:
                    try:
                        # 日付の抽出（"2025/4/1" → "2025-04-01"）
                        date_str = parts[0].strip()
                        # 日付フォーマットを統一
                        date_parts = date_str.split('/')
                        if len(date_parts) == 3:
                            year = date_parts[0]
                            month = date_parts[1].zfill(2)  # 1桁月を2桁に
                            day = date_parts[2].zfill(2)    # 1桁日を2桁に
                            formatted_date = f"{year}-{month}-{day}"
                        else:
                            formatted_date = date_str
                        
                        # 時刻の抽出（"13:00" → 13）
                        time_str = parts[1].strip()
                        hour = int(time_str.split(':')[0])
                        hour_str = str(hour).zfill(2)  # 追加：2桁ゼロ埋め

                        # データの抽出
                        actual_power = float(parts[2])
                        supply_capacity = float(parts[5])
                        
                        # BigQuery用行データ作成
                        output_line = f"{formatted_date},{hour_str},{actual_power},{supply_capacity}"
                        output_lines.append(output_line)
                        processed_count += 1
                        
                    except (ValueError, IndexError) as e:
                        logger.warning(f"Skipping invalid row {i}: {line} - {e}")
                        continue
            
            # 出力CSVファイルに書き込み
            with open(output_csv_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(output_lines))
            
            logger.info(f"Successfully processed {processed_count} hourly records to {output_csv_path}")
            return output_csv_path
            
        except Exception as e:
            logger.error(f"Error processing CSV to hourly data: {e}")
            raise