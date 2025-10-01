◆ログの設定
    ・JsonFormatter
        ・JsonFormatter(Formatter)
            ・JsonFormatterというクラスを作りながらloggingのFormatterを継承している
            ・format(self, record: LogRecord) -> str:
                ・-> str:最終的に文字列になるというコメントのようなもの
                ・logging が format を自動呼出しすることがあるのでその対応のためにオーバーライドしている
                ・log_dataという辞書を作成
                    ・self.formatTime(record, self.datefmt)
                        ・LogRecordオブジェクトが持っているタイムスタンプを成型するメソッド
                            ・LogRecordオブジェクトはrecord: LogRecordで受け取っている
                            ・指定のないこの場合は"%Y-%m-%d %H:%M:%S,sss"
                    ・LogRecordオブジェクトが持っている下記も取得
                        ・レベル文字("DEBUG", "INFO")、メッセージ、名前、ログを出したモジュール
                        　ログを出した関数、ログを出した行番号
                            ・getMessage()：LogRecordオブジェクトが持っているメソッド
                ・hasattr(record, 'execution_id')
                    ・hasattr()：オブジェクトに特定の属性があるか調べるメソッド
                    ・LogRecordオブジェクト(record)にexecution_idという属性があるかを調べて
                    　あればlog_data['execution_id']に追加している
                ・hasattr(record, 'additional_data')
                    ・LogRecordオブジェクト(record)にadditional_dataという属性があるかを調べて
                    　あればlog_data['additional_data']に追加している
            ・log_dataをjsonにして返す
    ★LogRecordオブジェクトの情報log_dataをjsonにして返す。情報の受け渡しはformat()で自動化されていて、内容一部変えるために
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


    ・logger, log_file_path = setup_prediction_logging()
        ・ログの設定を実行
    

    ・log_and_save_to_bq