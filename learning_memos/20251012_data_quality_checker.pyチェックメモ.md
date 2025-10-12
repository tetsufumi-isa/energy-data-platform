・class DataQualityChecker:
    ・main()
        ・日数とプロジェクトIDのargparse作成
            ・日数はデフォルト7日
            ・プロジェクトIDはデフォルト'energy-env'
        ・checker = DataQualityChecker(args.project_id)を実行
            ・BQおよびログに必要な情報を取得
        ・results = checker.run_all_checks(args.days)を実行
            ・
    


    ・def __init__(self, project_id="energy-env"):
        ・BQのプロジェクトID、チェックテーブル名やログのディレクトリ設定対応
        ・BQクライアント初期化
        ・BQログテーブル名定義
    ★BQおよびログに必要な情報を取得


    ・def run_all_checks(self, days=7):
        ・execution_id作成
        ・power_results = self.check_power_data(days)実行
    


    ・def check_power_data(self, days=7):
        ・レコード数チェック
            ・期待されるレコード数は日数x24
            ・レコード数チェック用クエリを流して確認
            ・結果をチェックテーブルのスキーマにあわせた辞書として作成
                ・結果があわなかったらその旨で辞書作成、raiseはしない
        ・使用電力NULL値チェック
            ・レコード数チェック用クエリを流して確認
            ・結果をチェックテーブルのスキーマにあわせた辞書として作成
                ・結果があわなかったらその旨で辞書作成、raiseはしない
        ・供給電力NULL値チェック
            ・レコード数チェック用クエリを流して確認
            ・結果をチェックテーブルのスキーマにあわせた辞書として作成
                ・結果があわなかったらその旨で辞書作成、raiseはしない
