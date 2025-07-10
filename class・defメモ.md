class MainETLPipeline:
    """メインETLパイプライン - Extract + Load統合処理"""
    
    def __init__(self, base_dir="data/raw", bucket_name="energy-env-data"):
        """
        初期化
        
        Args:
            base_dir (str): ローカルデータ保存先
            bucket_name (str): GCSバケット名
        """
        self.base_dir = Path(base_dir) → ローカルの保存先をpathオブジェクトで作成
        self.bucket_name = bucket_name → バケット名を作成
        
        # 各コンポーネントを初期化
        self.downloader = PowerDataDownloader(str(self.base_dir)) → 東電のURLでpathオブジェクトを作成
        self.uploader = GCSUploader(bucket_name) → gcsの情報が入ったオブジェクトを作成




class GCSUploader:
    """Google Cloud Storageへのファイルアップロードを管理するクラス"""
    
    def __init__(self, bucket_name, project_id=None):
        """
        初期化
        
        Args:
            bucket_name (str): GCSバケット名
            project_id (str, optional): GCPプロジェクトID
        """
        self.bucket_name = bucket_name →引数
        self.project_id = project_id →引数
        self.client = storage.Client(project=project_id) →googleのstorageライブラリを使ってオブジェクト作成
        self.bucket = self.client.bucket(bucket_name) →上記のオブジェクト使って引数のバケット名からバケット作成


class PowerDataDownloader:
    """東京電力でんき予報データダウンローダー"""
    
    BASE_URL = "https://www.tepco.co.jp/forecast/html/images"
    
    def __init__(self, base_dir="data/raw"):
        """
        初期化
        
        Args:
            base_dir (str): データ保存先のベースディレクトリ
        """
        self.base_dir = Path(base_dir) → 東電のURLでpathオブジェクトを作成



def run_etl_for_month(self, yyyymm): → class MainETLPipelineのメソッド
    """
    月指定でETLパイプラインを実行
    
    Args:
        yyyymm (str): 年月 (YYYYMM形式)
        
    Returns:
        dict: 実行結果サマリー
    """
    logger.info(f"Starting ETL pipeline for month {yyyymm}")
    
    # Phase 1: Extract
    logger.info("Phase 1: Extracting data from TEPCO website")
    download_results = self.downloader.download_for_month(yyyymm) →resultsという結果の辞書を返す
    
    if not download_results['success']:→成功がなければ、つまり失敗なら
        logger.warning(f"No data downloaded for month {yyyymm}. Skipping upload phase.")
        return {
            'download_results': download_results,
            'upload_results': {'success': [], 'failed': []},→失敗なら実行されず両方空なので表示されない
            'overall_status': 'failed',
            'message': f'月{yyyymm}のダウンロードに失敗したため、アップロードをスキップしました'
        }
    
    # Phase 2: Load
    logger.info("Phase 2: Loading data to Google Cloud Storage")
    upload_results = self._upload_downloaded_data(download_results['success'])→DL成功結果の辞書からyyymmだけを渡してupを処理し、upの成功可否の辞書を受け取る
    
    # 結果サマリー作成
    overall_status = 'success' if download_results['success'] and upload_results['success'] else 'partial'
    
    return {
        'download_results': download_results,
        'upload_results': upload_results,
        'overall_status': overall_status,
        'message': self._create_summary_message(download_results, upload_results)
    }→ダウンロードとアップロードの成功可否の結果を返す


def download_for_month(self, yyyymm): → class PowerDataDownloaderのメソッド
    """
    指定月のデータをダウンロード
    
    Args:
        yyyymm (str): 年月 (YYYYMM形式)
        
    Returns:
        dict: ダウンロード結果
    """
    # 月フォーマットの事前チェック
    try:
        month_date = datetime.strptime(yyyymm, '%Y%m') →入力した月の初日のdatetimeのobj
    except ValueError:
        raise ValueError(f"月はYYYYMM形式で入力してください: {yyyymm}")
    
    # 未来月チェック →入力付き初日と今月初日を比較することで未来の月となっていないか？
    current_month = datetime.today().replace(day=1) →今月のdatetimeのobj
    if month_date > current_month:
        current_month_str = current_month.strftime('%Y%m')
        raise ValueError(f"未来の月は指定できません: {yyyymm} (今月: {current_month_str})")

    results = {'success': [], 'failed': []}
    
    try:
        if self.download_month_data(yyyymm):
            results['success'].append(yyyymm)
        else:
            results['failed'].append(yyyymm)
    except Exception as e:
        logger.error(f"Failed to download {yyyymm}: {e}")
        results['failed'].append(yyyymm)
    
    return results

def download_month_data(self, yyyymm): → class PowerDataDownloaderのメソッド
    """
    指定月のデータをダウンロード・解凍
    
    Args:
        yyyymm (str): 年月 (YYYYMM形式)
        
    Returns:
        bool: ダウンロード成功時True
        
    Raises:
        requests.exceptions.RequestException: ダウンロードエラー
    """
    url = f"{self.BASE_URL}/{yyyymm}_power_usage.zip" →ダウンロードする東電のzipのURL
    month_dir = self.base_dir / yyyymm → ローカルのディレクトリ、月まで
    zip_path = month_dir / f"{yyyymm}.zip" →ローカルのディレクトリ、zipまで
    
    try:
        # ディレクトリ作成
        month_dir.mkdir(parents=True, exist_ok=True)
        
        # ZIPダウンロード
        logger.info(f"Downloading: {url}")
        response = requests.get(url, timeout=30) →equestsというライブラリを使ってダウンロード内容も含めたobj作成
        response.raise_for_status() → 上記objでエラーがあればexceptionを発生させるメソッド
        
        # ZIP保存
        with open(zip_path, 'wb') as f:
            f.write(response.content)
        
        # ZIP解凍
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(month_dir)
        
        logger.info(f"Successfully downloaded and extracted {yyyymm} data to {month_dir}")
        return True
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            logger.warning(f"Data for {yyyymm} not yet available (404)")
            return False
        else:
            logger.error(f"HTTP error downloading {yyyymm}: {e}")
            raise
    except Exception as e:
        logger.error(f"Error downloading {yyyymm}: {e}")
        raise


def run_etl_for_date(self, date_str):
    """
    日付指定でETLパイプラインを実行
    
    Args:
        date_str (str): 日付文字列 (YYYYMMDD形式)
        
    Returns:
        dict: 実行結果サマリー
    """
    logger.info(f"Starting ETL pipeline for date {date_str}")
    
    # Phase 1: Extract
    logger.info("Phase 1: Extracting data from TEPCO website")
    download_results = self.downloader.download_for_date(date_str) →ダウンロードしつつ成功可否の辞書が入ったリストを返す
    
    if not download_results['success']:
        logger.warning(f"No data downloaded for date {date_str}. Skipping upload phase.")
        return {
            'download_results': download_results,
            'upload_results': {'success': [], 'failed': []},→失敗なら実行されず両方空なので表示されない
            'overall_status': 'failed',
            'message': f'日付{date_str}のダウンロードに失敗したため、アップロードをスキップしました'
        }
    
    # Phase 2: Load
    logger.info("Phase 2: Loading data to Google Cloud Storage")
    upload_results = self._upload_downloaded_data(download_results['success'])→DL成功結果の辞書からyyymmだけを渡してupを処理し、upの成功可否の辞書を受け取る
    
    # 結果サマリー作成 →DLとUPどちらも成功であればsucessという文字列を返す
    overall_status = 'success' if download_results['success'] and upload_results['success'] else 'partial'
    
    return {→成功時はDLとUP両方の結果情報を辞書として戻す
        'download_results': download_results,
        'upload_results': upload_results,
        'overall_status': overall_status,
        'message': self._create_summary_message(download_results, upload_results)
    }



def download_for_date(self, date_str): → class PowerDataDownloaderのメソッド
    """
    特定日のデータ（その日が含まれる月）をダウンロード
    
    Args:
        date_str (str): 日付文字列 (YYYYMMDD形式)
        
    Returns:
        dict: ダウンロード結果
    """
    months = self.get_months_from_date(date_str)
    results = {'success': [], 'failed': []}
    
    for month in months:
        try:
            if self.download_month_data(month):  →ダウンロード実行し、成功ならtureを返す
                results['success'].append(month) →上記の辞書をリストとして追加
            else:
                results['failed'].append(month)
        except Exception as e:
            logger.error(f"Failed to download {month}: {e}")
            results['failed'].append(month)
    
    return results →成功可否の辞書が入ったリストを返す



def _upload_downloaded_data(self, successful_months):→class MainETLPipelineのメソッド
    """
    ダウンロードされたデータをGCSにアップロード
    
    Args:
        successful_months (list): →ダウンロード成功した月のリスト
        
    Returns:
        dict: アップロード結果
    """
    upload_results = {'success': [], 'failed': []}
    
    for month in successful_months:→successful_monthsはDLが成功したyyyymm
        month_dir = self.base_dir / month →ローカルのDL成功のディレクトリ
        
        if not month_dir.exists():→DL成功したはずのyyymmのディレクトリがない
            logger.warning(f"Directory not found: {month_dir}")
            upload_results['failed'].append(month)
            continue →UP失敗の辞書に追加
        
        try:
            # 月ディレクトリ内のCSVとZIPをアップロード
            destination_prefix = f"raw_data/{month}"
            
            # CSVファイルをアップロード
            csv_uris = self.uploader.upload_directory(
                str(month_dir), 
                destination_prefix,
                file_extension=".csv"
            )
            
            # ZIPファイルを日付付きでバックアップアップロード
            today_str = datetime.today().strftime('%Y-%m-%d')
            zip_uris = self.uploader.upload_directory(
                str(month_dir),
                f"archives/{month}/{today_str}",  # 日付付きパス
                file_extension=".zip"
            )
            
            uploaded_uris = csv_uris + zip_uris
            
            # 古いZIPバージョンをクリーンアップ
            self._cleanup_old_zip_versions()
            
            logger.info(f"Uploaded {len(uploaded_uris)} files for month {month}")
            upload_results['success'].append(month)
            
        except Exception as e:
            logger.error(f"Failed to upload data for month {month}: {e}")
            upload_results['failed'].append(month)
    
    return upload_results →up成功可否の辞書を返す



def test_etl_for_days(pipeline):
    """日数指定ETLテスト"""
    print_test_header("日数指定ETLテスト")
    
    # 少ない日数でテスト（1日分）
    test_days = 1
    
    try:
        print_result(True, f"テスト対象: 過去{test_days}日分")
        
        # ETL実行
        results = pipeline.run_etl_for_days(test_days) 
        
        # 戻り値形式チェック
        required_keys = ['download_results', 'upload_results', 'overall_status', 'message']
        for key in required_keys:
            if key in results:
                print_result(True, f"戻り値キー確認: {key}")
            else:
                print_result(False, f"戻り値キー不足: {key}")
                return
        
        # 結果詳細表示
        if results['download_results']['success']:
            print_result(True, f"ダウンロード成功: {', '.join(results['download_results']['success'])}")
        if results['download_results']['failed']:
            print_result(True, f"ダウンロード失敗: {', '.join(results['download_results']['failed'])}")
        
        if results['upload_results']['success']:
            print_result(True, f"アップロード成功: {', '.join(results['upload_results']['success'])}")
        if results['upload_results']['failed']:
            print_result(True, f"アップロード失敗: {', '.join(results['upload_results']['failed'])}")
        print_result(True, f"総合ステータス: {results['overall_status']}")
        
        # 成功判定
        if results['overall_status'] in ['success', 'partial']:
            print_result(True, "日数指定ETL正常完了")
        else:
            print_result(False, "日数指定ETL処理失敗")
            
    except Exception as e:
        print_result(False, f"日数指定ETLエラー: {e}")




def run_etl_for_days(self, days=5):
    """
    日数指定でETLパイプラインを実行
    
    Args:
        days (int): 今日から遡る日数
        
    Returns:
        dict: 実行結果サマリー
    """
    logger.info(f"Starting ETL pipeline for {days} days")
    
    # Phase 1: Extract (データダウンロード)
    logger.info("Phase 1: Extracting data from TEPCO website")
    download_results = self.downloader.download_for_days(days) →ダウンロード可否の結果の辞書を受け取る
    
    if not download_results['success']:
        logger.warning("No data downloaded successfully. Skipping upload phase.")
        return {
            'download_results': download_results,
            'upload_results': {'success': [], 'failed': []},
            'overall_status': 'failed',
            'message': 'ダウンロードに失敗したため、アップロードをスキップしました'
        }
    
    # Phase 2: Load (GCSアップロード)
    logger.info("Phase 2: Loading data to Google Cloud Storage")
    upload_results = self._upload_downloaded_data(download_results['success'])
    
    # 結果サマリー作成
    overall_status = 'success' if download_results['success'] and upload_results['success'] else 'partial'
    
    return {
        'download_results': download_results,
        'upload_results': upload_results,
        'overall_status': overall_status,
        'message': self._create_summary_message(download_results, upload_results)
    }


def download_for_days(self, days=5):
    """
    指定日数分のデータをダウンロード
    
    Args:
        days (int): 今日から遡る日数
        
    Returns:
        dict: ダウンロード結果 {'success': [...], 'failed': [...]}
    """
    months = self.get_required_months(days) →引数days日前の日付のyyyymmを取得
    results = {'success': [], 'failed': []}
    
    for month in sorted(months):
        try:
            if self.download_month_data(month): →ダウンロードを実行し成功ならtureを返す
                results['success'].append(month) →上記のtureを受け取ったら成功の辞書に追加
            else:
                results['failed'].append(month)
        except Exception as e:
            logger.error(f"Failed to download {month}: {e}")
            results['failed'].append(month)
    
    return results →結果の辞書を返す



def _process_raw_csv_to_hourly(self, input_csv_path):
    """
    東電の原形CSVから1時間データのみを抽出してBigQuery用フォーマットに変換
    
    Args:
        input_csv_path (str): 入力CSVファイルパス
        
    Returns:
        str: 加工済みCSVファイルのパス
        
    Raises:
        ValueError: CSVの構造が期待と異なる場合
    """
    # 加工済みファイルのパスを生成
    base_name = os.path.basename(input_csv_path)
    dir_name = os.path.dirname(input_csv_path)
    processed_filename = base_name.replace('_power_usage.csv', '_hourly_temp.csv')
    output_csv_path = os.path.join(dir_name, processed_filename)
    
    try:
        logger.info(f"Processing CSV to hourly data: {input_csv_path}")
        
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
            raise ValueError("Header line not found in CSV")
        
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
                    
                    # データの抽出
                    actual_power = float(parts[2])
                    supply_capacity = float(parts[5])
                    
                    # BigQuery用行データ作成
                    output_line = f"{formatted_date},{hour},{actual_power},{supply_capacity}"
                    output_lines.append(output_line)
                    processed_count += 1
                    
                except (ValueError, IndexError) as e:
                    logger.warning(f"Skipping invalid row {i}: {line} - {e}")
                    continue
        
        # 出力CSVファイルに書き込み
        with open(output_csv_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(output_lines))
        
        logger.info(f"Successfully processed {processed_count} hourly records to {output_csv_path}")
        return output_csv_path
        
    except Exception as e:
        logger.error(f"Error processing CSV to hourly data: {e}")
        raise