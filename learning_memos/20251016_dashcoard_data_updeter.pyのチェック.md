・main()
    ・updater = DashboardDataUpdater()を実行
        ・処理に必要な諸々の設定を対応
    ・results = updater.update_dashboard_data()を実行
        ・execution_id作成し、ダッシュボードデータの今日以降のデータを削除してから
    　    新たに最新のデータを入れなおしてログを作成しローカルとBQへ保存。
    　    どこかで失敗したらエラーメッセージ付きのログを作成しローカルとBQへ保存。
    　  　結果の概要の辞書を返す。
    ・print_update_results(results)を実行
        ・処理結果をpurintする
    ・失敗時はexit code 1を返す


・class DashboardDataUpdater:
    ・__init__(self, project_id="energy-env"):
        ・BQで必要な処理を設定
            ・project_id、dataset_id
            ・BQクライアント
            ・ダッシュボード、ログ各々のテーブル名取得
        ・環境変数を使って必要なディレクトリ設定
    ★処理に必要な諸々の設定を対応


    ・update_dashboard_data(self):
        ・execution_id作成
        ・deleted_rows = self.delete_future_data()実行
            ・実行日以降のダッシュボードテーブルのデータ削除
            ・クエリ失敗したらエラーメッセージ返す
        ・inserted_rows = self.insert_dashboard_data_direct()実行
            ・実行日以降のデータをダッシュボードテーブルへインサート
    　      　失敗時にはエラーメッセージを返す
        ・上記がここまで成功していた場合
            ・成功ログの辞書をlog_dataとして作成
            ・self._write_log(log_data)実行
                ・受け取ったlog_dataををローカルとBQへ保存
    　          　インサート失敗したらそのログをローカルに保存。
            ・結果の概要をとなる辞書を返す
        ・上記が失敗していた場合
            ・エラーメッセージを載せたログの辞書をlog_dataとして作成
            ・self._write_log(log_data)実行
                ・受け取ったlog_dataををローカルとBQへ保存
    　          　インサート失敗したらそのログをローカルに保存。
            ・結果の概要となる辞書を返す
    ★execution_id作成し、ダッシュボードデータの今日以降のデータを削除してから
    　新たに最新のデータを入れなおしてログを作成しローカルとBQへ保存。
    　どこかで失敗したらエラーメッセージ付きのログを作成しローカルとBQへ保存。
    　結果の概要の辞書を返す。


    ・delete_future_data(self):
        ・実行日以降のダッシュボードテーブルのデータを削除するクエリ実行
            ・result()実行しているが返していないのは
            　クエリ完了まで待つための実行だから
        ・削除されたレコード数を返す
        ・クエリ失敗したらエラーメッセージ返す
    ★実行日以降のダッシュボードテーブルのデータ削除。
    　クエリ失敗したらエラーメッセージ返す。


    ・insert_dashboard_data_direct(self):
        ・ダッシュボードテーブルへのデータ作成とインサートクエリ実行
            ・データの内容
                ・電気、天気、予測結果を実行日以降でインサート
                ・データ作成日が最新のものだけインサート
                    ・重複は発生しない想定だが念のために対応
        ・エラー時はエラーメッセージを返す
    ★実行日以降のデータをダッシュボードテーブルへインサート
    　失敗時にはエラーメッセージを返す


    ・def _write_log(self, log_data):
        ・受け取ったlog_dataをローカルにjsonとして作成
        ・BQへインサート
            ・インサート失敗時にはそのログをローカルに保存
    ★受け取ったlog_dataををローカルとBQへ保存
    　インサート失敗したらそのログをローカルに保存。

    ・def print_update_results(results):
    ★処理結果をpurintする