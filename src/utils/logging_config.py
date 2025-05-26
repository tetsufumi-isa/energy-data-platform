# src/utils/logging_config.py

from logging import getLogger, StreamHandler, Formatter, INFO, WARNING
import sys

def setup_logging(level=INFO):
    """アプリケーションのロギング設定をセットアップする
    
    Args:
        level: ロガーのログレベル（デフォルト: INFO）
               DEBUG, INFO, WARNING, ERROR, CRITICALのいずれか
    
    Note:
        この関数は、アプリケーション起動時に一度だけ呼び出してください。
        二回目以降の呼び出しは無視されます（二重設定防止のため）。
    """
    # アプリケーションのトップレベルロガーを取得
    app_logger = getLogger('energy_env')
    
    # 二重設定を避ける
    if len(app_logger.handlers) > 0:
        return
    
    # ログレベルを設定
    app_logger.setLevel(level)
    
    # 共通フォーマットの設定
    formatter = Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    
    # コンソール出力ハンドラー
    console_handler = StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    app_logger.addHandler(console_handler)
    
    # サードパーティーライブラリのログレベルを調整（必要に応じて）
    getLogger('google').setLevel(WARNING)
    getLogger('googleapiclient').setLevel(WARNING)