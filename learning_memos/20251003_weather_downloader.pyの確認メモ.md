・class WeatherDownloader
    ・属性
        ・APIエンドポイントのURLを過去/予測どちらも保持
        ・座標は千葉で保持
            ・千葉が最も精度が良かった
        ・取得する気象変数をWEATHER_VARIABLESというリストで保持


    ・def main()
        ・'--date'と'--download-dir'というパーサーを作成
        ・'--date'が無い場合は10日前から3日前までの日付を作成
            ・historical_start：10日前の日付
            ・historical_end：3日前の日付
        ・WeatherDownloaderにargs.download_dir渡して初期化
            ・download_dirは必須ではないのでnoneを渡すこともある
            ・初期化することでダウンロード/ログのディレクトリ作成とBQクライアントのインスタンス作成
        ・download_daily_weather_dataを(args.date)で実行
            ・dateは必須ではないのでnoneを渡すこともある


    ・def __init__(self, download_dir=None):
        ・環境変数を基にダウンロードとログのディレクトリ作成
        ・BQクライアントのインスタンス作成
    ★ダウンロード/ログのディレクトリ作成とBQクライアントのインスタンス作成


    ・def download_daily_weather_data(self, target_date=None):
        ・基準日を受け取らなかった場合
            ・execution_id作成
            ・10日前から3日前までの日付を作成
                ・historical_start：10日前の日付
                ・historical_end：3日前の日付
            ・HTTPセッションとヘッダー設定を定義
            ・resultsという結果を保存する辞書を作成
                ・{'historical': [], 'forecast': []}という構造で作成
            ・過去データ取得
                ・get_historical_data(session, historical_start, historical_end)を実行
                    ・ダウンロードが成功したらbodyを含むセッションをhistorical_responseで受け取る
                    ・ダウンロード失敗の時はget_historical_dataからエラーが流れてくる
                        ・エラーはキャッチしてエラーログを作成し_write_log(log_data)を実行
                            ・log_dataとして受け取ってローカルとBQに保存。
                            　BQ接続エラーの際はそのログもローカルに残す。
                    ・validate_response(historical_response)を実行
                        ・HTTPセッションから実際に使うデータだけを抜き出し無いように欠損がないかチェックして返す
                        ・エラーがあればフラグで確認できるのでraiseを実行
                            ・ここでのraiseは外側のtryでキャッチしてエラーログを保存 
            
            
            
            ・sessionを開放
        ・基準日を受け取った場合
            ・execution_id作成
            ・基準日から30日前までを取得
            ・HTTPセッションとヘッダー設定を定義
            ・get_historical_data(session, historical_start, historical_end)を実行
                ・ダウンロードが成功したらbodyを含むセッションをhistorical_responseで受け取る
                ・ダウンロード失敗の時はget_historical_dataからエラーが流れてくる


    ・def get_historical_data(self, session, start_date, end_date)
        ・ダウンロードに必要な設定内容をparamsにまとめる
        ・download_with_retryを(session, self.HISTORICAL_URL, params)で実行
            ・ダウンロードが成功した際にはそれを返す
                ・書き込みは行っていない
            ・ダウンロード成功でないときはエラーが発生し、download_with_retryがエラーをキャッチせずに
            　ここに戻ってくるが、ここでもキャッチせずに更に呼び出しもとに戻す
    ★受け取った期間でダウンロードを実行し成功すれば返す、書き込みは行っていない。
    　ダウンロードが成功していなければエラーを呼び出しもとに返す


    ・def download_with_retry(self, session, url, params, max_retries=3):
        ・max_retries=3をデフォルトとして3回のfor文
            ・session.get(url, params=params, timeout=30)
                ・params(ダウンロード設定のパラメータが入ったリスト)の設定でresponseで受け取る
                    ・ステータスが200(OK)ならresponseを返す
                        ・responseにダウンロードしたデータが入っている
                            ・書き込みはまだ行っていない
                    ・ステータスが429なら数秒待ってやり直し
                    ・それ以外の場合はresponse.raise_for_status()でエラー発生
                        ・このエラーをrequests.exceptions.RequestExceptionで拾う
                            ・3回目の失敗でなければループを回して3回目ならここでエラーを発生
                                ・このエラー発生時は呼び出し元に戻る
                                    ・このエラーは200(OK)や429(レート制限)どちらでもないエラー
        ・forの途中でダウンロードできるとこの関数抜けるので、forをmax_retries=3でやっても
        　ダウンロードできないときはここでエラーを起こす、このエラーは呼び出しもとに戻る
            ・ここでのエラーは429(レート制限)がmax_retries=3でずっと続いたエラー
    ★ダウンロード設定のparamsに基づいてダウンロードして返す、書き込みは行っていない。
    　200(OK)や429(レート制限)でない場合は呼び出しもとにエラーを返す。429(レート制限)には
    　max_retries=3の回数で対応するが解消しなかったらその場合もエラーを呼び出しもとに返す。
                        

    ・def _write_log(self, log_data):
        ・log_dataで受け取った辞書をローカルにjsonで保存しつつBQにもインサート
            ・ローカルの保存名は日付付き："{log_date}_weather_execution.jsonl"
            ・BQでのインサートがエラーの際にはBQ接続エラーのログもローカルに残す
    ★ログとなる辞書データをlog_dataとして受け取ってローカルとBQに保存。
    　BQ接続エラーの際はそのログもローカルに残す。


    ・def validate_response(self, response):
        ・検証結果を保存する辞書としてvalidation_resultを作成
            ・validというフラグを作成
                ・初期状態はtrue、エラーを見つけたらfalseにする
        ・受け取ったHTTPのセッションをjsonに変換してdataとして受け取る
        ・hourly_data = data['hourly']
            ・天気データのjsonは下記の状態なのでhourlyだけ取り出して使う
                {
                    "latitude": 35.6047,
                    "longitude": 140.1233,
                    "timezone": "Asia/Tokyo",
                    "hourly": {
                        "time": [...],
                        "temperature_2m": [...],
                        "relative_humidity_2m": [...],
                        "precipitation": [...],
                        "weather_code": [...]
                }
        ・天気APIの必要な情報の種別がはいっているWEATHER_VARIABLESをforでまわして
        　それがhourly_dataにあるかチェック
            ・なければその種別をmissing_varsというリストに追加
                ・missing_varsが空でなければ種別が欠けている
                    ・validをfalseにする
                    ・validation_resultのissuesに欠けている種別を記載しておく
        ・hourly_data内のtimeをカウントしてvalidation_resultに記載しておく
        ・エラーは下記の内容でキャッチ
            ・JSONデコードエラー
            ・その他エラー
        ・validation_resultを返す
    ★HTTPセッションから実際に使うデータだけを抜き出し無いように欠損がないかチェックして返す
    　
