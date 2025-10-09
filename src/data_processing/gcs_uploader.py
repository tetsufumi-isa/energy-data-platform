"""
GCSアップローダー

Phase 11: CLI対応追加
- ファイル単体アップロード
- ディレクトリアップロード
- コマンドライン実行対応

実行方法:
    # ファイル単体アップロード
    python -m src.data_processing.gcs_uploader --file data/raw/202507/20250701_power_usage.csv --destination raw_data/202507/20250701_power_usage.csv

    # ディレクトリアップロード
    python -m src.data_processing.gcs_uploader --upload-dir data/raw/202507 --prefix raw_data/202507

    # バケット名指定（デフォルト: energy-env-data）
    python -m src.data_processing.gcs_uploader --bucket my-bucket --file test.csv --destination test.csv
"""

import os
import argparse
from pathlib import Path
from google.cloud import storage
from logging import getLogger

# モジュール専用のロガーを取得
logger = getLogger('energy_env.data.gcs_uploader')

class GCSUploader:
    """Google Cloud Storageへのファイルアップロードを管理するクラス"""

    def __init__(self, bucket_name='energy-env-data', project_id='energy-env'):
        """
        初期化

        Args:
            bucket_name (str): GCSバケット名（デフォルト: energy-env-data）
            project_id (str): GCPプロジェクトID（デフォルト: energy-env）
        """
        self.bucket_name = bucket_name
        self.project_id = project_id
        self.client = storage.Client(project=project_id)
        self.bucket = self.client.bucket(bucket_name)
        logger.info(f"GCSUploader初期化完了 バケット: {bucket_name}")
    
    def upload_file(self, local_file_path, destination_blob_name):
        """
        ローカルファイルをGCSにアップロードする

        Args:
            local_file_path (str): アップロードするローカルファイルのパス
            destination_blob_name (str): GCS上での保存先パス（必須、バケットルート配置を防ぐため）

        Returns:
            str: アップロードされたファイルのGCS上のURI

        Raises:
            FileNotFoundError: ローカルファイルが存在しない場合
            ValueError: destination_blob_nameが未指定の場合
        """
        if not os.path.exists(local_file_path):
            raise FileNotFoundError(f"ローカルファイルが見つかりません: {local_file_path}")

        if not destination_blob_name:
            raise ValueError("destination_blob_nameは必須です（バケットルート配置を防ぐため）")

        # Blobオブジェクトを作成
        blob = self.bucket.blob(destination_blob_name)

        # ファイルをアップロード
        blob.upload_from_filename(local_file_path)

        logger.info(f"ファイルアップロード完了: {local_file_path} -> {destination_blob_name}")

        # GCS URIを返す
        return f"gs://{self.bucket_name}/{destination_blob_name}"
    
    def upload_directory(self, local_dir_path, destination_prefix, file_extension=None):
        """
        ローカルディレクトリ内のファイルをGCSにアップロードする（1階層のみ、サブディレクトリは無視）
        CSVファイルは1時間データに加工してからアップロード

        Args:
            local_dir_path (str): アップロードするローカルディレクトリのパス
            destination_prefix (str): GCS上でのプレフィックス（必須、バケットルート配置を防ぐため）
            file_extension (str, optional): 特定の拡張子を持つファイルのみをアップロード

        Returns:
            list: アップロードされたファイルのGCS上のURIのリスト

        Raises:
            NotADirectoryError: 指定されたパスがディレクトリでない場合
            ValueError: destination_prefixが未指定の場合
        """
        dir_path = Path(local_dir_path)

        if not dir_path.is_dir():
            raise NotADirectoryError(f"ディレクトリではありません: {local_dir_path}")

        if not destination_prefix:
            raise ValueError("destination_prefixは必須です")

        uploaded_uris = []

        # ディレクトリ内のファイルをリストアップ（1階層のみ）
        for file_path in dir_path.iterdir():
            # ファイルのみ処理（サブディレクトリは無視）
            if not file_path.is_file():
                continue

            # 拡張子フィルタリング
            if file_extension and not file_path.name.endswith(file_extension):
                continue

            # GCS上の保存先パスを作成
            gcs_path = f"{destination_prefix}/{file_path.name}"

            # CSVファイルの場合は加工処理を行う
            if file_path.name.endswith('.csv'):
                try:
                    # CSVファイルを1時間データに加工（メモリ内で処理）
                    processed_content = self._process_raw_csv_to_hourly_memory(str(file_path))

                    # GCS上でも _hourly ファイル名に統一
                    gcs_filename = file_path.name.replace('_power_usage.csv', '_hourly.csv')
                    processed_gcs_path = f"{destination_prefix}/{gcs_filename}"

                    # メモリから直接GCSにアップロード
                    blob = self.bucket.blob(processed_gcs_path)
                    blob.upload_from_string(processed_content, content_type='text/csv')
                    uri = f"gs://{self.bucket_name}/{processed_gcs_path}"
                    uploaded_uris.append(uri)

                    # 原形CSVファイルを削除
                    file_path.unlink()
                    logger.info(f"CSV加工・アップロード完了: {file_path.name} -> {gcs_filename}")

                except Exception as e:
                    logger.error(f"CSVファイル加工失敗: {file_path.name}: {e}")
                    # 加工に失敗した場合は原形ファイルをそのままアップロード
                    uri = self.upload_file(str(file_path), gcs_path)
                    uploaded_uris.append(uri)

            else:
                # CSV以外（ZIPファイル等）はそのままアップロード
                uri = self.upload_file(str(file_path), gcs_path)
                uploaded_uris.append(uri)

        logger.info(f"ディレクトリアップロード完了: {len(uploaded_uris)}件のファイルを {local_dir_path} からGCSへアップロード")
        return uploaded_uris
    
    def _process_raw_csv_to_hourly_memory(self, input_csv_path):
        """
        東電の原形CSVから1時間データのみを抽出してBigQuery用フォーマットに変換（メモリ内処理）

        Args:
            input_csv_path (str): 入力CSVファイルパス

        Returns:
            str: 加工済みCSVデータ（文字列）

        Raises:
            ValueError: CSVの構造が期待と異なる場合
        """
        try:
            logger.info(f"CSVを1時間データに加工中: {input_csv_path}")

            # Shift-JISエンコーディングでCSV読み込み
            with open(input_csv_path, 'r', encoding='shift-jis') as f:
                content = f.read()

            # メインデータ部分を特定
            lines = content.split('\n')

            # 出力用データを準備
            output_lines = []
            output_lines.append('date,hour,actual_power,supply_capacity')  # ヘッダー

            # ヘッダー行（DATE,TIME...）を見つける
            header_line_index = -1
            for i, line in enumerate(lines):
                if 'DATE,TIME,当日実績(万kW)' in line:
                    header_line_index = i
                    break

            if header_line_index == -1:
                raise ValueError("CSVヘッダー行が見つかりません")

            # ヘッダーの次行から24行処理
            processed_count = 0
            for i in range(header_line_index + 1, min(header_line_index + 25, len(lines))):
                line = lines[i].strip()
                if not line:
                    continue

                parts = line.split(',')
                if len(parts) >= 6:
                    try:
                        # 日付の抽出（"2025/4/1" → "2025-04-01"）
                        date_str = parts[0].strip()
                        # 日付フォーマットを統一
                        date_parts = date_str.split('/')
                        if len(date_parts) == 3:
                            year = date_parts[0]
                            month = date_parts[1].zfill(2)  # 1桁月を2桁に
                            day = date_parts[2].zfill(2)    # 1桁日を2桁に
                            formatted_date = f"{year}-{month}-{day}"
                        else:
                            formatted_date = date_str

                        # 時刻の抽出（"13:00" → 13）
                        time_str = parts[1].strip()
                        hour = int(time_str.split(':')[0])
                        hour_str = str(hour).zfill(2)  # 追加：2桁ゼロ埋め

                        # データの抽出
                        actual_power = float(parts[2])
                        supply_capacity = float(parts[5])

                        # BigQuery用行データ作成
                        output_line = f"{formatted_date},{hour_str},{actual_power},{supply_capacity}"
                        output_lines.append(output_line)
                        processed_count += 1

                    except (ValueError, IndexError) as e:
                        logger.warning(f"無効な行をスキップ {i}: {line} - {e}")
                        continue

            # 文字列として返す（ファイルには書き込まない）
            csv_content = '\n'.join(output_lines)
            logger.info(f"1時間データ加工完了: {processed_count}件のレコードを処理")
            return csv_content

        except Exception as e:
            logger.error(f"CSV加工エラー: {e}")
            raise


def main():
    """メイン関数 - CLI実行用"""
    parser = argparse.ArgumentParser(description='GCSアップローダー（Phase 11対応版）')
    parser.add_argument('--file', type=str,
                       help='アップロードするファイルパス')
    parser.add_argument('--destination', type=str,
                       help='GCS上の保存先パス（--fileと併用）')
    parser.add_argument('--upload-dir', type=str,
                       help='アップロードするディレクトリパス')
    parser.add_argument('--prefix', type=str,
                       help='GCS上のプレフィックス（--upload-dirと併用、必須）')
    parser.add_argument('--bucket', type=str, default='energy-env-data',
                       help='GCSバケット名（デフォルト: energy-env-data）')
    parser.add_argument('--file-extension', type=str,
                       help='特定の拡張子のファイルのみアップロード（例: .csv）')

    args = parser.parse_args()

    # 引数の排他チェック
    if args.file and args.upload_dir:
        print("エラー: --file と --upload-dir は同時に指定できません")
        return

    if not args.file and not args.upload_dir:
        print("エラー: --file または --upload-dir のいずれかを指定してください")
        return

    if args.file and not args.destination:
        print("エラー: --file を指定する場合は --destination も必要です")
        return

    if args.upload_dir and not args.prefix:
        print("エラー: --upload-dir を指定する場合は --prefix も必要です（バケットルート配置を防ぐため）")
        return

    print(f"GCSアップローダー開始")
    print(f"バケット: {args.bucket}")

    try:
        # GCSUploader初期化
        uploader = GCSUploader(args.bucket)

        if args.file:
            # ファイル単体アップロード
            print(f"ファイルアップロード: {args.file} -> {args.destination}")
            uri = uploader.upload_file(args.file, args.destination)
            print(f"アップロード完了: {uri}")

        elif args.upload_dir:
            # ディレクトリアップロード
            print(f"ディレクトリアップロード: {args.upload_dir}")
            print(f"プレフィックス: {args.prefix if args.prefix else '(なし)'}")
            if args.file_extension:
                print(f"拡張子フィルタ: {args.file_extension}")

            uris = uploader.upload_directory(
                args.upload_dir,
                destination_prefix=args.prefix,
                file_extension=args.file_extension
            )
            print(f"アップロード完了: {len(uris)}件")
            for uri in uris:
                print(f"  - {uri}")

    except Exception as e:
        print(f"エラー: {e}")
        return

    print("GCSアップロード完了")


if __name__ == "__main__":
    main()