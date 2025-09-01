# %%
# ================================================================
# 段階的予測テスト + 予測結果保存機能（Phase 11ダッシュボード用）
# 目的: 実運用での予測値依存による精度劣化測定 + CSV保存
# 期間: 2025-06-01 ～ 2025-06-16 (16日間×24時間=384回予測)
# 新機能: 予測結果をCSV形式で保存（GCSアップロード・Looker Studio用）
# ログ対応: 重要なプロセスをログ出力
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
from logging import getLogger, FileHandler, StreamHandler, Formatter, INFO
import sys
warnings.filterwarnings('ignore')

# ログ設定
def setup_prediction_logging():
    """予測実験用のログ設定"""
    # ログディレクトリ作成
    energy_env_path = os.getenv('ENERGY_ENV_PATH', '.')
    log_dir = Path(energy_env_path) / 'logs' / 'predictions'
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # ログファイル名（タイムスタンプ付き）
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = log_dir / f'prediction_iterative_{timestamp}.log'
    
    # ロガー設定
    logger = getLogger('energy_env.predictions')
    logger.setLevel(INFO)
    
    # 既存ハンドラーをクリア（重複防止）
    logger.handlers.clear()
    
    # フォーマッター
    formatter = Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    # ファイルハンドラー
    file_handler = FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # コンソールハンドラー（重要なメッセージのみ）
    console_handler = StreamHandler(sys.stdout)
    console_handler.setFormatter(Formatter('%(message)s'))
    logger.addHandler(console_handler)
    
    return logger, log_file

# ログ設定実行
logger, log_file_path = setup_prediction_logging()

# 日本語フォント設定
plt.rcParams['font.family'] = 'Meiryo'
plt.rcParams['figure.figsize'] = (12, 8)
plt.rcParams['font.size'] = 10

logger.info("段階的予測実験開始（保存機能付き・dropna()なし）")
logger.info("=" * 60)
logger.info(f"ログファイル: {log_file_path}")
print("段階的予測テスト開始（保存機能付き・dropna()なし）")
print("=" * 60)

# %%
# ================================================================
# 1. データ読み込み・基本確認
# ================================================================

# 環境変数からベースパスを取得
energy_env_path = os.getenv('ENERGY_ENV_PATH', '.')

# ml_features.csvの読み込み
ml_features_path = Path(energy_env_path) / 'data' / 'ml' / 'ml_features.csv'
ml_features = pd.read_csv(ml_features_path)
print(f"データ読み込み完了")
print(f"データ形状: {ml_features.shape}")

# dateとhour列からdatetime列を作成
ml_features['datetime'] = pd.to_datetime(ml_features['date'].astype(str) + ' ' + ml_features['hour'].astype(str).str.zfill(2) + ':00:00')

# calendar_data_with_prev_business.csv読み込み
calendar_data_path = Path(energy_env_path) / 'data' / 'ml' / 'calendar_data_with_prev_business.csv'
calendar_data = pd.read_csv(calendar_data_path)
print(f"営業日カレンダー読み込み完了")

# datetime列をインデックスに設定（高速検索のため）
ml_features = ml_features.set_index('datetime')
calendar_data['date'] = pd.to_datetime(calendar_data['date'])
calendar_data = calendar_data.set_index('date')

print(f"データ準備完了")

# %%
# ================================================================
# 2. Phase 9特徴量定義（12特徴量）
# ================================================================

# Phase 9で使用した12特徴量を定義
features = [
    'hour',                    # 時間（0-23）
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

# 学習データ準備（～2025/5/31まで）
train_end_date = '2025-05-31'
train_data = ml_features[ml_features.index <= train_end_date].copy()

# 特徴量・ターゲット準備（欠損値込み）
X_train = train_data[features]
y_train = train_data['actual_power']

print(f"\nXGBoostモデル学習開始")
print(f"学習データ: {len(X_train):,}件（欠損値込み）")
print(f"学習期間: {train_data.index.min()} ～ {train_data.index.max()}")

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
    予測対象時刻の特徴量を準備（フォールバック完全削除版）
    
    Args:
        target_datetime: 予測対象日時
        predictions: 過去の予測値辞書
        
    Returns:
        list: 12特徴量の値リスト
    """
    # ml_features.csvから該当時刻のデータを取得
    if target_datetime in ml_features.index:
        # 基本的にml_features.csvの値をそのまま使用
        feature_values = ml_features.loc[target_datetime, features].values.copy()
        
        # lag特徴量のみ予測値で上書き（該当する場合のみ）
        for i, feature in enumerate(features):
            if feature == 'lag_1_day':
                lag_datetime = target_datetime - timedelta(days=1)
                if lag_datetime in predictions:
                    feature_values[i] = predictions[lag_datetime]
            
            elif feature == 'lag_7_day':
                lag_datetime = target_datetime - timedelta(days=7)
                if lag_datetime in predictions:
                    feature_values[i] = predictions[lag_datetime]
                    
            elif feature == 'lag_1_business_day':
                # 1営業日前の予測値があれば使用（なければnanのまま）
                for days_back in range(1, 8):  # 最大7日前まで探索
                    lag_datetime = target_datetime - timedelta(days=days_back)
                    if lag_datetime in predictions:
                        # 営業日判定
                        lag_date = lag_datetime.date()
                        if lag_date in calendar_data.index and not calendar_data.loc[lag_date, 'is_holiday'] and lag_datetime.weekday() < 5:
                            feature_values[i] = predictions[lag_datetime]
                            break
        
        return feature_values
    
    else:
        # ml_features.csvにない場合はエラー
        raise ValueError(f"Target datetime {target_datetime} not found in ml_features")

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
        if target_datetime in ml_features.index:
            actual_value = ml_features.loc[target_datetime, 'actual_power']
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

# %%
# ================================================================
# 6. 全期間精度計算・結果分析
# ================================================================

# 全期間の予測値・実績値収集
all_predictions = []
all_actuals = []
prediction_datetimes = []

for dt, pred in predictions.items():
    if dt in ml_features.index:
        all_predictions.append(pred)
        all_actuals.append(ml_features.loc[dt, 'actual_power'])
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
        
        if target_datetime in ml_features.index:
            actual_value = ml_features.loc[target_datetime, 'actual_power']
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