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
        ・受け取ったprocess_status(BQスキーマにあわせた辞書形式)から'process_type'と'status'を取得し
        　メッセージを作成しlog_massageとしている
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


◆予測
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
    
    ・prepare_features(target_datetime, predictions)
        ・target_datetimeで受け取った対象のレコードだけをrowとする
            ・future_features(気象データ、カレンダー、循環特徴量)から受け取る
        ・予測用の配列であるfeature_valuesを作成
        ・定義した12特徴量のfeaturesをfor文で回して予測用のfeature_valuesにデータを追加していく
            ・16*24の予測のうちの1回目
                ・引数のpredictionsは空の辞書
                ・lag_1_dayには前日の実績値を追加
                ・lag_7_dayには7日前の実績値を追加
                ・lag_1_business_day
                    ・20のrangeを作って1からfor文
                        ・1日ずつ遡ってlag_dateとlag_datetimeを都度作成
                        ・business_days_trainの中にlag_datetimeがあればその実績値を追加
            ・2回目以降の場合
                ・引数のpredictionsに予測した日時をキーに予測値が入った辞書が入っている
                ・lag_1_dayはpredictionsを使って予測値が入る
                ・lag_7_dayは対象が過去なら実績値、未来ならpredictionsを使って予測値が入る
                ・lag_1_business_day
                    ・対象が未来なら未来ならpredictionsを使って予測値が入る
                    ・過去なら1回目と同様の動作
            ・その他の特徴量はrowから受け取ってfeature_valuesに追加
                ・rowの中身はfuture_features(気象データ、カレンダー、循環特徴量)
            ・過去と未来どちらにもヒットが無ければnan
        ・feature_valuesを返す
            ・12特徴量のfeaturesをfor文で回して作っているのでfeaturesのカラム順で作成されている
    ★target_datetimeで受け取った日時に対する実績値または予測値を配置しfeature_valuesとして返す
    　初回は実績値だけだが2回目以降は初回で予測した日時と予測がpredictionsに入ってくるのでそれも使う
    　feature_valuesは定義した12特徴量のfeaturesをfor文で回して作っているので
    　featuresのカラム順で作成されている
    
    ・予測結果を格納する変数を作成
        ・predictions：空の辞書
        ・daily_results：空の配列
    
    ・current_dateを宣言
        ・current_dateは最初はstart_dateが配置され今日の00:00:00のdate_timeになる
    ・16のrangeを作成してfor(16日分の予測)
        ・current_date += timedelta(days=1)で当日+15日でまわす
            ・24のrangeを作成してfor
                ・target_datetime = current_date + timedelta(hours=hour)
                    ・0時始まりで分と秒はゼロのまま0～23まで繰り返す
                ・prepare_features(target_datetime, predictions)
                    ・最初の実行はpredictionsは空で投げるがprepare_featuresで使わないので問題なし
                        ・全て実績の特徴量データをfeature_valuesとして受け取る
                    ・2回目以降は予測値をpredictionsに入れて投げる
                ・モデルに食わせるdfとしてX_predを作成
                    ・feature_valuesにカラムとしてfeaturesを使っているがfeature_valuesは
                    　元々featuresをfor文で回して作成したので問題なし
                ・X_predで予測実行し結果をpred_valueで受け取る
                ・predictionsをtarget_datetimeをキーで、pred_valueを値として辞書更新
                    ・予測対象となる日付時間に対する予測値の辞書ができあがる
    ・16日分の予測が終わったら終了時間をprediction_end_timeとして保持
    ・prediction_start_timeとprediction_end_timeを使って予測にかかった時間(秒)を
    　duration_secondsとして保持


◆プロセス実行ステータス記録

