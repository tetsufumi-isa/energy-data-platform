・main()
    ・updater = SystemStatusUpdater()実行
        ・処理に必要な諸々の設定を対応
    ・results = updater.update_system_status()を実行
        ・既存レコードの削除～最新データインサート～ログ作成までを処理。
    　  　失敗したらエラーメッセージでどこのエラーか判別可能。
    ・print_update_results(results)を実行
        ・処理結果をpurintする
    ・失敗時はexit code 1を返す


・class SystemStatusUpdater:
    ・__init__(self, project_id="energy-env"):
        ・BQで必要な処理を設定
            ・project_id、dataset_id
            ・BQクライアント
            ・system_status、ログ各々のテーブル名取得
        ・環境変数を使って必要なディレクトリ設定
    ★処理に必要な諸々の設定を対応


    ・def update_system_status(self):
        ・execution_id作成
        ・try:
            ・deleted_rows = self.delete_all_records()
                ・全レコード削除。失敗したらエラーメッセージを返す。
            ・inserted_rows = self.insert_latest_status()
                ・最新のステータスをインサート。失敗したらエラーメッセージを返す。
            ・結果のデータをlog_dataという辞書として作成
            ・ _write_log(log_data)実行
                ・受け取ったlog_dataををローカルとBQへ保存
    　          　インサート失敗したらそのログをローカルに保存。
            ・削除～インサート～ログ保存までが完了した旨の情報を辞書で返す
        ・Exception:
            ・失敗のログをlog_dataとして作成
            ・ _write_log(log_data)実行
                ・受け取ったlog_dataををローカルとBQへ保存
    　          　インサート失敗したらそのログをローカルに保存。
            ・更新が失敗したことを辞書の形で返す
                ・エラー時のメッセージが入っているのでメッセージで
                　何のエラーか判別可能
    ★既存レコードの削除～最新データインサート～ログ作成までを処理。
    　失敗したらエラーメッセージでどこのエラーか判別可能。


    ・def delete_all_records(self):
    ★全レコード削除。失敗したらエラーメッセージを返す。


    ・def insert_latest_status(self):
        ・下記の内容でクエリ作成し実行
            ・process_execution_logの過去2日でprocess_typeの
            　started_at DESCでrow_no
                ・日付で取ると最新のprocess_typeのみとなる為
            ・data_quality_checksの過去2日で
            　check_timestamp DESCでrow_no
            ・各項目の最新を確認し'OK'または'ERROR'
                ・'WARNING'はデータ欠損や想定外エラー
            ・失敗したらエラーメッセージを返す
    ★ステータスをインサート。失敗したらエラーメッセージを返す。


    ・def _write_log(self, log_data):
        ・受け取ったlog_dataをローカルにjsonとして作成
        ・BQへインサート
            ・インサート失敗時にはそのログをローカルに保存
    ★受け取ったlog_dataををローカルとBQへ保存
    　インサート失敗したらそのログをローカルに保存


・def print_update_results(results):
★処理結果をpurintする