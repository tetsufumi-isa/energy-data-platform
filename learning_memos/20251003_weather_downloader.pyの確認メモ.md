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
            ・実行結果はargs.date有り無しで以下の通り
                ・args.date有り：args.date30日前～args.dateまでの過去データ取得
                ・args.date無し
                    ・実行10日前～3日前までの過去データ取得
                    ・実行日含めた16日先までの予測データも取得
                ・ダウンロード成功ならそのログ、失敗でもエラーログ生成しBQへインサート
            ・ダウンロードエラーであればここまでエラーが流れてくるのでprintで表示
                ・ダウンロードエラーのログ自体は呼び出し先の関数で作られている

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
                ・historical_filenameとしてjsonのファイルパスを作成
                ・historical_path = self.save_json_response(historical_response, historical_filename)を実行
                    ・データを書き込みして保存してファイルパスを返す
                    ・エラーであればraiseで呼び出しもとにエラーを返す
                ・resultsに過去データ書き込みの概要を記載
                    ・過去データの記載内容
                        ・ダウンロードデータのファイルパス
                        ・ダウンロード期間：10日前から３日前まで
                        ・データ件数(time)を数える
                            ・validation_resultの中に入っている
                        ・save_json_responseで作成して受け取ったvalidation_result
            ・予測データ取得
                ・get_forecast_data(session, forecast_days=16)を実行
                    ・ダウンロードが成功したらbodyを含むセッションをforecast_responseで受け取る
                    ・ダウンロード失敗の時はget_forecast_dataからエラーが流れてくる
                        ・エラーはキャッチしてエラーログを作成し_write_log(log_data)を実行
                            ・log_dataとして受け取ってローカルとBQに保存。
                            　BQ接続エラーの際はそのログもローカルに残す。
                ・validate_response(forecast_response)を実行            
                    ・HTTPセッションから実際に使うデータだけを抜き出し無いように欠損がないかチェックして返す
                    ・エラーがあればフラグで確認できるのでraiseを実行
                        ・ここでのraiseは外側のtryでキャッチしてエラーログを保存           
                ・forecast_filenameとしてjsonのファイルパスを作成
                ・forecast_path = self.save_json_response(historical_response, historical_filename)を実行
                    ・データを書き込みして保存してファイルパスを返す
                    ・エラーであればraiseで呼び出しもとにエラーを返す
                ・resultsに予測データ書き込みの概要を記載
                    ・予測データの記載内容
                        ・ダウンロードデータのファイルパス
                        ・ダウンロード期間：当日含め１６日先まで
                        ・データ件数(time)を数える
                            ・validation_resultの中に入っている
                        ・save_json_responseで作成して受け取ったvalidation_result 
            ・成功ログ取得
                ・ダウンロードにかかった時間を計測
                ・過去と未来のダウンロード結果をlog_dataという辞書として作成
                    ・log_dataはログ用のBQテーブルにあわせた設計なのでそのままインサート可能
            ・_write_log(log_data)実行
                ・ログとなる辞書データをlog_dataとして受け取ってローカルとBQに保存。
    　          　BQ接続エラーの際はそのログもローカルに残す。
            ・sessionを開放
        ・基準日を受け取った場合
            ・基準日を受け取らなかった場合の過去データ取得と基本的には同じ動き
                ・データ書き込み～ログ生成～セッションクローズまで行う
                ・違いは期間
                    ・基準日無しの過去データ取得：実行10日前から3日前までの日付を作成
                    ・基準日ありの過去データ取得：基準日30日前～基準日まで
    ★日付を受け取った場合は日付の30日前～受け取った日付までの過去データ取得。
    　日付無しの場合は実行10日前～3日前までの過去データと実行日含めた16日先までの予測データを取得
    　ダウンロード成功ならそのログ、失敗でもエラーログ生成しBQへインサート。


    ・def get_historical_data(self, session, start_date, end_date)
        ・ダウンロードに必要な設定内容をparamsにまとめる
        ・download_with_retryを(session, self.HISTORICAL_URL, params)で実行
            ・ダウンロードが成功した際にはそれを返す
                ・書き込みは行っていない
            ・ダウンロード成功でないときはエラーが発生し、download_with_retryがエラーをキャッチせずに
            　ここに戻ってくるが、ここでもキャッチせずに更に呼び出しもとに戻す
    ★受け取った期間でダウンロードを実行し成功すれば返す、書き込みは行っていない。
    　ダウンロードが成功していなければエラーを呼び出しもとに返す


    ・def get_forecast_data(self, session, forecast_days=16):
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
            ・validation_resultの形式
                {
                    'valid': True,                  --フラグ
                    'issues': [],                   --問題が発生した際に内容を文章で記載
                    'stats': {'total_hours': 192}   --例：192時間分のデータ
                }
    ★HTTPセッションから実際に使うデータだけを抜き出し無いように欠損がないかチェックして返す
    　

    ・def save_json_response(self, response, filename)
        ・受け取ったデータを書き込みして保存
    ★受け取ったデータを書き込みして保存しファイルパスを返す、エラーであれraiseでエラーを返す