◆download_daily_weather_data
・基準日が無ければ昨日を基準日して、yyyymmddを取得
・基準日から6日前を取得
    ・基準日は引数で受け取った日にちと指定なしで前日にした2パターンあり
・get_historical_data を実行

    ◆get_historical_data
    ・取得時のパラメータ作成
        ・取得する場所：千葉
        ・開始日と終了日設定を日本時間で設定
    ・download_with_retry を実行
    
        ◆download_with_retry
        ・3回までのリトライで気象データを取得
            ・response.get() が取得でjsonが返ってくる
            ・パラメータに沿って複数日を一気に取得
        ・返ってきた結果を辞書に変換し返す
            ・response.json() で辞書に変換
    
    ・返ってきた辞書データを返す

・取得した過去7日分データを historical_data という変数に保存
・

        