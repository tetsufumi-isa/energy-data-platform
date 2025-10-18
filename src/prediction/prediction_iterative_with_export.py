# %%
# ================================================================
# 日次予測実行スクリプト（Phase 11）
# 目的: 今日から14日間の電力使用量を予測
# データソース: BigQuery（昨日までの学習データ・今日からの気象データ）
# 出力: CSV形式の予測結果 + BigQueryステータスログ
# 検証: 別モジュール（14日に1回実行）
# ================================================================

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import mean_absolute_percentage_error, mean_absolute_error, r2_score
import xgboost as xgb
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import warnings
import os
from pathlib import Path
from logging import getLogger, FileHandler, StreamHandler, Formatter, INFO, LogRecord
import sys
from google.cloud import bigquery
import uuid
import json
warnings.filterwarnings('ignore')

# 日本語フォント設定
plt.rcParams['font.family'] = 'Meiryo'
plt.rcParams['figure.figsize'] = (12, 8)
plt.rcParams['font.size'] = 10

# %%
# ================================================================
# ロガー定義・ログ設定
# ================================================================

# モジュールレベルのロガー定義
logger = getLogger(__name__)

# JSON形式のログフォーマッター
class JsonFormatter(Formatter):
    """JSON形式でログを出力するカスタムフォーマッター"""
    def format(self, record: LogRecord) -> str:
        log_data = {
            'timestamp': self.formatTime(record, self.datefmt),
            'level': record.levelname,
            'message': record.getMessage(),
            'logger': record.name,
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        # プロセスステータスデータがあれば含める（BigQueryスキーマに準拠した辞書）
        if hasattr(record, 'process_status'):
            log_data['process_status'] = record.process_status

        return json.dumps(log_data, ensure_ascii=False)

# ログ設定
def setup_prediction_logging():
    """
    予測実験用のログ設定（JSON形式）

    モジュールレベルのloggerに対してハンドラーを設定する。
    loggerオブジェクト自体は返さず、ログファイルパスのみ返す。
    """
    # ログディレクトリ作成
    energy_env_path = os.getenv('ENERGY_ENV_PATH', '.')
    log_dir = Path(energy_env_path) / 'logs' / 'predictions'
    log_dir.mkdir(parents=True, exist_ok=True)

    # ログファイル名（タイムスタンプ付き・.jsonl形式）
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = log_dir / f'prediction_iterative_{timestamp}.jsonl'

    # ログレベル設定
    logger.setLevel(INFO)

    # 既存ハンドラーをクリア（重複防止）
    logger.handlers.clear()

    # JSONフォーマッター
    json_formatter = JsonFormatter()

    # ファイルハンドラー（JSON形式）
    file_handler = FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(json_formatter)
    logger.addHandler(file_handler)

    # コンソールハンドラー（通常形式・見やすさ優先）
    console_handler = StreamHandler(sys.stdout)
    console_handler.setFormatter(Formatter('%(message)s'))
    logger.addHandler(console_handler)

    return log_file

# ログ設定実行
log_file_path = setup_prediction_logging()

# %%
# ================================================================
# 統合ログ保存関数（ファイル + BQ）
# ================================================================

def log_and_save_to_bq(client, process_status, log_level='INFO'):
    """
    ログをファイルとBigQueryの両方に保存（データ一元化）

    Args:
        client: BigQueryクライアント
        process_status: プロセス実行ステータス（BigQueryのprocess_execution_logテーブルスキーマに準拠した辞書）
        log_level: ログレベル（'INFO', 'ERROR'など）

    Returns:
        bool: BQ保存成功=True, 失敗=False
    """
    # BQ用にデータ整形（日付型をISO形式文字列に変換）
    table_id = 'energy-env.prod_energy_data.process_execution_log'
    bq_data = process_status.copy()

    # started_at変換（datetime → ISO形式文字列）
    if 'started_at' in bq_data and bq_data['started_at']:
        if isinstance(bq_data['started_at'], datetime):
            bq_data['started_at'] = bq_data['started_at'].isoformat()
        else:
            raise TypeError(f"started_atにdatetimeではない値が発生しています。実際の型: {type(bq_data['started_at'])}, 値: {bq_data['started_at']}")

    # completed_at変換（datetime → ISO形式文字列）
    if 'completed_at' in bq_data and bq_data['completed_at']:
        if isinstance(bq_data['completed_at'], datetime):
            bq_data['completed_at'] = bq_data['completed_at'].isoformat()
        else:
            raise TypeError(f"completed_atにdatetimeではない値が発生しています。実際の型: {type(bq_data['completed_at'])}, 値: {bq_data['completed_at']}")

    # date変換（date → 文字列）
    if 'date' in bq_data and bq_data['date']:
        bq_data['date'] = str(bq_data['date'])

    # client.insert_rows_json()は成功は空で失敗時のみエラー情報の入ったリストを返す
    errors = client.insert_rows_json(table_id, [bq_data])

    # ファイルへのログ出力（変換済みbq_dataを使用してJSON serialization問題を回避）
    log_message = f"{process_status.get('process_type', 'UNKNOWN')}: {process_status.get('status', 'UNKNOWN')}"
    if log_level == 'INFO':
        logger.info(log_message, extra={'process_status': bq_data})
    elif log_level == 'ERROR':
        logger.error(log_message, extra={'process_status': bq_data})

    if errors:
        logger.error(f"BQインサートエラー: {errors}")
        return False
    else:
        logger.info(f"BQ保存成功: execution_id={process_status.get('execution_id')}")
        return True

# %%
# ================================================================
# 予測実行開始（実行ID生成）
# ================================================================

# 実行ID生成（ステータスログ用）
execution_id = str(uuid.uuid4())
prediction_start_time = datetime.now()

logger.info("段階的予測実験開始")
logger.info("=" * 60)
logger.info(f"実行ID: {execution_id}")
logger.info(f"ログファイル: {log_file_path}")
print("段階的予測テスト開始")
print("=" * 60)
print(f"実行ID: {execution_id}")

# %%
# ================================================================
# 1. BigQueryクライアント初期化・データ読み込み
# ================================================================

# 環境変数からベースパスを取得
energy_env_path = os.getenv('ENERGY_ENV_PATH', '.')

# BigQueryクライアント初期化
logger.info("BigQueryクライアント初期化")
client = bigquery.Client(project='energy-env')
print("BigQueryクライアント初期化完了")

try:
    # ml_featuresテーブルから学習データ取得（実行日の前日まで）
    logger.info("ml_featuresテーブルから学習データ取得開始")
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    logger.info(f"学習データ期間: ～{yesterday}")
    query_ml_features = f"""
    SELECT
        date,
        hour,
        actual_power,
        supply_capacity,
        temperature_2m,
        relative_humidity_2m,
        precipitation,
        weather_code,
        day_of_week,
        is_weekend,
        is_holiday,
        month,
        hour_sin,
        hour_cos,
        lag_1_day,
        lag_7_day,
        lag_1_business_day
    FROM `energy-env.prod_energy_data.ml_features`
    WHERE date <= '{yesterday}'
    ORDER BY date, hour
    """
    ml_features_train = client.query(query_ml_features).to_dataframe()
    logger.info(f"学習データ取得完了: {len(ml_features_train):,}件")
    print(f"学習データ取得完了: {len(ml_features_train):,}件")

    # datetime列作成
    ml_features_train['datetime'] = pd.to_datetime(
        ml_features_train['date'].astype(str) + ' ' +
        ml_features_train['hour'].astype(str).str.zfill(2) + ':00:00'
    )
    ml_features_train = ml_features_train.set_index('datetime')

    # 予測期間設定（今日から14日間）
    today = datetime.now().strftime('%Y-%m-%d')
    end_date_str = (datetime.now() + timedelta(days=13)).strftime('%Y-%m-%d')
    logger.info(f"予測期間: {today} ～ {end_date_str}")

    # calendar_dataテーブル取得（営業日判定用・予測期間のみ）
    logger.info("calendar_dataテーブル取得開始")
    query_calendar = f"""
    SELECT
        date,
        day_of_week,
        is_weekend,
        is_holiday
    FROM `energy-env.prod_energy_data.calendar_data`
    WHERE date BETWEEN '{today}' AND '{end_date_str}'
    ORDER BY date
    """
    calendar_data = client.query(query_calendar).to_dataframe()
    calendar_data['date'] = pd.to_datetime(calendar_data['date']).dt.date
    calendar_data = calendar_data.set_index('date')
    logger.info(f"カレンダーデータ取得完了: {len(calendar_data):,}件")
    print(f"カレンダーデータ取得完了: {len(calendar_data):,}件")

    # 予測期間の気象・カレンダーデータ取得（未来データ生成用・今日から14日間）
    logger.info("予測期間の気象・カレンダーデータ取得開始")
    query_future_data = f"""
    SELECT
        w.date,
        w.hour,
        w.temperature_2m,
        w.relative_humidity_2m,
        w.precipitation,
        w.weather_code,
        c.day_of_week,
        c.is_weekend,
        c.is_holiday,
        EXTRACT(MONTH FROM w.date) as month
    FROM (
        SELECT *
        FROM `energy-env.prod_energy_data.weather_data`
        WHERE date BETWEEN '{today}' AND '{end_date_str}'
            AND prefecture = '千葉県'
    ) w
    LEFT JOIN `energy-env.prod_energy_data.calendar_data` c
        ON w.date = c.date
    ORDER BY w.date, w.hour
    """
    future_features = client.query(query_future_data).to_dataframe()

    # hour列を数値型に変換（BQから文字列で取得されるため）
    future_features['hour'] = pd.to_numeric(future_features['hour'])

    future_features['datetime'] = pd.to_datetime(
        future_features['date'].astype(str) + ' ' +
        future_features['hour'].astype(str).str.zfill(2) + ':00:00'
    )
    future_features = future_features.set_index('datetime')

    # 循環特徴量追加（hour_sin, hour_cos）
    future_features['hour_sin'] = np.sin(2 * np.pi * future_features['hour'] / 24)
    future_features['hour_cos'] = np.cos(2 * np.pi * future_features['hour'] / 24)

    logger.info(f"予測期間の気象・カレンダーデータ取得完了: {len(future_features):,}件")
    print(f"予測期間の気象・カレンダーデータ取得完了: {len(future_features):,}件")

    print(f"データ準備完了")

except Exception as e:
    # BigQueryエラー（接続・クエリ実行エラー）をログに記録
    logger.error(f"BigQueryエラー: {e}")
    logger.error(f"エラー詳細: {type(e).__name__}")
    print(f"\nBigQueryエラーが発生しました: {e}")
    print(f"ログファイルを確認してください: {log_file_path}")
    # エラーを再送出してプログラム停止
    raise

# %%
# ================================================================
# 2. Phase 9特徴量定義（12特徴量）
# ================================================================

# Phase 9で使用した12特徴量を定義
features = [
    'hour',                   # 時間（0-23）
    'is_weekend',             # 週末フラグ
    'is_holiday',             # 祝日フラグ  
    'month',                  # 月（1-12）
    'hour_sin',               # 時間周期性（sin）
    'hour_cos',               # 時間周期性（cos）
    'lag_1_day',              # 1日前同時刻（重要！）
    'lag_7_day',              # 7日前同時刻
    'lag_1_business_day',     # 1営業日前同時刻（重要度84.3%！）
    'temperature_2m',         # 気温
    'relative_humidity_2m',   # 湿度
    'precipitation'           # 降水量
]

print(f"\n使用特徴量: {len(features)}個")
for i, feature in enumerate(features, 1):
    print(f"  {i:2d}. {feature}")

# %%
# ================================================================
# 3. XGBoostモデル学習
# ================================================================

# 学習データ準備
X_train = ml_features_train[features]
y_train = ml_features_train['actual_power']

print(f"\nXGBoostモデル学習開始")
print(f"学習データ: {len(X_train):,}件（欠損値込み）")
print(f"学習期間: {ml_features_train.index.min()} ～ {ml_features_train.index.max()}")

# XGBoostモデル（Phase 9設定）
xgb_model = xgb.XGBRegressor(
    n_estimators=200,
    max_depth=8,
    learning_rate=0.05,
    random_state=42,
    verbosity=0
)

# モデル学習
logger.info("XGBoostモデル学習開始")
xgb_model.fit(X_train, y_train)
logger.info("XGBoostモデル学習完了")
print("XGBoostモデル学習完了")

# %%
# ================================================================
# 4. 営業日データ準備 + 特徴量準備関数
# ================================================================

# 営業日のみに絞ったDataFrameを事前作成
# 過去20日分のみ（lag_1_business_dayの探索範囲）
# タイムゾーンnaiveなdatetimeに変換（pandasのDatetimeIndexと比較するため）
lookback_start = pd.to_datetime((datetime.now() - timedelta(days=20)))
business_days_train = ml_features_train[
    (ml_features_train.index >= lookback_start) &
    (~ml_features_train['is_holiday']) &
    (~ml_features_train['is_weekend'])
][['actual_power']]  # 実績値のみ

business_days_future = calendar_data[
    (~calendar_data['is_holiday']) & (~calendar_data['is_weekend'])
].index  # 日付のみ（Index化）

def prepare_features(target_datetime, predictions):
    """
    予測対象時刻の特徴量を準備（BQ対応版）

    Args:
        target_datetime: 予測対象日時
        predictions: 過去の予測値辞書

    Returns:
        list: 12特徴量の値リスト
    """
    # future_featuresから該当時刻のデータを取得
    if target_datetime not in future_features.index:
        raise ValueError(f"予測対象日時 {target_datetime} が future_features に見つかりません")

    # 基本特徴量を取得（気象・カレンダー・循環特徴量）
    row = future_features.loc[target_datetime]

    # 12特徴量を順番に設定
    feature_values = []
    for feature in features:
        if feature == 'lag_1_day':
            # 1日前の予測値
            lag_datetime = target_datetime - timedelta(days=1)
            if lag_datetime in predictions:
                feature_values.append(predictions[lag_datetime])
            else:
                # 予測値がない場合（予測期間前）はml_features_trainから取得
                if lag_datetime in ml_features_train.index:
                    feature_values.append(ml_features_train.loc[lag_datetime, 'actual_power'])
                else:
                    feature_values.append(np.nan)

        elif feature == 'lag_7_day':
            # 7日前の予測値
            lag_datetime = target_datetime - timedelta(days=7)
            if lag_datetime in predictions:
                feature_values.append(predictions[lag_datetime])
            else:
                # 予測値がない場合はml_features_trainから取得
                if lag_datetime in ml_features_train.index:
                    feature_values.append(ml_features_train.loc[lag_datetime, 'actual_power'])
                else:
                    feature_values.append(np.nan)

        elif feature == 'lag_1_business_day':
            # 1営業日前の予測値（最大20日前まで探索・長期休暇対応）
            found = False
            for days_back in range(1, 21):
                lag_datetime = target_datetime - timedelta(days=days_back)
                lag_date = lag_datetime.date()

                # 予測値優先（未来の営業日）
                if lag_datetime in predictions and lag_date in business_days_future:
                    feature_values.append(predictions[lag_datetime])
                    found = True
                    break
                # 学習データから取得（過去の営業日）
                elif lag_datetime in business_days_train.index:
                    feature_values.append(business_days_train.loc[lag_datetime, 'actual_power'])
                    found = True
                    break

            if not found:
                feature_values.append(np.nan)

        else:
            # その他の特徴量はfuture_featuresから取得
            feature_values.append(row[feature])

    return feature_values

# %%
# ================================================================
# 5. 段階的予測実行（今日から14日間）
# ================================================================

# 予測期間設定（今日から14日間）
start_date = pd.to_datetime(today)
end_date = pd.to_datetime(end_date_str)

# 予測結果格納辞書
predictions = {}
daily_results = []

logger.info("段階的予測実行開始")
logger.info(f"予測期間: {start_date.date()} ～ {end_date.date()}")
logger.info(f"予測回数: {14 * 24}回（14日×24時間）")

print(f"\n段階的予測実行開始")
print(f"予測期間: {start_date.date()} ～ {end_date.date()}")
print(f"予測回数: {14 * 24}回（14日×24時間）")

# 14日間の段階的予測
current_date = start_date

for day in range(14):
    print(f"\nDay {day+1}: {current_date.strftime('%Y-%m-%d')}")

    # 1日24時間の予測
    for hour in range(24):
        target_datetime = current_date + timedelta(hours=hour)

        # 特徴量準備
        feature_values = prepare_features(target_datetime, predictions)

        # DataFrameに変換（XGBoostに入力）
        X_pred = pd.DataFrame([feature_values], columns=features)

        # 予測実行
        pred_value = xgb_model.predict(X_pred)[0]
        predictions[target_datetime] = pred_value

    current_date += timedelta(days=1)

logger.info("段階的予測完了")
print(f"\n段階的予測完了")

# 予測完了時刻・処理時間計算
prediction_end_time = datetime.now()
duration_seconds = int((prediction_end_time - prediction_start_time).total_seconds())

# %%
# ================================================================
# 6. 予測結果CSV保存
# ================================================================

def save_prediction_results_to_csv(predictions, execution_id):
    """
    予測結果をCSV形式で保存（BigQueryスキーマに準拠）

    Args:
        predictions (dict): 予測結果辞書 {datetime: predicted_value}
        execution_id (str): 実行ID

    Returns:
        dict: 保存結果情報
    """
    # 実行タイムスタンプ生成（日本時間）
    now = datetime.now()
    timestamp = now.strftime('%Y%m%d_%H%M%S')
    run_date = now.strftime('%Y-%m-%d')

    # ディレクトリ作成
    base_path = Path(energy_env_path) / 'data' / 'predictions'
    base_path.mkdir(parents=True, exist_ok=True)

    # 予測結果をDataFrameに変換（BigQueryスキーマに準拠）
    prediction_data = []

    for target_datetime, predicted_value in predictions.items():
        prediction_data.append({
            'execution_id': execution_id,
            'prediction_date': target_datetime.strftime('%Y-%m-%d'),
            'prediction_hour': target_datetime.hour,
            'predicted_power_kwh': round(predicted_value, 2),
            'created_at': now.strftime('%Y-%m-%d %H:%M:%S')
        })

    # 予測結果CSV保存
    predictions_df = pd.DataFrame(prediction_data)
    csv_filename = f"predictions_{timestamp}.csv"
    csv_filepath = base_path / csv_filename
    predictions_df.to_csv(csv_filepath, index=False, encoding='utf-8')

    # 保存結果返却
    result = {
        'success': True,
        'timestamp': timestamp,
        'run_date': run_date,
        'csv_file': str(csv_filepath),
        'prediction_count': len(predictions),
        'date_range': f"{min(predictions.keys()).date()} to {max(predictions.keys()).date()}"
    }

    return result

# 予測結果保存実行
logger.info("予測結果CSV保存開始")
print(f"\n予測結果CSV保存開始")
print("=" * 50)

save_result = save_prediction_results_to_csv(predictions, execution_id)

if save_result['success']:
    logger.info("予測結果保存完了")
    logger.info(f"実行タイムスタンプ: {save_result['timestamp']}")
    logger.info(f"予測件数: {save_result['prediction_count']}件")
    logger.info(f"保存ファイル: {save_result['csv_file']}")

    print(f"予測結果保存完了")
    print(f"実行タイムスタンプ: {save_result['timestamp']}")
    print(f"保存ファイル: {save_result['csv_file']}")
    print(f"データ概要:")
    print(f"  予測件数: {save_result['prediction_count']}件")
    print(f"  対象期間: {save_result['date_range']}")
else:
    logger.error("予測結果保存失敗")
    print(f"保存失敗")

# %%
# ================================================================
# 7. 予測結果BigQuery保存
# ================================================================

logger.info("予測結果BigQuery保存開始")
print(f"\n予測結果BigQuery保存開始")
print("=" * 50)

# BigQueryテーブル設定
dataset_id = 'prod_energy_data'
table_id = 'prediction_results'
table_ref = f"{client.project}.{dataset_id}.{table_id}"

# 予測結果をBigQuery用に変換
now = pd.Timestamp.now()  # サーバーローカル時間（JST）
bq_prediction_data = []
for target_datetime, predicted_value in predictions.items():
    bq_prediction_data.append({
        'execution_id': execution_id,
        'prediction_date': pd.Timestamp(target_datetime.date()),  # pandas Timestamp
        'prediction_hour': target_datetime.hour,
        'predicted_power_kwh': round(predicted_value, 2),
        'created_at': now
    })

bq_predictions_df = pd.DataFrame(bq_prediction_data)
bq_insert_success = False
bq_error_message = None

try:
    # BigQueryへ挿入
    job = client.load_table_from_dataframe(
        bq_predictions_df,
        table_ref,
        job_config=bigquery.LoadJobConfig(
            write_disposition="WRITE_APPEND"
        )
    )
    job.result()  # Wait for the job to complete

    bq_insert_success = True
    logger.info(f"予測結果BigQuery保存完了: {len(bq_predictions_df)}件")
    print(f"予測結果BigQuery保存完了: {len(bq_predictions_df)}件")

except Exception as e:
    bq_error_message = str(e)
    logger.error(f"BigQuery保存エラー: {bq_error_message}")
    print(f"BigQuery保存エラー: {bq_error_message}")
    print(f"注意: 予測結果はCSVファイルに保存済みです")

# %%
# ================================================================
# 8. プロセス実行ステータス記録
# ================================================================

logger.info("プロセス実行ステータス記録開始")

# プロセス実行ステータス作成（BigQueryのprocess_execution_logテーブルスキーマに準拠）
process_status = {
    'execution_id': execution_id,
    'date': str(end_date.date()),  # 文字列に変換
    'process_type': 'ML_PREDICTION',
    'status': 'SUCCESS',
    'error_message': None,
    'started_at': prediction_start_time,
    'completed_at': prediction_end_time,
    'duration_seconds': duration_seconds,
    'records_processed': len(predictions),
    'file_size_mb': None,
    'additional_info': json.dumps({  # JSON文字列に変換
        'prediction_period': f"{start_date.date()} to {end_date.date()}",
        'prediction_count': len(predictions),
        'csv_saved': save_result['success'],
        'bq_saved': bq_insert_success
    })
}

# ローカルログ保存 + BigQueryインサート
try:
    log_and_save_to_bq(client=client, process_status=process_status, log_level='INFO')
    logger.info("プロセス実行ステータス記録完了（ローカル + BQ）")
    print(f"\nプロセス実行ステータス記録完了（ローカル + BQ）")
except Exception as e:
    logger.error(f"プロセス実行ステータス記録エラー: {e}")
    print(f"プロセス実行ステータス記録エラー: {e}")

logger.info("日次予測処理完了")
print(f"\n日次予測処理完了")
