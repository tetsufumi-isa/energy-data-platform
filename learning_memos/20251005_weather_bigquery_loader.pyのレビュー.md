・class WeatherBigQueryLoader
    ・main()
        ・アーグパースを作成
            ・'--data-type'
                ・historical: 過去データ, forecast: 予測データ
                ・このパラメータは必須
            ・'--project-id'
            ・'--raw-data-dir'
            ・'--target-date'
                ・YYYY-MM-DD形式
    ・loader = WeatherBigQueryLoader(args.project_id, args.raw_data_dir)を実行
        ・BQやディレクトリなどのインサートに必要な環境の設定を完了させる
    ・results = loader.load_weather_data(args.data_type, args.target_date)を実行
        ・execution_idを作成し、ルールに沿ったjsonのパスを作成しデータを取得、
    　  　欠損値確認しBQのスキーマにあわせた辞書を作成しログテーブルへインサート。
    　  　インサートの成功/失敗時にあわせてログも作成しそのログもローカルへ保存しつつ
    　  　ログテーブルへインサート。処理が終わったファイルはアーカイブフォルダへ移動。
    　  　成功/失敗時にあわせて作成された辞書を返す。
    ・結果のresultsを表示して終了


    ・def __init__(self, project_id="energy-env", json_dir=None):
        ・下記を作成
            ・BQに関して
                ・プロジェクトID
                ・データセットID
                ・電力データをインサートするテーブル名
                ・ログをインサートするテーブル名
                ・BQクライアント
                ・上記はBQの設計と同じと確認済
            ・ディレクトリに関して
                ・電力APIの保存ディレクトリをraw_data_dirとして保存
                    ・weather_downloader.pyと整合性があること確認済
                ・ログのディレクトリ
    ★BQやディレクトリなどのインサートに必要な環境の設定を完了させる


    ・def load_weather_data(self, data_type, target_date=None):
        ・execution_id作成
        ・受け取ったdata_typeやtarget_dateからjsonのファイルパス作成
        ・if not json_file.exists():を実行
            ・exists()はファイルが存在するかのチェック
            ・notが付いているのでこのif文はjsonが存在しないとtrue
                ・trueの場合はraise
        ・rows = self.parse_json_to_rows(json_file)を実行
            ・欠損値チェックをして問題なければjsonをBQスキーマにあわせた
            　rowsを受け取る
        ・self.delete_duplicate_data(rows)を実行
            ・投入予定のデータと重複する日付をBQテーブルから削除するクエリを流す
        ・bq_client.insert_rows_json()実行でインサート
            ・このメソッドは常にerros[]を返すが成功したら空で返す
                ・if errorsでtrueならraise
        ・move_processed_files(self, json_files):を実行
            ・インサートのエラーならここまで落ちてこないので
            　これが実行する時はインサート成功の前提
                ・処理済ファイルを受け取ってアーカイブへ移動
        ・成功のログをBQのログテーブルスキーマにあわせた辞書のlog_dataとして作成
        ・_write_log(log_data)を実行
            ・成功ログをローカルへ保存しとBQテーブルへインサート。
    　      　インサートエラー時にはそのログをローカルへ保存。
        ・bq_client.insert_rows_json()のエラー時にはエラーのログを作成し
        　_write_log(log_data)を実行
        ・成功/失敗それぞれにあわせて辞書を作成し返す
    ★execution_idを作成し、ルールに沿ったjsonのパスを作成しデータを取得、
    　欠損値確認しBQのスキーマにあわせた辞書を作成しログテーブルへインサート。
    　インサートの成功/失敗時にあわせてログも作成しそのログもローカルへ保存しつつ
    　ログテーブルへインサート。処理が終わったファイルはアーカイブフォルダへ移動。
    　成功/失敗時にあわせて作成された辞書を返す。
    

    ・def parse_json_to_rows(self, json_file_path):
        ・jsonを開いてBQのスキーマに必要な要素を抜き出して
        　それぞれリストや辞書として持つ
            ・hourly_data = data.get('hourly', {})
            ・times = hourly_data.get('time', [])
            ・temps = hourly_data.get('temperature_2m', [])
            ・humidity = hourly_data.get('relative_humidity_2m', [])
            ・precip = hourly_data.get('precipitation', [])
            ・weather_codes = hourly_data.get('weather_code', [])
        ・時間以外の要素の長さが入った辞書をdata_lengthsとして持つ
            data_lengths = {
                'time': len(times),
                'temperature_2m': len(temps),
                'relative_humidity_2m': len(humidity),
                'precipitation': len(precip),
                'weather_code': len(weather_codes)
            }        
        ・data_lengthsをfor文で回してtimesの長さと不一致
        　つまり欠損値があったらエラーをだす
            ・エラーがなければrowsという時間ごとのデータを保存するリストを作成
            ・timesをforで回してrowを作成
                row = {
                        'prefecture': '千葉県',
                        'date': date_str,
                        'hour': hour_str,
                        'temperature_2m': temps[i],
                        'relative_humidity_2m': humidity[i],
                        'precipitation': precip[i],
                        'weather_code': weather_codes[i],
                        'created_at': datetime.now().isoformat()
                    }
        ・rowsにrowを追加して返す
    ★ダウンロードされたjsonを開いて欠損値を確認した後にBQのスキーマにあわせた
    　rowsを返す


    ・def delete_duplicate_data(self, rows):
        ・投入予定のrowsから日付だけを取り出す
        ・取り出した日付のmaxとminを割り出す
        ・日付のmin～maxの期間のデータを削除するクエリを流す
            ・過去に予測として取得した期間が残っているので
            　過去データとして取り直したときにはこのロジックで
            　削除できる        
    ★投入予定のデータと重複する日付をBQテーブルから削除するクエリを流す


    ・def move_processed_files(self, json_files):
    ★処理済ファイルを受け取ってアーカイブへ移動


    ・def _write_log(self, log_data):
        ・受け取ったlog_data(成功ログの辞書)をjsonとしてローカルに保存
        ・log_dataをBQへインサート
            ・インサートのエラーはローカルにログ保存
    ★成功ログをローカルへ保存しとBQテーブルへインサート。
    　インサートエラー時にはそのログをローカルへ保存。