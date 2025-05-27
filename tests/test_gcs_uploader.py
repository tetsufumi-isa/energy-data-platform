"""
GCSUploader 手動テストスクリプト

実行方法:
    VS Code統合ターミナル（Ctrl + `）から実行
    python -m tests.test_gcs_uploader
    
    または
    python tests/test_gcs_uploader.py
"""

from src.data_processing.gcs_uploader import GCSUploader
import os

def print_test_header(test_name):
    """テスト項目のヘッダーを表示"""
    print(f"\n{'='*50}")
    print(f"[TEST] {test_name}")
    print('='*50)

def print_result(success, message):
    """テスト結果を表示"""
    status = "✓ 成功" if success else "✗ 失敗"
    print(f"{status}: {message}")

def test_initialization():
    """GCSUploaderの初期化テスト"""
    print_test_header("GCSUploader初期化テスト")
    
    try:
        uploader = GCSUploader("energy-env-data")
        print_result(True, f"バケット名: {uploader.bucket_name}")
        print_result(True, f"プロジェクトID: {uploader.project_id}")
        return uploader
    except Exception as e:
        print_result(False, f"初期化エラー: {e}")
        return None

def test_single_file_upload(uploader):
    """単一ファイルアップロードテスト"""
    print_test_header("単一ファイルアップロードテスト")
    
    # テスト用ファイルを作成
    test_file = "test_upload.txt"
    test_content = "これはGCSアップロードのテストファイルです。"
    
    try:
        # テストファイル作成
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write(test_content)
        print_result(True, f"テストファイル作成: {test_file}")
        
        # destination_blob_name未指定でアップロード
        uri1 = uploader.upload_file(test_file)
        print_result(True, f"アップロード完了（自動命名）: {uri1}")
        
        # destination_blob_name指定でアップロード
        uri2 = uploader.upload_file(test_file, "test/custom_name.txt")
        print_result(True, f"アップロード完了（カスタム名）: {uri2}")
        
        # URIの形式確認
        if uri1.startswith("gs://energy-env-data/") and uri2.startswith("gs://energy-env-data/"):
            print_result(True, "URI形式が正しい")
        else:
            print_result(False, "URI形式が不正")
        
    except Exception as e:
        print_result(False, f"アップロードエラー: {e}")
    finally:
        # テストファイルを削除
        if os.path.exists(test_file):
            os.remove(test_file)
            print_result(True, "テストファイル削除完了")

def test_directory_upload_no_filter(uploader):
    """ディレクトリアップロードテスト（フィルタなし）"""
    print_test_header("ディレクトリアップロード（全ファイル）")
    
    target_dir = "data/raw/202504"
    
    try:
        if not os.path.exists(target_dir):
            print_result(False, f"テスト対象ディレクトリが存在しません: {target_dir}")
            return
        
        # ディレクトリ内のファイル数を事前にカウント
        file_count = 0
        for root, _, files in os.walk(target_dir):
            file_count += len(files)
        print_result(True, f"対象ディレクトリ内ファイル数: {file_count}")
        
        # アップロード実行
        uris = uploader.upload_directory(target_dir, "test_upload/202504")
        
        print_result(True, f"アップロード完了: {len(uris)}ファイル")
        print(f"ファイル数一致: {len(uris) == file_count}")
        
        # いくつかのURIを表示
        for i, uri in enumerate(uris[:3]):
            print(f"  [{i+1}] {uri}")
        if len(uris) > 3:
            print(f"  ... 他{len(uris)-3}ファイル")
            
    except Exception as e:
        print_result(False, f"ディレクトリアップロードエラー: {e}")

def test_directory_upload_csv_filter(uploader):
    """ディレクトリアップロードテスト（CSVフィルタあり）"""
    print_test_header("ディレクトリアップロード（CSVフィルタ）")
    
    target_dir = "data/raw/202504"
    
    try:
        if not os.path.exists(target_dir):
            print_result(False, f"テスト対象ディレクトリが存在しません: {target_dir}")
            return
        
        # CSVファイル数を事前にカウント
        csv_count = 0
        for root, _, files in os.walk(target_dir):
            csv_count += len([f for f in files if f.endswith('.csv')])
        print_result(True, f"対象ディレクトリ内CSVファイル数: {csv_count}")
        
        # CSVフィルタでアップロード実行
        uris = uploader.upload_directory(target_dir, "test_upload/csv_only", ".csv")
        
        print_result(True, f"CSVアップロード完了: {len(uris)}ファイル")
        print(f"CSV数一致: {len(uris) == csv_count}")
        
        # アップロードされたファイルがすべてCSVか確認
        all_csv = all(uri.endswith('.csv') for uri in uris)
        print_result(all_csv, "すべてCSVファイル" if all_csv else "CSV以外のファイルが含まれている")
        
        # いくつかのURIを表示
        for i, uri in enumerate(uris[:3]):
            print(f"  [{i+1}] {uri}")
        if len(uris) > 3:
            print(f"  ... 他{len(uris)-3}ファイル")
            
    except Exception as e:
        print_result(False, f"CSVフィルタアップロードエラー: {e}")

def test_error_handling(uploader):
    """エラーハンドリングテスト"""
    print_test_header("エラーハンドリングテスト")
    
    # 存在しないファイルのテスト
    try:
        uploader.upload_file("non_existent_file.txt")
        print_result(False, "存在しないファイル: エラーが発生しませんでした")
    except FileNotFoundError as e:
        print_result(True, f"存在しないファイル: 期待通りのエラー - {e}")
    except Exception as e:
        print_result(False, f"存在しないファイル: 予期しないエラー - {e}")
    
    # 存在しないディレクトリのテスト
    try:
        uploader.upload_directory("non_existent_directory")
        print_result(False, "存在しないディレクトリ: エラーが発生しませんでした")
    except NotADirectoryError as e:
        print_result(True, f"存在しないディレクトリ: 期待通りのエラー - {e}")
    except Exception as e:
        print_result(False, f"存在しないディレクトリ: 予期しないエラー - {e}")

def main():
    """メインテスト実行"""
    print("GCSUploader 手動テストスクリプト開始")
    print(f"現在の作業ディレクトリ: {os.getcwd()}")
    
    # 初期化テスト
    uploader = test_initialization()
    if uploader is None:
        print("\n初期化に失敗したため、テストを中止します。")
        return
    
    # 各テストを実行
    test_single_file_upload(uploader)
    test_directory_upload_no_filter(uploader)
    test_directory_upload_csv_filter(uploader)
    test_error_handling(uploader)
    
    print(f"\n{'='*50}")
    print("すべてのテストが完了しました！")
    print("GCS コンソール（https://console.cloud.google.com/storage）で")
    print("アップロードされたファイルを確認してください。")
    print('='*50)

if __name__ == "__main__":
    main()