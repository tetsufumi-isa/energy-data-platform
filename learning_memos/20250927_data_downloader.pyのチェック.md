・main
    ・default_base_dir が data/raw のパス
    ・パーサーで下記を設定
        ・days：遡る日数
        ・month：指定月
        ・date：特定日
        ・base-dir：保存先ディレクトリ(デフォルトはdefault_base_dir)
        ・パーサーの排他チェックも設定
    ・downloader = PowerDataDownloader(args.base_dir)
        ・base_dir作成、log_dir作成、bigquery.Client()でテーブル名も設定
    ・実行モードによって以下を実行
        ・args.month：downloader.download_for_month(args.month)
            ・uuid作成、zipダウンロードおよび解凍、ログデータ作成(uuid含む)、ログデータをローカルに保存、BQのテーブルにインサート、
            　成功/失敗が入ったdownload_for_monthの results を main のローカル変数の results として保存
        ・args.date：downloader.download_for_date(args.date)
            ・日付から月を作成、uuid作成、zipダウンロードおよび解凍、ログデータ作成(uuid含む)、ログデータをローカルに保存、
            　BQのテーブルにインサート、成功/失敗が入ったdownload_for_monthの results を main のローカル変数の results として保存
        ・args.days:：downloader.download_for_days(args.days)
            ・入力した日数分、昨日から戻って対応する複数の日付に対応する月全てを取得しそのすべての月に対して
        　  　uuid作成、zipダウンロードおよび解凍、ログデータ作成(uuid含む)、ログデータをローカルに保存、BQのテーブルにインサートし
        　  　成功/失敗の月をresultsとして返す
    ・結果を表示


・PowerDataDownloader
    ・init
        ・引数の base_dir が none か確認
            ・none の場合
                ・energy_env_path に環境変数の ENERGY_ENV_PATH を利用
                ・ENERGY_ENV_PATH が設定されていなければエラーメッセージ
                ・base_dir に data/raw を設定
                ・log_dir に logs/tepco_api を設定
            ・none ではない場合
                ・log_dir に logs/tepco_api を設定
        ・bigquery.Client()でテーブル名も設定
        ★base_dir作成、log_dir作成、bigquery.Client()でテーブル名も設定
    

    ・_write_log
        ・download_month_data で作成した log_data というログデータの辞書を json ファイルとして保存
        ・init で取得済のBQのテーブルに log_data をインサート
        ★log_data を json としてローカルに保存しつつBQのテーブルにインサート
    

    ・get_months_from_date
        ・日付の入力形式チェック
        ・入力された日付が今日以降となっていないかチェック
        ・日付から月を作成してmonthとして返す
        ★日付の入力形式と昨日までの入力となっているかチェックして月をmonthとして返す
    

    ・get_required_months
        ・昨日から入力した日数分をマイナスした日付全てを取得
        ・その複数の日付に対応する月を取得してmonthsとして集合で取得
        ・monthsを返す
        ★入力した日数分、昨日から遡り対応するすべての月を集合として返す


    ・download_month_data
        ・execution_id：uuidを生成して配置
        ・started_at：開始時間
        ・url：対象月のダウンロードURL
            ・power_usage というファイル名を入れたURLと決まっている。
        ・month_dir：ダウンロード先のURL
        ・zip_path：ダウンロードしたzipのダウンロード先も含めてのパス

        ・対象日付が無い場合は昨日を使用(電力データは翌日確定の為)
        ・month_dir のフォルダ作成
        ・zipをダウンロード
            ・response.raise_for_status()を使って、ステータスコードがエラー関係ならエラーを発生させる
        ・zipを保存
        ・データ量を計測
            ・zip_path.stat().st_size は zip_pah がダウンロードファイルのパスで .st_size でサイズを計測
        ・ダウンロード時間も計測
        ・ログデータの json を log_data として作成
        ・self._write_log(log_data)
            ・ローカルに json を保存
            ・BQのテーブルにjsonインサート
        ・tureを返す
        ★uuid作成、zipダウンロードおよび解凍、ログデータ作成(uuid含む)、ログデータをローカルに保存、BQのテーブルにインサートしtrueを返す


    ・download_for_month
        ・月の入力形式チェック
            ・違ったらエラーメッセージ出力
        ・月が未来の月だった場合はエラーメッセージ出力
        ・resultsという成功と失敗を保存する配列を作成
        ・self.download_month_data(yyyymm)
            ・uuid作成、zipダウンロードおよび解凍、ログデータ作成(uuid含む)、ログデータをローカルに保存、BQのテーブルにインサート
        ・成功/失敗を results に配置
        ・resultsを返す
        ★uuid作成、zipダウンロードおよび解凍、ログデータ作成(uuid含む)、ログデータをローカルに保存、BQのテーブルにインサート、
        　成功/失敗が入ったresultsを返す
    

    ・download_for_date
        ・self.get_months_from_date(date_str)
            ・日付の入力形式と昨日までの入力となっているかチェックして月をmonthとして返す
        ・self.download_month_data(month):
            ・uuid作成、zipダウンロードおよび解凍、ログデータ作成(uuid含む)、ログデータをローカルに保存、BQのテーブルにインサート、
            　成功/失敗が入ったresultsを返す
        ★日付の入力形式チェック、uuid作成、zipダウンロードおよび解凍、ログデータ作成(uuid含む)、ログデータをローカルに保存、
        　BQのテーブルにインサート、成功/失敗が入ったresultsを返す
    

    ・download_for_days
        ・self.get_required_months(days)
            ・入力した日数分、昨日から遡り対応するすべての月を集合としてmonthsという集合で受け取る
        ・results という成功/失敗を格納する配列を作成
        ・受け取った months に対して for 文で self.download_month_data(month) を実行
            ・self.download_month_data(month)
                ・uuid作成、zipダウンロードおよび解凍、ログデータ作成(uuid含む)、ログデータをローカルに保存、
            　  　BQのテーブルにインサートしtrueを返す
            ・self.download_month_data が ture を返したら resuluts の成功に月を追加、true じゃなければ失敗に月を追加
        ・results を戻す
        ★入力した日数分、昨日から戻って対応する複数の日付に対応する月全てを取得しそのすべての月に対して
        　uuid作成、zipダウンロードおよび解凍、ログデータ作成(uuid含む)、ログデータをローカルに保存、BQのテーブルにインサートし
        　成功/失敗の月をresultsとして返す
        


    
