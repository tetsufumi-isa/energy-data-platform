・class GCSUploader:
    ・main()
        ・argparse作成
            ・'--file'：UPするファイルパス
            ・'--destination'GCS上の保存先パス(ファイル名まで必須)
            ・'--upload-dir'UPするディレクトリ
            ・'--prefix'：GCS上のプレフィックス(ファイル名不可)
            ・'--bucket'：GCSバケット名
            ・'--file-extension'：特定の拡張子のみアップロード
        ・引数の排他チェック
            ・'--file'の時は'--destination'必須
            ・'--upload-dir'の時は'--prefix'必須
        ・uploader = GCSUploader(args.bucket)
            ・upに必要な情報を定義し、GCSUploader初期化
        ・argparseの引数によって分岐
            ・'--file'
                ・uri = uploader.upload_file(args.file, args.destination)実行
                    ・ファイルをGCSにUPしてURIを文字列で返す
            ・'--upload-dir'
    


    ・def __init__(self, bucket_name='energy-env-data', project_id='energy-env'):
    ★upに必要な情報を定義し、GCSUploader初期化



    ・def upload_file(self, local_file_path, destination_blob_name):
        ・local_file_path(ローカルファイルのパス)が存在しなければエラー
        ・destination_blob_name(保存先ファイルパス)が存在しなければエラー
        ・destination_blob_nameを使ってblobを作成
            ・blob：gcs上のファイルを扱うオブジェクト
        ・upload_from_filename(local_file_path)実行
            ・googleが用意してるアップロードのメソッド
                ・blobオブジェクトがup先の情報持ってるから
                　引数はlocal_file_pathだけでいい
        ・upしたGCS URIを返す文字列で返す
    ★ファイルをGCSにUPしてURIを文字列で返す
    


    ・def upload_directory(self, local_dir_path, destination_prefix, file_extension=None):
        ・local_dir_path(UPするディレクトリ)でdir_pathというpathオブジェクトを作成
        ・destination_prefixがnullでないことをチェック
        ・dir_path内の情報をforで回していく
            ・ディレクトリ(サブフォルダ)はスルー
            ・file_extension(拡張子)を受けっとていればそれでフィルタリング
            ・GCS上の保存先パスをgcs_pathとして作成
            ・CSVファイルの場合は加工処理を行う
                ・processed_file_path = self._process_raw_csv_to_hourly(str(file_path))を実行



    ・_process_raw_csv_to_hourly(self, input_csv_path):
        ・ファイル名をbase_name、ディレクトリ部分のみをdir_nameとして保持
