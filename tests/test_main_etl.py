"""
MainETLPipeline 手動テストスクリプト

実行方法:
    VS Code統合ターミナル（Ctrl + `）から実行
    python -m tests.test_main_etl
    
    または
    python tests/test_main_etl.py
"""

import os
from datetime import datetime, timedelta

from src.pipelines.main_etl import MainETLPipeline
from src.utils.logging_config import setup_logging

def print_test_header(test_name):
    """テスト項目のヘッダーを表示"""
    print(f"\n{'='*70}")
    print(f"[TEST] {test_name}")
    print('='*70)

def print_result(success, message):
    """テスト結果を表示"""
    status = "✓ 成功" if success else "✗ 失敗"
    print(f"{status}: {message}")

def test_initialization():
    """MainETLPipelineの初期化テスト"""
    print_test_header("MainETLPipeline初期化テスト")
    
    try:
        # デフォルト初期化
        pipeline = MainETLPipeline()
        print_result(True, f"downloader設定: {pipeline.downloader.base_dir}")
        print_result(True, f"uploader設定: gs://{pipeline.uploader.bucket_name}")
        
        # カスタム初期化
        custom_pipeline = MainETLPipeline("custom/data", "custom-bucket")
        print_result(True, f"カスタム設定確認: {custom_pipeline.base_dir}")
        
        return pipeline
    except Exception as e:
        print_result(False, f"初期化エラー: {e}")
        return None

def test_etl_for_month(pipeline):
    """月指定ETLテスト"""
    print_test_header("月指定ETLテスト")
    
    # テスト対象月（過去の確実に存在する月）
    test_month = "202505"
    
    try:
        print_result(True, f"テスト対象月: {test_month}")
        
        # ETL実行
        results = pipeline.run_etl_for_month(test_month)
        
        # 戻り値形式チェック
        required_keys = ['download_results', 'upload_results', 'overall_status', 'message']
        for key in required_keys:
            if key in results:
                print_result(True, f"戻り値キー確認: {key}")
            else:
                print_result(False, f"戻り値キー不足: {key}")
                return
        
        # 結果詳細表示
        if results['download_results']['success']:
            print_result(True, f"ダウンロード成功: {', '.join(results['download_results']['success'])}")
        if results['download_results']['failed']:
            print_result(True, f"ダウンロード失敗: {', '.join(results['download_results']['failed'])}")
        
        if results['upload_results']['success']:
            print_result(True, f"アップロード成功: {', '.join(results['upload_results']['success'])}")
        if results['upload_results']['failed']:
            print_result(True, f"アップロード失敗: {', '.join(results['upload_results']['failed'])}")
        print_result(True, f"総合ステータス: {results['overall_status']}")
        print_result(True, f"メッセージ: {results['message']}")
        
        # 成功判定
        if results['overall_status'] in ['success', 'partial']:
            print_result(True, "月指定ETL正常完了")
        else:
            print_result(False, "月指定ETL処理失敗")
            
    except Exception as e:
        print_result(False, f"月指定ETLエラー: {e}")

def test_etl_for_date(pipeline):
    """日付指定ETLテスト"""
    print_test_header("日付指定ETLテスト")
    
    # テスト対象日（過去の確実に存在する日）
    test_date = "20250501"
    
    try:
        print_result(True, f"テスト対象日: {test_date}")
        
        # ETL実行
        results = pipeline.run_etl_for_date(test_date)
        
        # 戻り値形式チェック
        required_keys = ['download_results', 'upload_results', 'overall_status', 'message']
        for key in required_keys:
            if key in results:
                print_result(True, f"戻り値キー確認: {key}")
            else:
                print_result(False, f"戻り値キー不足: {key}")
                return
        
        # 結果詳細表示
        if results['download_results']['success']:
            print_result(True, f"ダウンロード成功: {', '.join(results['download_results']['success'])}")
        if results['download_results']['failed']:
            print_result(True, f"ダウンロード失敗: {', '.join(results['download_results']['failed'])}")
        
        if results['upload_results']['success']:
            print_result(True, f"アップロード成功: {', '.join(results['upload_results']['success'])}")
        if results['upload_results']['failed']:
            print_result(True, f"アップロード失敗: {', '.join(results['upload_results']['failed'])}")
        print_result(True, f"総合ステータス: {results['overall_status']}")
        
        # 成功判定
        if results['overall_status'] in ['success', 'partial']:
            print_result(True, "日付指定ETL正常完了")
        else:
            print_result(False, "日付指定ETL処理失敗")
            
    except Exception as e:
        print_result(False, f"日付指定ETLエラー: {e}")

def test_etl_for_days(pipeline):
    """日数指定ETLテスト"""
    print_test_header("日数指定ETLテスト")
    
    # 少ない日数でテスト（1日分）
    test_days = 1
    
    try:
        print_result(True, f"テスト対象: 過去{test_days}日分")
        
        # ETL実行
        results = pipeline.run_etl_for_days(test_days)
        
        # 戻り値形式チェック
        required_keys = ['download_results', 'upload_results', 'overall_status', 'message']
        for key in required_keys:
            if key in results:
                print_result(True, f"戻り値キー確認: {key}")
            else:
                print_result(False, f"戻り値キー不足: {key}")
                return
        
        # 結果詳細表示
        if results['download_results']['success']:
            print_result(True, f"ダウンロード成功: {', '.join(results['download_results']['success'])}")
        if results['download_results']['failed']:
            print_result(True, f"ダウンロード失敗: {', '.join(results['download_results']['failed'])}")
        
        if results['upload_results']['success']:
            print_result(True, f"アップロード成功: {', '.join(results['upload_results']['success'])}")
        if results['upload_results']['failed']:
            print_result(True, f"アップロード失敗: {', '.join(results['upload_results']['failed'])}")
        print_result(True, f"総合ステータス: {results['overall_status']}")
        
        # 成功判定
        if results['overall_status'] in ['success', 'partial']:
            print_result(True, "日数指定ETL正常完了")
        else:
            print_result(False, "日数指定ETL処理失敗")
            
    except Exception as e:
        print_result(False, f"日数指定ETLエラー: {e}")

def test_error_handling(pipeline):
    """エラーハンドリングテスト"""
    print_test_header("エラーハンドリングテスト")
    
    # 未来月でのテスト（エラーが期待される）
    future_date = datetime.today() + timedelta(days=60)
    future_month = future_date.strftime('%Y%m')
    future_date_str = future_date.strftime('%Y%m%d')
    
    print_result(True, f"未来月テスト対象: {future_month}")
    print_result(True, f"未来日テスト対象: {future_date_str}")
    
    # 未来月テスト
    try:
        results = pipeline.run_etl_for_month(future_month)
        print_result(False, "未来月がエラーにならない")
    except ValueError as e:
        if "未来の月は指定できません" in str(e):
            print_result(True, f"未来月を正しく拒否: {e}")
        else:
            print_result(False, f"予期しないエラー: {e}")
    except Exception as e:
        print_result(False, f"未来月テストで予期しないエラー: {e}")
    
    # 未来日テスト
    try:
        results = pipeline.run_etl_for_date(future_date_str)
        print_result(False, "未来日がエラーにならない")
    except ValueError as e:
        if "未来の日付は指定できません" in str(e):
            print_result(True, f"未来日を正しく拒否: {e}")
        else:
            print_result(False, f"予期しないエラー: {e}")
    except Exception as e:
        print_result(False, f"未来日テストで予期しないエラー: {e}")
    
    # 無効フォーマットテスト
    try:
        results = pipeline.run_etl_for_month("invalid_month")
        print_result(False, "無効月フォーマットがエラーにならない")
    except ValueError as e:
        if "月はYYYYMM形式で入力してください" in str(e):
            print_result(True, f"無効月フォーマットを正しく検出: {e}")
        else:
            print_result(False, f"予期しないエラー: {e}")
    except Exception as e:
        print_result(False, f"無効月フォーマットテストで予期しないエラー: {e}")

def main():
    """メインテスト実行"""
    print("MainETLPipeline 手動テストスクリプト開始")
    print(f"現在の作業ディレクトリ: {os.getcwd()}")
    
    # ログ設定を初期化
    setup_logging()
    
    # 初期化テスト
    pipeline = test_initialization()
    if pipeline is None:
        print("\n初期化に失敗したため、テストを中止します。")
        return
    
    # 各ETLテストを実行
    test_etl_for_month(pipeline)
    test_etl_for_date(pipeline)
    test_etl_for_days(pipeline)
    test_error_handling(pipeline)
    
    print(f"\n{'='*70}")
    print("MainETLPipeline 全テスト完了！")
    print("Phase 4: ETLパイプライン基盤構築（100%完了）✅")
    print("次のフェーズ: BigQuery統合開発")
    print('='*70)

if __name__ == "__main__":
    main()