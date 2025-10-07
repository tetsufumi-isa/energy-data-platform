・class PowerBigQueryLoader:
    ・def main():
        ・argparseを作成
            ・'--date'、'--project-id'、'--raw-data-dir'
                ・'--date'は何日分遡るかという指示
                    ・遡った日に対応する月を処理する
                    ・2/5から3日遡ると2月だけ、10日遡ると1月と2月のデータが対象
        ・loader = PowerBigQueryLoader(args.project_id, args.raw_data_dir)を実行
            ・インサートに必要なBQ側の設定やディレクトリの取得を対応
        ・results = loader.load_power_data(args.date)を実行
            ・execution_idを作成、対象の月に対応するcsvを必要な部分だけ抜き出してBQへインサート。
    　      　zipがありインサートもしているので保存はしない。ログを作成しローカル保存とBQへインサート。
    　      　インサート失敗の時はそのログを作成してローカルに保存。
    ・結果をpirt表示s手終了
    


    ・def __init__(self, project_id="energy-env", raw_data_dir=None):
        ・BQのproject_id、dataset_id、table_idを定義
        ・環境変数を使って電力データやログの保管場所などを定義
        ・BQクライアントの設定
        ・ログテーブル名の定義
    ★インサートに必要なBQ側の設定やディレクトリの取得を対応


    ・def load_power_data(self, days=5):
        ・execution_idを作成
        ・該当の月を取得、複数の場合もある
        ・月のcsvのパスを全て集めてフラットなリストall_csv_filesを返す
            ・月跨ぎでもフラットなリストで返す
        ・all_csv_filesをfor文で回す
            ・rows = self.parse_csv_to_rows(csv_file)を実行
                ・1つのcsvパスを受け取ってBQスキーマに必要なデータを作成し
    　          　欠損などないか確認して問題なければデータが入ったrowsを返す
                    ・rowsはリストに日別の辞書がネストして入っている
            ・rowsが空でなければ、rowsをフラットにしてall_rowsというリストに入れる
                ・日時別のカラムがキーの辞書がフラットに入るのでインサートしやすい
            ・対応が終わったcsv_files(csvのパス)はprocessed_filesというリストで保持
        ・delete_duplicate_data(all_rows)を実行
            ・インサート予定の日付を予めテーブルから削除して重複を避ける
        ・all_rowsをインサート
        ・processed_filesを使って対応したcsvを削除
            ・zipはあるしBQにインサート済なので保存不要と判断
        ・成功/失敗に応じてログ作成して_write_log(log_data)実行
            ・失敗はtryで拾っている
            ・_write_log(log_data)
                ・ログをローカルとBQテーブルに保存、インサート失敗したら
                　そのログもローカルに保存
    ★execution_idを作成、対象の月に対応するcsvを必要な部分だけ抜き出してBQへインサート。
    　zipがありインサートもしているので保存はしない。ログを作成しローカル保存とBQへインサート。
    　インサート失敗の時はそのログを作成してローカルに保存。
    

    ・def parse_csv_to_rows(self, csv_file_path):
        ・lines = content.split('\n')
            ・読み込んだcsvを行ごとのリストにする
        ・行毎にforで回して電力が記載されている箇所を探す
            ・ヒットしたら24時間分取得
            ・抜けなどないかチェック
            ・問題なければrowという辞書に追加
            ・rowを集めたrowsというリストを作成
        ・rowsに24時間データがあるか、最後が23となっているかを確認
        ・rowsを返す
    ★1つのcsvパスを受け取ってBQスキーマに必要なデータを作成し
    　欠損などないか確認して問題なければデータが入ったrowsを返す


    ・def delete_duplicate_data(self, rows):
        ・受け取った実データが入った辞書のリストから日付を取得
        ・maxとminの日付を取得
        ・BQのテーブルにmaxとminの間を削除するクエリを流す
            ・これからインサートするデータの重複を削除する
    ★インサート予定の日付を予めテーブルから削除して重複を避ける


    ・def _write_log(self, log_data):
        ・ログをローカルに保存
        ・BQにもインサート
        ・インサート失敗したらログのインサート失敗のログをローカルに保存
    ★ログをローカルとBQテーブルに保存、インサート失敗したらそのログも
    　ローカルに保存