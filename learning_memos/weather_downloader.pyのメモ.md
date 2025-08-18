◆main
・パーサーを設定
    ・パーサーは date、output-dir
　
・WeatherDownloaderクラスを初期化
    ◆WeatherDownloader
    ・環境変数を使ってダウンロードパスを作成

・download_daily_weather_dataを実行
    ◆download_daily_weather_data
    ・基準日が無ければ下記
        ・historical_start：現在時刻から10日前の日付
        ・historical_end：現在時刻から3日前の日付
        ※APIの仕様で現在時刻から2日前までは過去データが無いので上記を設定している
        ・get_historical_data を実行

            ◆get_historical_data
            ・取得時のパラメータ作成
                ・取得する場所：千葉
                ・開始日と終了日設定を日本時間で設定
            ・download_with_retry を実行

                ◆download_with_retry
                ・3回までのリトライで気象データを取得
                ・session.get() が取得でjsonをresponceで受け取っている
                    ・jsonはパラメータに沿って複数日を一気に取得
                ・statuscodeが問題なければresponceで返す
            
            ・返ってきたresponceを返す

        ・取得した過去7日分データを historical_response という変数に保存
        ・validate_response を実行
            
            ◆validate_response
                ・jsonが入っているresoponce.json()で辞書データに変換しdataに保存
                ・その辞書を使って想定されたカラムがあるかチェック
                    ・想定するカラム構造は WeatherDownloader の中にあるクラス属性
        
        ・基準日からjsonのファイル名作成
        ・save_json_responseを実行

            ◆save_json_response
                ・jsonを設定したファイル名で保存
                ・パス名を返す
        
        ・get_forecast_dataを実行

            ◆get_forecast_data
            ・取得時のパラメータ作成
                ・取得する場所：千葉
                ・16日先までを取得
            ・download_with_retry を実行

                ◆download_with_retry
                ・3回までのリトライで気象データを取得
                ・session.get() が取得でjsonをresponceで受け取っている
                    ・jsonはパラメータに沿って複数日を一気に取得
                ・statuscodeが問題なければresponceで返す
            
            ・返ってきたresponceを返す
        
        ・取得した16日分予測データを forecast_response という変数に保存
        ・validate_response を実行
            
            ◆validate_response
                ・jsonが入っているresoponce.json()で辞書データに変換しdataに保存
                ・その辞書を使って想定されたカラムがあるかチェック
                    ・想定するカラム構造は WeatherDownloader の中にあるクラス属性

        ・基準日からjsonのファイル名作成
        ・save_json_responseを実行

            ◆save_json_response
                ・jsonを設定したファイル名で保存
                ・パス名を返す
    
    ・基準日の指定があった場合は下記を対応
        ・historical_start：指定した基準日から30日前の日付
        ・historical_end：指定した基準日の日付
        ・get_historical_data を実行

            ◆get_historical_data
            ・取得時のパラメータ作成
                ・取得する場所：千葉
                ・開始日と終了日設定を日本時間で設定
            ・download_with_retry を実行

                ◆download_with_retry
                ・3回までのリトライで気象データを取得
                ・session.get() が取得でjsonをresponceで受け取っている
                    ・jsonはパラメータに沿って複数日を一気に取得
                ・statuscodeが問題なければresponceで返す
            
            ・返ってきたresponceを返す

        ・取得した過去7日分データを historical_response という変数に保存
        ・validate_response を実行
            
            ◆validate_response
                ・jsonが入っているresoponce.json()で辞書データに変換しdataに保存
                ・その辞書を使って想定されたカラムがあるかチェック
                    ・想定するカラム構造は WeatherDownloader の中にあるクラス属性
        
        ・基準日からjsonのファイル名作成
        ・save_json_responseを実行

            ◆save_json_response
                ・jsonを設定したファイル名で保存
                ・パス名を返す
