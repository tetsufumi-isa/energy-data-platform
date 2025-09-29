"""
DataDownloader 手動テストスクリプト

実行方法:
    VS Code統合ターミナル（Ctrl + `）から実行
    python -m tests.test_data_downloader
    
    または
    python tests/test_data_downloader.py
"""

import os
import tempfile
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from src.data_processing.data_downloader import PowerDataDownloader
from src.utils.logging_config import setup_logging

def print_test_header(test_name):
    """テスト項目のヘッダーを表示"""
    print(f"\n{'='*60}")
    print(f"[TEST] {test_name}")
    print('='*60)

def print_result(success, message):
    """テスト結果を表示"""
    status = "✓ 成功" if success else "✗ 失敗"
    print(f"{status}: {message}")

def test_initialization():
    """PowerDataDownloaderの初期化テスト"""
    print_test_header("PowerDataDownloader初期化テスト")
    
    try:
        # デフォルト初期化
        downloader1 = PowerDataDownloader()
        print_result(True, f"デフォルト初期化: base_dir={downloader1.base_dir}")
        
        # カスタムディレクトリ初期化
        downloader2 = PowerDataDownloader("custom/data")
        print_result(True, f"カスタム初期化: base_dir={downloader2.base_dir}")
        
        
        return downloader1
    except Exception as e:
        print_result(False, f"初期化エラー: {e}")
        return None

def test_date_processing():
    """日付処理・エラーハンドリングテスト"""
    print_test_header("日付処理・エラーハンドリングテスト")
    
    downloader = PowerDataDownloader()
    
    # 正常系: 月抽出ロジックのテスト
    try:
        result = downloader.get_month_from_date("20250501")
        expected = "202505"
        if result == expected:
            print_result(True, f"月抽出成功: {result}")
        else:
            print_result(False, f"月抽出失敗: {result} != {expected}")
    except Exception as e:
        print_result(False, f"正常日付でエラー: {e}")
    
    # 異常系: エラーハンドリングのテスト（標準モジュールのエラーを受け取れるか）
    try:
        downloader.get_month_from_date("invalid_date")
        print_result(False, "無効日付がエラーにならない")
    except ValueError:
        print_result(True, "無効日付を正しく検出")
    except Exception as e:
        print_result(False, f"予期しないエラー: {e}")

def test_required_months_calculation():
    """必要月計算ロジックテスト"""
    print_test_header("必要月計算ロジックテスト")
    
    downloader = PowerDataDownloader()
    
    # 現在日付の確認
    today = datetime.today()
    print_result(True, f"今日の日付: {today.strftime('%Y-%m-%d')}")
    
    # 日数別テスト
    test_cases = [1, 5, 10, 35]  # 月跨ぎテスト含む
    
    for days in test_cases:
        try:
            months = downloader.get_required_months(days)
            print_result(True, f"{days}日分の必要月: {sorted(months)}")
            
            # 月数の妥当性チェック（最大2ヶ月まで）
            if len(months) <= 2:
                print_result(True, f"  月数が妥当: {len(months)}ヶ月")
            else:
                print_result(False, f"  月数が多すぎ: {len(months)}ヶ月")
                
        except Exception as e:
            print_result(False, f"{days}日分計算エラー: {e}")

def test_month_validation():
    """月指定バリデーションテスト"""
    print_test_header("月指定バリデーションテスト")
    
    downloader = PowerDataDownloader()
    
    # 正常系: 月フォーマットのテスト
    try:
        # 実際にdownload_for_month()を呼んでバリデーションをテスト
        # （ダウンロードは実行されるが、テスト目的）
        result = downloader.download_for_month("202505")
        print_result(True, "月バリデーション成功")
    except Exception as e:
        print_result(False, f"正常月でエラー: {e}")
    
    # 異常系: 月フォーマットエラーのテスト
    try:
        downloader.download_for_month("invalid_month")
        print_result(False, "不正月がエラーにならない")
    except ValueError as e:
        if "月はYYYYMM形式で入力してください" in str(e):
            print_result(True, f"不正月を正しく検出: {e}")
        else:
            print_result(False, f"予期しないエラーメッセージ: {e}")
    except Exception as e:
        print_result(False, f"予期しないエラー: {e}")

def test_future_date_handling():
    """未来日付・未来月の処理テスト"""
    print_test_header("未来日付・未来月処理テスト")
    
    downloader = PowerDataDownloader()
    
    # 未来の日付（6ヶ月後）
    future_date = datetime.today() + timedelta(days=180)
    future_date_str = future_date.strftime('%Y%m%d')
    future_month_str = future_date.strftime('%Y%m')
    
    print_result(True, f"未来テスト日付: {future_date_str}")
    print_result(True, f"未来テスト月: {future_month_str}")
    
    # 未来日付の処理テスト（新機能：未来日付は拒否される）
    try:
        month = downloader.get_month_from_date(future_date_str)
        print_result(False, f"未来日付が拒否されなかった: {month}")
    except ValueError as e:
        if "計測が完了した昨日までの日付しか指定できません" in str(e):
            print_result(True, f"未来日付を正しく拒否: {e}")
        else:
            print_result(False, f"予期しないエラー: {e}")
    except Exception as e:
        print_result(False, f"未来日付処理で予期しないエラー: {e}")

if __name__ == "__main__":
    print("PowerDataDownloader 手動テストスクリプト開始")
    print(f"現在の作業ディレクトリ: {os.getcwd()}")
    
    # ログ設定を初期化
    setup_logging()
    
    # 基本テスト実行
    print_test_header("テスト開始")
    
    # 初期化テスト
    downloader = test_initialization()
    if downloader is None:
        print("\n初期化に失敗したため、テストを中止します。")
        exit(1)
    
    # 各テストを実行
    test_date_processing()
    test_month_validation()
    test_required_months_calculation()
    test_future_date_handling()
    
    print(f"\n{'='*60}")
    print("Phase 1: 基本機能テスト完了")
    print("次回: ダウンロード機能・コマンドライン引数テストを実装予定")
    print('='*60)