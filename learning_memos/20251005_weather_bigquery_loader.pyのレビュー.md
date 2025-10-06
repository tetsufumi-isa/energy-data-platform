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