・main()
    ・updater = PredictionAccuracyUpdater()実行
        ・処理に必要な諸々の設定を対応
    ・results = updater.update_prediction_accuracy()実行
        ・削除～インサート～ログ保存までが完了した旨の情報を辞書で返す
        　失敗時はその旨を辞書で返す。メッセージで何のエラーか判別可能
    ・print_update_results(results)を実行
        ・処理結果をpurintする
    ・失敗時はexit code 1を返す



・class PredictionAccuracyUpdater:
    ・__init__(self, project_id="energy-env"):
        ・BQで必要な処理を設定
            ・project_id、dataset_id
            ・BQクライアント
            ・予測結果、ログ各々のテーブル名取得
        ・環境変数を使って必要なディレクトリ設定
    ★処理に必要な諸々の設定を対応


    ・def update_prediction_accuracy(self):
        ・try:
            ・execution_id作成
            ・deleted_rows = self.delete_recent_data()実行
                ・実行日7日前～昨日までの予測精度分析テーブルのデータ削除。
        　      　クエリ失敗したらエラーメッセージ返す。
            ・inserted_rows = self.insert_prediction_accuracy()実行
                ・実行日7日前～昨日までのデータを予測精度分析テーブルへインサート
        　      　クエリ失敗したらエラーメッセージ返す
            ・成功のログをlog_dataとして作成
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
        ★削除～インサート～ログ保存までが完了した旨の情報を辞書で返す
        　失敗時はその旨を辞書で返す。メッセージで何のエラーか判別可能


    ・def delete_recent_data(self):実行
        ・try:
            ・実行日7日前～昨日までの予測精度分析テーブルのデータを削除するクエリ実行
            ・削除されたレコード数を返す
        ・Exception:
            ・エラーメッセージ返す
    ★実行日7日前～昨日までの予測精度分析テーブルのデータ削除。
    　クエリ失敗したらエラーメッセージ返す。


    ・def insert_prediction_accuracy(self):実行
        ・try:
            ・実行日7日前～昨日までのデータを予測精度分析テーブルへインサート
                ・prediction_resultsとenergy_data_hourlyからデータを取得して
                　差分の絶対値とその割合を計算
         ・Exception:
            ・エラーメッセージ返す
     ★実行日7日前～昨日までのデータを予測精度分析テーブルへインサート
    　 クエリ失敗したらエラーメッセージ返す


    ・def _write_log(self, log_data):
        ・受け取ったlog_dataをローカルにjsonとして作成
        ・BQへインサート
            ・インサート失敗時にはそのログをローカルに保存
    ★受け取ったlog_dataををローカルとBQへ保存
    　インサート失敗したらそのログをローカルに保存

・def print_update_results(results):
★処理結果をpurintする