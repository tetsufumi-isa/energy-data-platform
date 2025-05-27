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
                
                # ファイルをアップロード
                uri = self.upload_file(local_file_path, gcs_path)
                uploaded_uris.append(uri)
        
        logger.info(f"Uploaded {len(uploaded_uris)} files from {local_dir_path} to GCS")
        return uploaded_uris