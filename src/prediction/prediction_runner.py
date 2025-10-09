"""
予測実行モジュール - main_etl.pyから呼び出し用

日次予測実行：今日から16日間の電力使用量を予測
データソース: BigQuery（昨日までの学習データ・今日からの気象データ）
出力: CSV形式の予測結果 + BigQueryステータスログ
"""

import pandas as pd
import numpy as np
import xgboost as xgb
from datetime import datetime, timedelta
from pathlib import Path
from logging import getLogger
from google.cloud import bigquery
import uuid
import os

# モジュール専用のロガーを取得
logger = getLogger('energy_env.prediction_runner')


def run_daily_prediction(project_id="energy-env"):
    """
    日次予測実行（今日から16日間）

    Args:
        project_id (str): GCPプロジェクトID

    Returns:
        dict: 実行結果サマリー
    """
    # 実行ID生成
    execution_id = str(uuid.uuid4())
    prediction_start_time = datetime.now()

    logger.info(f"日次予測実行開始: execution_id={execution_id}")

    try:
        # BigQueryクライアント初期化
        client = bigquery.Client(project=project_id)

        # データ取得
        logger.info("BigQueryからデータ取得開始")
        ml_features_train, future_features, calendar_data = _fetch_data_from_bigquery(client)
        logger.info(f"データ取得完了: 学習データ{len(ml_features_train):,}件")

        # 特徴量定義
        features = [
            'hour', 'is_weekend', 'is_holiday', 'month',
            'hour_sin', 'hour_cos',
            'lag_1_day', 'lag_7_day', 'lag_1_business_day',
            'temperature_2m', 'relative_humidity_2m', 'precipitation'
        ]

        # モデル学習
        logger.info("XGBoostモデル学習開始")
        xgb_model = _train_model(ml_features_train, features)
        logger.info("XGBoostモデル学習完了")

        # 段階的予測実行
        logger.info("段階的予測実行開始")
        predictions = _run_iterative_prediction(
            xgb_model, features, ml_features_train,
            future_features, calendar_data
        )
        logger.info(f"段階的予測完了: {len(predictions)}件")

        # CSV保存
        logger.info("予測結果CSV保存開始")
        csv_result = _save_predictions_to_csv(predictions, execution_id)
        logger.info(f"CSV保存完了: {csv_result['csv_file']}")

        # BigQuery保存
        logger.info("予測結果BigQuery保存開始")
        bq_result = _save_predictions_to_bigquery(client, predictions, execution_id)

        if bq_result['success']:
            logger.info(f"BigQuery保存完了: {bq_result['rows_inserted']}行")
        else:
            logger.error(f"BigQuery保存失敗: {bq_result['error']}")

        # 実行完了
        prediction_end_time = datetime.now()
        duration_seconds = int((prediction_end_time - prediction_start_time).total_seconds())

        # ステータスログ記録
        _save_execution_status(
            client, execution_id, prediction_start_time,
            prediction_end_time, duration_seconds,
            len(predictions), csv_result['success'], bq_result['success']
        )

        logger.info(f"日次予測実行完了: execution_id={execution_id}")

        return {
            'status': 'success',
            'execution_id': execution_id,
            'prediction_count': len(predictions),
            'csv_file': csv_result['csv_file'],
            'bq_saved': bq_result['success'],
            'duration_seconds': duration_seconds
        }

    except Exception as e:
        logger.error(f"日次予測実行失敗: {e}")
        return {
            'status': 'failed',
            'error': str(e),
            'execution_id': execution_id
        }


def _fetch_data_from_bigquery(client):
    """BigQueryからデータ取得"""
    # 学習データ取得（昨日まで）
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    query_ml_features = f"""
    SELECT
        date, hour, actual_power, supply_capacity,
        temperature_2m, relative_humidity_2m, precipitation, weather_code,
        day_of_week, is_weekend, is_holiday, month,
        hour_sin, hour_cos, lag_1_day, lag_7_day, lag_1_business_day
    FROM `energy-env.prod_energy_data.ml_features`
    WHERE date <= '{yesterday}'
    ORDER BY date, hour
    """
    ml_features_train = client.query(query_ml_features).to_dataframe()

    # datetime列作成
    ml_features_train['datetime'] = pd.to_datetime(
        ml_features_train['date'].astype(str) + ' ' +
        ml_features_train['hour'].astype(str).str.zfill(2) + ':00:00'
    )
    ml_features_train = ml_features_train.set_index('datetime')

    # 予測期間設定（今日から16日間）
    today = datetime.now().strftime('%Y-%m-%d')
    end_date_str = (datetime.now() + timedelta(days=15)).strftime('%Y-%m-%d')

    # カレンダーデータ取得
    query_calendar = f"""
    SELECT date, day_of_week, is_weekend, is_holiday
    FROM `energy-env.prod_energy_data.calendar_data`
    WHERE date BETWEEN '{today}' AND '{end_date_str}'
    ORDER BY date
    """
    calendar_data = client.query(query_calendar).to_dataframe()
    calendar_data['date'] = pd.to_datetime(calendar_data['date']).dt.date
    calendar_data = calendar_data.set_index('date')

    # 予測期間の気象・カレンダーデータ取得
    query_future_data = f"""
    SELECT
        w.date, w.hour,
        w.temperature_2m, w.relative_humidity_2m, w.precipitation, w.weather_code,
        c.day_of_week, c.is_weekend, c.is_holiday,
        EXTRACT(MONTH FROM w.date) as month
    FROM (
        SELECT *
        FROM `energy-env.prod_energy_data.weather_data`
        WHERE date BETWEEN '{today}' AND '{end_date_str}'
            AND prefecture = 'chiba'
    ) w
    LEFT JOIN `energy-env.prod_energy_data.calendar_data` c
        ON w.date = c.date
    ORDER BY w.date, w.hour
    """
    future_features = client.query(query_future_data).to_dataframe()
    future_features['datetime'] = pd.to_datetime(
        future_features['date'].astype(str) + ' ' +
        future_features['hour'].astype(str).str.zfill(2) + ':00:00'
    )
    future_features = future_features.set_index('datetime')

    # 循環特徴量追加
    future_features['hour_sin'] = np.sin(2 * np.pi * future_features['hour'] / 24)
    future_features['hour_cos'] = np.cos(2 * np.pi * future_features['hour'] / 24)

    return ml_features_train, future_features, calendar_data


def _train_model(ml_features_train, features):
    """XGBoostモデル学習"""
    X_train = ml_features_train[features]
    y_train = ml_features_train['actual_power']

    xgb_model = xgb.XGBRegressor(
        n_estimators=200,
        max_depth=8,
        learning_rate=0.05,
        random_state=42,
        verbosity=0
    )

    xgb_model.fit(X_train, y_train)
    return xgb_model


def _run_iterative_prediction(xgb_model, features, ml_features_train, future_features, calendar_data):
    """段階的予測実行"""
    # 営業日データ準備
    lookback_start = pd.to_datetime(datetime.now() - timedelta(days=20))
    business_days_train = ml_features_train[
        (ml_features_train.index >= lookback_start) &
        (~ml_features_train['is_holiday']) &
        (~ml_features_train['is_weekend'])
    ][['actual_power']]

    business_days_future = calendar_data[
        (~calendar_data['is_holiday']) & (~calendar_data['is_weekend'])
    ].index

    # 予測期間設定
    today = datetime.now()
    predictions = {}

    # 16日間の段階的予測
    for day in range(16):
        current_date = today + timedelta(days=day)

        for hour in range(24):
            target_datetime = current_date.replace(hour=hour, minute=0, second=0, microsecond=0)

            # 特徴量準備
            feature_values = _prepare_features(
                target_datetime, predictions, features,
                future_features, ml_features_train,
                business_days_train, business_days_future
            )

            # 予測実行
            X_pred = pd.DataFrame([feature_values], columns=features)
            pred_value = xgb_model.predict(X_pred)[0]
            predictions[target_datetime] = pred_value

    return predictions


def _prepare_features(target_datetime, predictions, features, future_features,
                      ml_features_train, business_days_train, business_days_future):
    """予測対象時刻の特徴量を準備"""
    if target_datetime not in future_features.index:
        raise ValueError(f"予測対象日時 {target_datetime} が future_features に見つかりません")

    row = future_features.loc[target_datetime]
    feature_values = []

    for feature in features:
        if feature == 'lag_1_day':
            lag_datetime = target_datetime - timedelta(days=1)
            if lag_datetime in predictions:
                feature_values.append(predictions[lag_datetime])
            elif lag_datetime in ml_features_train.index:
                feature_values.append(ml_features_train.loc[lag_datetime, 'actual_power'])
            else:
                feature_values.append(np.nan)

        elif feature == 'lag_7_day':
            lag_datetime = target_datetime - timedelta(days=7)
            if lag_datetime in predictions:
                feature_values.append(predictions[lag_datetime])
            elif lag_datetime in ml_features_train.index:
                feature_values.append(ml_features_train.loc[lag_datetime, 'actual_power'])
            else:
                feature_values.append(np.nan)

        elif feature == 'lag_1_business_day':
            found = False
            for days_back in range(1, 21):
                lag_datetime = target_datetime - timedelta(days=days_back)
                lag_date = lag_datetime.date()

                if lag_datetime in predictions and lag_date in business_days_future:
                    feature_values.append(predictions[lag_datetime])
                    found = True
                    break
                elif lag_datetime in business_days_train.index:
                    feature_values.append(business_days_train.loc[lag_datetime, 'actual_power'])
                    found = True
                    break

            if not found:
                feature_values.append(np.nan)
        else:
            feature_values.append(row[feature])

    return feature_values


def _save_predictions_to_csv(predictions, execution_id):
    """予測結果をCSV保存"""
    energy_env_path = os.getenv('ENERGY_ENV_PATH', '.')
    base_path = Path(energy_env_path) / 'data' / 'predictions'
    base_path.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    timestamp = now.strftime('%Y%m%d_%H%M%S')

    prediction_data = []
    for target_datetime, predicted_value in predictions.items():
        prediction_data.append({
            'execution_id': execution_id,
            'prediction_date': target_datetime.strftime('%Y-%m-%d'),
            'prediction_hour': target_datetime.hour,
            'predicted_power_kwh': round(predicted_value, 2),
            'created_at': now.strftime('%Y-%m-%d %H:%M:%S')
        })

    predictions_df = pd.DataFrame(prediction_data)
    csv_filename = f"predictions_{timestamp}.csv"
    csv_filepath = base_path / csv_filename
    predictions_df.to_csv(csv_filepath, index=False, encoding='utf-8')

    return {
        'success': True,
        'csv_file': str(csv_filepath),
        'timestamp': timestamp
    }


def _save_predictions_to_bigquery(client, predictions, execution_id):
    """予測結果をBigQuery保存"""
    try:
        table_ref = f"{client.project}.prod_energy_data.prediction_results"

        bq_prediction_data = []
        for target_datetime, predicted_value in predictions.items():
            bq_prediction_data.append({
                'execution_id': execution_id,
                'prediction_date': target_datetime.strftime('%Y-%m-%d'),
                'prediction_hour': target_datetime.hour,
                'predicted_power_kwh': round(predicted_value, 2),
                'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })

        bq_predictions_df = pd.DataFrame(bq_prediction_data)

        job = client.load_table_from_dataframe(
            bq_predictions_df,
            table_ref,
            job_config=bigquery.LoadJobConfig(write_disposition="WRITE_APPEND")
        )
        job.result()

        return {
            'success': True,
            'rows_inserted': len(bq_predictions_df)
        }

    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'rows_inserted': 0
        }


def _save_execution_status(client, execution_id, start_time, end_time,
                           duration_seconds, prediction_count, csv_saved, bq_saved):
    """実行ステータスをBigQueryに記録"""
    try:
        table_id = 'energy-env.prod_energy_data.process_execution_log'

        process_status = {
            'execution_id': execution_id,
            'date': datetime.now().strftime('%Y-%m-%d'),
            'process_type': 'ML_PREDICTION',
            'status': 'SUCCESS',
            'error_message': None,
            'started_at': start_time.isoformat(),
            'completed_at': end_time.isoformat(),
            'duration_seconds': duration_seconds,
            'records_processed': prediction_count,
            'file_size_mb': None,
            'additional_info': f"csv_saved={csv_saved}, bq_saved={bq_saved}"
        }

        errors = client.insert_rows_json(table_id, [process_status])

        if errors:
            logger.error(f"ステータスログBQ保存エラー: {errors}")
        else:
            logger.info(f"ステータスログBQ保存成功: execution_id={execution_id}")

    except Exception as e:
        logger.error(f"ステータスログ保存失敗: {e}")


def main():
    """メイン関数 - 日次予測実行"""
    import sys

    print("🚀 日次予測実行開始（今日から16日間）")

    try:
        result = run_daily_prediction()

        if result['status'] == 'success':
            print(f"✅ 予測実行成功: {result['prediction_count']}件")
            print(f"📁 CSV保存: {result['csv_file']}")
            print(f"💾 BigQuery保存: {'成功' if result['bq_saved'] else '失敗'}")
            print("🏁 予測実行完了")
        else:
            print(f"❌ 予測実行失敗: {result.get('error', 'Unknown error')}")
            sys.exit(1)

    except Exception as e:
        print(f"💥 予測実行エラー: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
