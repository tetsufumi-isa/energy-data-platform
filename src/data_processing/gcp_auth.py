"""
GCP認証とクラウドサービス接続テスト用モジュール
"""
import os
from google.cloud import storage
from google.cloud import bigquery

def test_gcs_connection():
    """Google Cloud Storageへの接続をテスト"""
    try:
        # GCSクライアントの初期化
        storage_client = storage.Client()
        
        # バケット一覧の取得
        buckets = list(storage_client.list_buckets())
        
        print(f"GCS接続成功: {len(buckets)}個のバケットが見つかりました")
        for bucket in buckets:
            print(f" - {bucket.name}")
        
        return True
    except Exception as e:
        print(f"GCS接続エラー: {e}")
        return False

def test_bigquery_connection():
    """BigQueryへの接続をテスト"""
    try:
        # BigQueryクライアントの初期化
        bq_client = bigquery.Client()
        
        # データセット一覧の取得
        datasets = list(bq_client.list_datasets())
        
        print(f"BigQuery接続成功: {len(datasets)}個のデータセットが見つかりました")
        for dataset in datasets:
            print(f" - {dataset.dataset_id}")
        
        return True
    except Exception as e:
        print(f"BigQuery接続エラー: {e}")
        return False

if __name__ == "__main__":
    # 環境変数の確認
    cred_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
    print(f"認証キーのパス: {cred_path}")
    
    # GCS接続テスト
    gcs_result = test_gcs_connection()
    
    # BigQuery接続テスト
    bq_result = test_bigquery_connection()
    
    # 総合結果
    if gcs_result and bq_result:
        print("すべての接続テストに成功しました！")
    else:
        print("一部の接続テストに失敗しました。エラーメッセージを確認してください。")