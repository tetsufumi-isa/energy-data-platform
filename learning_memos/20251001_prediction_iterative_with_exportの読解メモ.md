◆ログの設定
    ・logger = getLogger(__name__)
        ・このモジュールで使うロガーを最初に作成

    ・JsonFormatter
        ・JsonFormatter(Formatter)
            ・JsonFormatterというクラスを作りながらloggingのFormatterを継承している
            ・format(self, record: LogRecord) -> str:
                ・-> str:最終的に文字列になるというコメントのようなもの
                ・logging が format を自動呼出しすることがあるのでその対応のためにオーバーライドしている
                ・log_dataという辞書を作成
                    ・self.formatTime(record, self.datefmt)
                        ・LogRecordオブジェクトが持っているタイムスタンプを成型するメソッド
                            ・LogRecordオブジェクトとは
                                ・ログを構造的に扱うオブジェクト
                                ・いわゆるログテキスト、作業の内容やその他が不定形で書かれている部分を
                                　メッセージとして保持しつつ、発生時間やメッセージレベル("DEBUG", "INFO")は
                                　別にもっている
                            ・LogRecordオブジェクトはrecordという変数でLogRecordで受け取っている
                            ・指定のないこの場合は"%Y-%m-%d %H:%M:%S,sss"
                    ・LogRecordオブジェクトが持っている下記も取得
                        ・レベル文字("DEBUG", "INFO")、メッセージ、名前、ログを出したモジュール
                        　ログを出した関数、ログを出した行番号
                            ・getMessage()：LogRecordオブジェクトが持っているメソッド
                ・hasattr(record, 'bq_schema'):
                    ・hasattr()：オブジェクトに特定の属性があるか調べるメソッド
                    ・BQのログテーブルにインサートするログ作成時であればlog_data['bq_schema']として追加している
            ・log_dataをjsonにして返す
    ★LogRecordオブジェクトの情報をjsonにして返す。情報の受け渡しはformat()で自動化されていて、内容一部変えるために
    　継承してつかわれている。


    ・setup_prediction_logging
        ・ログディレクトリ作成
        ・ファイル名をタイムスタンプ付きで作成
        ・log_fileという名前でログのパス作成
        ・'energy_env.predictions'というロガーを取得、なければ作成
            ・ロガー：ログ出力の管理オブジェクト
            ・INFOレベル以上の取得と設定
        ・重複防止のためにハンドラークリア
            ・ロガーが持っているログの出力先の管理オブジェクト
        ・JSON形式のファイルハンドラー設定
            ・json_formatterを使っている
        ・メッセージだけコンソールにも出力設定
        ・ロガーとログのパスを返す
    ★ログのディレクトリやパスを設定しロガーを作りjsonでの出力も設定しロガーとパスを返す


    ・log_file_path = setup_prediction_logging()
        ・ログの設定を実行
    ★JsonFormatterとsetup_prediction_loggingで定義した内容をロガーに設定する
    

    ・log_and_save_to_bq
        ・受け取ったprocess_status(BQスキーマにあわせた辞書形式)から'process_type'と'status'を取得しメッセージを作成しlog_massageとしている
        ・受け取ったログレベルがinfoである、またはログレベルを受け取っていなかったら、info()を実行
            ・logger.info(log_message, extra={'process_status': process_status})
                ・log_messageをメッセージ、つまりログテキストとして、process_statusを追加したLogRecordを作成し
                　更に最初に作ってsetup_prediction_logging()で設定したロガーに渡してレベルはinfoとして出力まで行う
                    ・info()はわかりづらいがLogRecordの作成から出力までを行っている
        ・受け取ったログレベルがエラーなら、log_massageをメッセージとしてスキーマを追加したLogRecordを作成し出力まで行う
            ・info()との違いはレベルがinfoかerrorかの違い
        ・インサートするBQのテーブル名を取得
        ・スキーマの辞書を別のテーブルへコピー
        ・'started_at'と'completed_at'はBQがpythonのdatetimeは受け付けないので文字列にしてインサートしBQ側で変換
        ・'date'も同じ理由で文字列にしてインサート
        ・jsonをインサートし、エラーがあれば表示しfalseを返す、成功すればtrueを返す
    ★BQクライアント、予測のステータスをBQにの内容に合わせた辞書、ログレベルを引数としてinfoとしてログを作成しBQへインサート


◆予測開始
    ・実行ID作成、開始時間計測、ログ表示
    ・ベースのパスを環境変数から作成
    ・BQクライアント初期化
    ・昨日までの学習データ抽出のクエリ実行、ml_features_trainというdfとして保持
        ・日付と時間が分れたデータの為、結合してdatetimeを作成
    ・予測期間と過去のデータを見るために必要なカレンダーデータ取得しデータフレームとして保持
        ・基本的には学習データの日付データを使う
        ・予測する未来日と〇〇営業日、前営業日というデータのみカレンダーテーブル空取得
    ・気象データとカレンダーデータを必要な期間で抽出してjoinしfuture_featuresというdfとして保持
        ・datetimeも作成
        ・循環特徴量も追加
    ・予測で使用する特徴量を定義しfeaturesとする
    ・XGBoostで学習
        ・設定は以前に精度が高かった内容で実行
    ・lag_1_business_dayようにdf作成
        ・business_days_train：過去20日の営業日だけのdatetimeと実績値
        ・business_days_future：16日先までの営業日だけのdatetimeのみ
    
    ・prepare_features_no_fallback(target_datetime, predictions)
        ・target_datetimeで受け取った対象のレコードだけをrowとする
        ・予測用の配列であるfeature_valuesを作成
        ・定義した12特徴量のfeaturesを使って予測用の1feature_valuesにデータを追加していく
            ・最初の予測
                ・lag_1_dayには前日の実績値を追加
                    ・予測用の配列であるfeature_valuesの最初の値
                ・lag_7_dayには7日前の実績値を追加
                    ・予測用の配列であるfeature_valuesの2つ目の値
                ・lag_1_business_day
                    ・20のrangeを作って1からfor文
                        ・1日ずつ遡ってlag_dateとlag_datetimeを都度作成
                        ・business_days_trainの中にlag_datetimeがあればその実績値を追加
                            ・予測用の配列であるfeature_valuesの3つ目の値
    

    ・予測結果を格納する変数を作成
        ・predictions：空の辞書
        ・daily_results：空の配列



