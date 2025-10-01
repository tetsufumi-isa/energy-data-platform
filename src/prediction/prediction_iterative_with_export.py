# %%
# ================================================================
# 段階的予測テスト + 予測結果保存機能（Phase 11ダッシュボード用）
# 目的: 実運用での予測値依存による精度劣化測定 + CSV保存
# 新機能: 予測結果をCSV形式で保存（GCSアップロード・Looker Studio用）
# ログ対応: 重要なプロセスをログ出力
# データソース: BigQuery（CSV廃止）
# ================================================================

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import mean_absolute_percentage_error, mean_absolute_error, r2_score
import xgboost as xgb
from datetime import datetime, timedelta
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
    # 1. ファイルへのログ出力（JSON形式）
    log_message = f"{process_status.get('process_type', 'UNKNOWN')}: {process_status.get('status', 'UNKNOWN')}"
    if log_level == 'INFO':
        logger.info(log_message, extra={'process_status': process_status})
    elif log_level == 'ERROR':
        logger.error(log_message, extra={'process_status': process_status})

    # 2. BigQueryへのインサート（同じデータ）
    table_id = 'energy-env.prod_energy_data.process_execution_log'

    # BQ用にデータ整形（日付型をISO形式文字列に変換）
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

logger.info("段階的予測実験開始（BQ対応版・保存機能付き・dropna()なし）")
logger.info("=" * 60)
logger.info(f"実行ID: {execution_id}")
logger.info(f"ログファイル: {log_file_path}")
print("段階的予測テスト開始（BQ対応版・保存機能付き・dropna()なし）")
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

# ml_featuresテーブルから学習データ取得（～2025-05-31）
logger.info("ml_featuresテーブルから学習データ取得開始")
query_ml_features = """
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
WHERE date <= '2025-05-31'
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

# 予測期間の検証用データ取得（2025-06-01～2025-06-16）
logger.info("予測期間の検証用データ取得開始")
query_validation = """
SELECT
    date,
    hour,
    actual_power
FROM `energy-env.prod_energy_data.ml_features`
WHERE date BETWEEN '2025-06-01' AND '2025-06-16'
ORDER BY date, hour
"""
validation_data = client.query(query_validation).to_dataframe()
validation_data['datetime'] = pd.to_datetime(
    validation_data['date'].astype(str) + ' ' +
    validation_data['hour'].astype(str).str.zfill(2) + ':00:00'
)
validation_data = validation_data.set_index('datetime')
logger.info(f"検証用データ取得完了: {len(validation_data):,}件")
print(f"検証用データ取得完了: {len(validation_data):,}件")

# calendar_dataテーブル取得
logger.info("calendar_dataテーブル取得開始")
query_calendar = """
SELECT
    date,
    day_of_week,
    is_weekend,
    is_holiday
FROM `energy-env.prod_energy_data.calendar_data`
ORDER BY date
"""
calendar_data = client.query(query_calendar).to_dataframe()
calendar_data['date'] = pd.to_datetime(calendar_data['date'])
calendar_data = calendar_data.set_index('date')
logger.info(f"カレンダーデータ取得完了: {len(calendar_data):,}件")
print(f"カレンダーデータ取得完了: {len(calendar_data):,}件")

# 予測期間の気象・カレンダーデータ取得（未来データ生成用）
logger.info("予測期間の気象・カレンダーデータ取得開始")
query_future_data = """
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
FROM `energy-env.prod_energy_data.weather_data` w
LEFT JOIN `energy-env.prod_energy_data.calendar_data` c
    ON w.date = c.date
WHERE w.date BETWEEN '2025-06-01' AND '2025-06-16'
    AND w.prefecture = 'chiba'
ORDER BY w.date, w.hour
"""
future_features = client.query(query_future_data).to_dataframe()
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
# 3. XGBoostモデル学習（土日祝日対応・dropna()なし）
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
# 4. 特徴量準備関数（フォールバック完全削除版）
# ================================================================

def prepare_features_no_fallback(target_datetime, predictions):
    """
    予測対象時刻の特徴量を準備（BQ対応版・フォールバック完全削除版）

    Args:
        target_datetime: 予測対象日時
        predictions: 過去の予測値辞書

    Returns:
        list: 12特徴量の値リスト
    """
    # future_featuresから該当時刻のデータを取得
    if target_datetime not in future_features.index:
        raise ValueError(f"Target datetime {target_datetime} not found in future_features")

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
            # 1営業日前の予測値（最大7日前まで探索）
            found = False
            for days_back in range(1, 8):
                lag_datetime = target_datetime - timedelta(days=days_back)
                lag_date = lag_datetime.date()

                # 営業日判定
                if lag_date in calendar_data.index:
                    if not calendar_data.loc[lag_date, 'is_holiday'] and lag_datetime.weekday() < 5:
                        # 予測値があれば使用
                        if lag_datetime in predictions:
                            feature_values.append(predictions[lag_datetime])
                            found = True
                            break
                        # 予測値がない場合はml_features_trainから取得
                        elif lag_datetime in ml_features_train.index:
                            feature_values.append(ml_features_train.loc[lag_datetime, 'actual_power'])
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
# 5. 段階的予測実行（2025-06-01 ～ 2025-06-16）
# ================================================================

# 予測期間設定
start_date = pd.to_datetime('2025-06-01')
end_date = pd.to_datetime('2025-06-16')

# 予測結果格納辞書
predictions = {}
daily_results = []

logger.info("段階的予測実行開始（フォールバック完全削除版）")
logger.info(f"予測期間: {start_date.date()} ～ {end_date.date()}")
logger.info(f"予測回数: {16 * 24}回（16日×24時間）")
logger.info("dropna()なし - XGBoost欠損値自動処理使用")
logger.info("フォールバック処理完全削除")

print(f"\n段階的予測実行開始（フォールバック完全削除版）")
print(f"予測期間: {start_date.date()} ～ {end_date.date()}")
print(f"予測回数: {16 * 24}回（16日×24時間）")

# 16日間の段階的予測
current_date = start_date

for day in range(16):
    daily_predictions = []
    daily_actuals = []
    
    print(f"\nDay {day+1}: {current_date.strftime('%Y-%m-%d')}")
    
    # 1日24時間の予測
    for hour in range(24):
        target_datetime = current_date + timedelta(hours=hour)
        
        # 特徴量準備（フォールバック完全削除版）
        feature_values = prepare_features_no_fallback(target_datetime, predictions)
        
        # DataFrameに変換（XGBoostに入力）
        X_pred = pd.DataFrame([feature_values], columns=features)
        
        # 予測実行
        pred_value = xgb_model.predict(X_pred)[0]
        predictions[target_datetime] = pred_value
        daily_predictions.append(pred_value)
        
        # 実績値取得（検証用）
        if target_datetime in validation_data.index:
            actual_value = validation_data.loc[target_datetime, 'actual_power']
            daily_actuals.append(actual_value)
    
    # 日別精度計算
    if len(daily_actuals) == 24:  # 完全な1日分のデータがある場合
        daily_mape = mean_absolute_percentage_error(daily_actuals, daily_predictions) * 100
        daily_mae = mean_absolute_error(daily_actuals, daily_predictions)
        daily_r2 = r2_score(daily_actuals, daily_predictions)
        
        daily_results.append({
            'day': day + 1,
            'date': current_date.strftime('%Y-%m-%d'),
            'mape': daily_mape,
            'mae': daily_mae,
            'r2': daily_r2,
            'predictions_mean': np.mean(daily_predictions),
            'actuals_mean': np.mean(daily_actuals)
        })
        
        print(f"  MAPE: {daily_mape:.2f}%, MAE: {daily_mae:.1f}万kW, R2: {daily_r2:.4f}")
    
    current_date += timedelta(days=1)

logger.info("段階的予測完了")
print(f"\n段階的予測完了")

# 予測完了時刻・処理時間計算
prediction_end_time = datetime.now()
duration_seconds = int((prediction_end_time - prediction_start_time).total_seconds())

# %%
# ================================================================
# 6. 全期間精度計算・結果分析
# ================================================================

# 全期間の予測値・実績値収集
all_predictions = []
all_actuals = []
prediction_datetimes = []

for dt, pred in predictions.items():
    if dt in validation_data.index:
        all_predictions.append(pred)
        all_actuals.append(validation_data.loc[dt, 'actual_power'])
        prediction_datetimes.append(dt)

# 全期間精度計算
overall_mape = mean_absolute_percentage_error(all_actuals, all_predictions) * 100
overall_mae = mean_absolute_error(all_actuals, all_predictions)
overall_r2 = r2_score(all_actuals, all_predictions)

logger.info("段階的予測 全期間結果計算完了")
logger.info(f"予測件数: {len(all_predictions)}件, MAPE: {overall_mape:.2f}%")

print(f"\n段階的予測 全期間結果")
print(f"=" * 40)
print(f"予測件数: {len(all_predictions)}件")
print(f"MAPE: {overall_mape:.2f}%")
print(f"MAE:  {overall_mae:.2f}万kW")
print(f"R2:   {overall_r2:.4f}")

# 統合ログ保存（ファイル + BQ）
logger.info("統合ログ保存開始（ファイル + BQ）")

# プロセス実行ステータス作成（BigQueryのprocess_execution_logテーブルスキーマに準拠した辞書）
process_status = {
    'execution_id': execution_id,
    'date': end_date.date(),
    'process_type': 'ML_PREDICTION',
    'status': 'SUCCESS',
    'error_message': None,
    'started_at': prediction_start_time,
    'completed_at': prediction_end_time,
    'duration_seconds': duration_seconds,
    'records_processed': len(all_predictions),
    'file_size_mb': None,
    'additional_info': {
        'mape': round(overall_mape, 2),
        'mae': round(overall_mae, 2),
        'r2': round(overall_r2, 4),
        'prediction_period': f"{start_date.date()} to {end_date.date()}"
    }
}

log_and_save_to_bq(client=client, process_status=process_status, log_level='INFO')
print(f"統合ログ保存完了（ファイル + BQ）")

# %%
# ================================================================
# 7. 【新機能】予測結果CSV保存機能
# ================================================================

def save_prediction_results_to_csv(predictions, daily_results):
    """
    予測結果をCSV形式で保存
    
    Args:
        predictions (dict): 予測結果辞書 {datetime: predicted_value}
        daily_results (list): 日別結果リスト（未使用）
    
    Returns:
        dict: 保存結果情報
    """
    # 実行タイムスタンプ生成
    now = datetime.now()
    timestamp = now.strftime('%Y%m%d_%H%M%S')
    run_date = now.strftime('%Y-%m-%d')
    
    # ディレクトリ作成
    base_path = Path(energy_env_path) / 'data' / 'predictions'
    base_path.mkdir(parents=True, exist_ok=True)
    
    # 予測結果をDataFrameに変換
    prediction_data = []
    
    for target_datetime, predicted_value in predictions.items():
        # 実績値を取得（ある場合のみ）
        actual_value = None
        error_abs = None
        error_rate = None

        if target_datetime in validation_data.index:
            actual_value = validation_data.loc[target_datetime, 'actual_power']
            error_abs = abs(predicted_value - actual_value)
            error_rate = error_abs / actual_value * 100
        
        prediction_data.append({
            'target_date': target_datetime.strftime('%Y-%m-%d'),
            'target_hour': target_datetime.hour,
            'target_weekday': target_datetime.weekday(),  # 0=月曜
            'target_is_weekend': 1 if target_datetime.weekday() >= 5 else 0,
            'predicted_power': round(predicted_value, 2),
            'actual_power': round(actual_value, 2) if actual_value is not None else None,
            'error_absolute': round(error_abs, 2) if error_abs is not None else None,
            'error_percentage': round(error_rate, 2) if error_rate is not None else None
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
        'date_range': f"{min(predictions.keys()).date()} to {max(predictions.keys()).date()}",
        'overall_mape': round(overall_mape, 2)
    }
    
    return result

# 予測結果保存実行
logger.info("予測結果CSV保存開始")
print(f"\n予測結果CSV保存開始")
print("=" * 50)

save_result = save_prediction_results_to_csv(predictions, daily_results)

if save_result['success']:
    logger.info("予測結果保存完了")
    logger.info(f"実行タイムスタンプ: {save_result['timestamp']}")
    logger.info(f"予測件数: {save_result['prediction_count']}件, 精度: MAPE {save_result['overall_mape']}%")
    logger.info(f"保存ファイル: {save_result['csv_file']}")
    
    print(f"予測結果保存完了")
    print(f"実行タイムスタンプ: {save_result['timestamp']}")
    print(f"保存ファイル: {save_result['csv_file']}")
    print(f"データ概要:")
    print(f"  予測件数: {save_result['prediction_count']}件")
    print(f"  対象期間: {save_result['date_range']}")
    print(f"  精度: MAPE {save_result['overall_mape']}%")
else:
    logger.error("予測結果保存失敗")
    print(f"保存失敗")

# %%
# ================================================================
# 8. 外れ値検出・分析（IQR法）
# ================================================================

print(f"\n外れ値検出・分析")
print(f"=" * 40)

# 残差計算
residuals = np.array(all_actuals) - np.array(all_predictions)
abs_residuals = np.abs(residuals)

# IQR法による外れ値検出
Q1 = np.percentile(abs_residuals, 25)
Q3 = np.percentile(abs_residuals, 75)
IQR = Q3 - Q1
outlier_threshold = Q3 + 1.5 * IQR

# 外れ値特定
outliers = abs_residuals > outlier_threshold
outliers_count = np.sum(outliers)

print(f"残差統計:")
print(f"  Q1: {Q1:.2f}万kW")
print(f"  Q3: {Q3:.2f}万kW") 
print(f"  IQR: {IQR:.2f}万kW")
print(f"  外れ値閾値: {outlier_threshold:.2f}万kW")
print(f"  外れ値: {outliers_count}件 ({outliers_count/len(abs_residuals)*100:.1f}%)")

# %%
# ================================================================
# 9. 実験総括・Phase 11準備完了確認
# ================================================================

print(f"\n段階的予測実験・Phase 11準備完了")
print("="*60)

print(f"【実験成果】")
print(f"段階的予測精度: MAPE {overall_mape:.2f}%")
print(f"前回固定予測からの劣化: +{overall_mape - 2.54:.2f}%")
print(f"外れ値: {outliers_count}件 ({outliers_count/len(abs_residuals)*100:.1f}%)")
print(f"土日祝日対応: dropna()なしでも安定運用")

print(f"\n【Phase 11ダッシュボード準備完了】")
print(f"予測結果CSV: {save_result['csv_file']}")
print(f"次ステップ: GCSUploader → BigQuery → Looker Studio")

print(f"\n【Phase 10完了判断】")
if overall_mape <= 3.5:
    print(f"MAPE {overall_mape:.2f}% - 実用レベル達成")
    print(f"Phase 10日次自動予測システム構築OK")
    print(f"Phase 11 Looker Studioダッシュボード移行OK")
else:
    print(f"MAPE {overall_mape:.2f}% - 精度向上策要検討")
    print(f"Phase 10システム化前に追加改良推奨")

logger.info("Phase 10段階的予測実験・保存機能付きバージョン完了")
logger.info("Phase 11 Looker Studioダッシュボード構築準備完了")

print(f"\nPhase 10段階的予測実験・保存機能付きバージョン完了")
print(f"Phase 11 Looker Studioダッシュボード構築準備完了")

# %%
# ================================================================
# 10. 保存したCSVファイルの確認
# ================================================================

print(f"\n保存されたCSVファイル確認")
print("=" * 50)

# 保存されたCSVの内容確認
if save_result['csv_file'] and os.path.exists(save_result['csv_file']):
    saved_df = pd.read_csv(save_result['csv_file'])
    print(f"予測結果CSV読み込み完了")
    print(f"データ形状: {saved_df.shape}")
    print(f"期間: {saved_df['target_date'].min()} ～ {saved_df['target_date'].max()}")
    print(f"時間範囲: {saved_df['target_hour'].min()}時 ～ {saved_df['target_hour'].max()}時")
    
    print(f"\n最初の3行:")
    print(saved_df.head(3).to_string(index=False))
    
    print(f"\n列情報:")
    for i, col in enumerate(saved_df.columns):
        print(f"  {i+1:2d}. {col}")

print(f"\n次のステップ:")
print(f"1. GCSUploaderでCSVファイルをGCSにアップロード")
print(f"2. BigQueryにEXTERNAL TABLE作成またはデータ投入")
print(f"3. Looker StudioでBigQueryデータソース接続")
print(f"4. ダッシュボード構築・公開設定")

# %%
# ================================================================
# エラーハンドリング（注意事項）
# ================================================================
#
# 現在のコードは段階的予測実験用のため、エラーハンドリングは最小限です。
# 本番運用時は以下の対応が必要：
#
# 1. try-exceptブロックで全体を囲む
# 2. エラー時にlog_and_save_to_bq()を呼び出し
#    - status='FAILED'
#    - error_message=str(e)
#    - 部分的な処理時間を記録
# 3. リトライロジックの実装（BQクエリ失敗時など）
#
# 例：
# try:
#     # 予測処理全体
#     ...
# except Exception as e:
#     logger.error(f"予測処理エラー: {e}")
#     # エラー時のプロセスステータス（BigQueryスキーマに準拠）
#     error_process_status = {
#         'execution_id': execution_id,
#         'date': end_date.date(),
#         'process_type': 'ML_PREDICTION',
#         'status': 'FAILED',
#         'error_message': str(e),
#         'started_at': prediction_start_time,
#         'completed_at': datetime.now(),
#         'duration_seconds': None,
#         'records_processed': None,
#         'file_size_mb': None,
#         'additional_info': None
#     }
#     log_and_save_to_bq(client=client, process_status=error_process_status, log_level='ERROR')
#     raise