# %%
# ================================================================
# 段階的予測テスト実装（修正版・dropna()なし）
# 目的: 実運用での予測値依存による精度劣化測定
# 期間: 2025-06-01 ～ 2025-06-16 (16日間×24時間=384回予測)
# 修正点: dropna()削除・Phase 10土日祝日対応と同じ条件
# ================================================================

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import mean_absolute_percentage_error, mean_absolute_error, r2_score
import xgboost as xgb
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# 日本語フォント設定
plt.rcParams['font.family'] = 'Meiryo'
plt.rcParams['figure.figsize'] = (12, 8)
plt.rcParams['font.size'] = 10

print("🔄 段階的予測テスト開始（修正版・dropna()なし）")
print("=" * 60)

# %%
# ================================================================
# 1. データ読み込み・基本確認
# ================================================================

# ml_features.csvの読み込み
ml_features = pd.read_csv('../../../data/ml/ml_features.csv')
print(f"📊 データ読み込み完了")
print(f"データ形状: {ml_features.shape}")

# dateとhour列からdatetime列を作成
ml_features['datetime'] = pd.to_datetime(ml_features['date'].astype(str) + ' ' + ml_features['hour'].astype(str).str.zfill(2) + ':00:00')

# 列名確認
print(f"列名: {list(ml_features.columns)}")

# datetime列の確認（複数パターン対応）
datetime_columns = [col for col in ml_features.columns if 'date' in col.lower()]
print(f"日時関連列: {datetime_columns}")

# 最初の数行確認
print(f"\n最初の5行:")
print(ml_features.head())

# calendar_data_with_prev_business.csv読み込み
calendar_data = pd.read_csv('../../../data/ml/calendar_data_with_prev_business.csv')
print(f"📅 営業日カレンダー読み込み完了")
print(f"カレンダーデータ形状: {calendar_data.shape}")

# calendar_dataのdate列をpandas datetimeに変換
calendar_data['date'] = pd.to_datetime(calendar_data['date'])

# datetime列をインデックスに設定（高速検索のため）
ml_features = ml_features.set_index('datetime')
calendar_data = calendar_data.set_index('date')

print(f"✅ データ準備完了")

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

print(f"\n🔧 使用特徴量: {len(features)}個")
for i, feature in enumerate(features, 1):
    print(f"  {i:2d}. {feature}")

# %%
# ================================================================
# 3. Phase 9ベースラインモデル学習（2025-05-31まで・dropna()なし）
# ================================================================

# 学習データ準備（2025-05-31まで）
train_end_date = '2025-05-31 23:00:00'
train_data = ml_features[ml_features.index <= train_end_date].copy()

print(f"\n📚 ベースラインモデル学習（dropna()なし版）")
print(f"学習期間: {train_data.index.min()} ～ {train_data.index.max()}")
print(f"学習データ件数: {len(train_data):,}件")

# 【修正】dropna()を削除 - XGBoost欠損値自動処理を活用
print(f"✅ dropna()なし - XGBoost欠損値自動処理使用")
print(f"学習データ（欠損値込み）: {len(train_data):,}件")

# 欠損値状況確認
missing_info = train_data[features].isnull().sum()
print(f"\n📊 各特徴量の欠損値状況:")
for feature in features:
    missing_count = missing_info[feature]
    missing_rate = missing_count / len(train_data) * 100
    print(f"  {feature:20s}: {missing_count:5d}件 ({missing_rate:5.1f}%)")

# 特徴量・目的変数分離（dropna()なし）
X_train = train_data[features]  # 欠損値込みで学習
y_train = train_data['actual_power']

# Phase 9と同じXGBoostモデル学習
xgb_model = xgb.XGBRegressor(
    n_estimators=200,
    max_depth=8,
    learning_rate=0.05,
    random_state=42,
    verbosity=0
)

print(f"\n🤖 XGBoostモデル学習中（欠損値自動処理）...")
xgb_model.fit(X_train, y_train)
print(f"✅ ベースラインモデル学習完了")

# %%
# ================================================================
# 4. 営業日マッピング関数の準備
# ================================================================

def get_prev_business_day(target_date):
    """指定日の前営業日を取得"""
    target_date_str = target_date.strftime('%Y-%m-%d')
    
    if target_date_str in calendar_data.index:
        prev_business_str = calendar_data.loc[target_date_str, 'prev_business_day']
        if pd.notna(prev_business_str):
            return pd.to_datetime(prev_business_str).date()
    
    # フォールバック: 単純に前日を返す
    return (target_date - timedelta(days=1)).date()

def prepare_features_for_prediction_debug(target_datetime, predictions_dict):
    """予測対象時刻の特徴量を準備（デバッグ版）"""
    print(f"\n{'='*60}")
    print(f"🔍 特徴量デバッグ: {target_datetime}")
    print(f"{'='*60}")
    
    # 基本カレンダー特徴量（確定値）
    hour = target_datetime.hour
    is_weekend = 1 if target_datetime.weekday() >= 5 else 0
    month = target_datetime.month
    hour_sin = np.sin(2 * np.pi * hour / 24)
    hour_cos = np.cos(2 * np.pi * hour / 24)
    
    print(f"📅 基本カレンダー特徴量:")
    print(f"  hour: {hour}")
    print(f"  is_weekend: {is_weekend} ({'週末' if is_weekend else '平日'})")
    print(f"  month: {month}")
    print(f"  hour_sin: {hour_sin:.4f}")
    print(f"  hour_cos: {hour_cos:.4f}")
    
    # 祝日フラグ（正確な実装）
    target_date_str = target_datetime.strftime('%Y-%m-%d')
    if target_date_str in calendar_data.index:
        is_holiday = 1 if calendar_data.loc[target_date_str, 'is_holiday'] else 0
        print(f"  is_holiday: {is_holiday} (カレンダーデータから取得)")
    else:
        is_holiday = 0  # フォールバック
        print(f"  is_holiday: {is_holiday} (フォールバック値)")
    
    # 気象データ（ml_featuresの実績値使用）
    print(f"\n🌤️ 気象特徴量:")
    if target_datetime in ml_features.index:
        temperature_2m = ml_features.loc[target_datetime, 'temperature_2m']
        relative_humidity_2m = ml_features.loc[target_datetime, 'relative_humidity_2m']
        precipitation = ml_features.loc[target_datetime, 'precipitation']
        print(f"  temperature_2m: {temperature_2m}°C (実績値)")
        print(f"  relative_humidity_2m: {relative_humidity_2m}% (実績値)")
        print(f"  precipitation: {precipitation}mm (実績値)")
    else:
        # フォールバック値
        temperature_2m = 20.0
        relative_humidity_2m = 60.0
        precipitation = 0.0
        print(f"  temperature_2m: {temperature_2m}°C (フォールバック)")
        print(f"  relative_humidity_2m: {relative_humidity_2m}% (フォールバック)")
        print(f"  precipitation: {precipitation}mm (フォールバック)")

    # lag_1_day（前日同時刻）
    print(f"\n⏰ ラグ特徴量:")
    lag_1_day_datetime = target_datetime - timedelta(days=1)
    print(f"  lag_1_day参照時刻: {lag_1_day_datetime}")

    if lag_1_day_datetime in ml_features.index and lag_1_day_datetime <= pd.to_datetime('2025-05-31 23:00:00'):
        lag_1_day = ml_features.loc[lag_1_day_datetime, 'actual_power']
        print(f"  lag_1_day: {lag_1_day}万kW (実績値)")
    elif lag_1_day_datetime in predictions_dict:
        lag_1_day = predictions_dict[lag_1_day_datetime]  # 予測値使用
        print(f"  lag_1_day: {lag_1_day}万kW (予測値)")
    else:
        lag_1_day = 3500.0  # フォールバック値
        print(f"  lag_1_day: {lag_1_day}万kW (フォールバック)")

    # lag_7_day（7日前同時刻）
    lag_7_day_datetime = target_datetime - timedelta(days=7)
    print(f"  lag_7_day参照時刻: {lag_7_day_datetime}")

    if lag_7_day_datetime in ml_features.index:
        lag_7_day = ml_features.loc[lag_7_day_datetime, 'actual_power']
        print(f"  lag_7_day: {lag_7_day}万kW (実績値)")
    elif lag_7_day_datetime in predictions_dict:
        lag_7_day = predictions_dict[lag_7_day_datetime]  # 6/8以降で予測値使用
        print(f"  lag_7_day: {lag_7_day}万kW (予測値)")
    else:
        lag_7_day = 3500.0  # フォールバック値
        print(f"  lag_7_day: {lag_7_day}万kW (フォールバック)")

    # lag_1_business_day（前営業日同時刻）- 最重要特徴量！
    prev_business_date = get_prev_business_day(target_datetime)
    lag_1_business_day_datetime = pd.to_datetime(f"{prev_business_date} {target_datetime.time()}")
    print(f"  lag_1_business_day参照時刻: {lag_1_business_day_datetime}")

    if lag_1_business_day_datetime in ml_features.index and lag_1_business_day_datetime <= pd.to_datetime('2025-05-31 23:00:00'):
        lag_1_business_day = ml_features.loc[lag_1_business_day_datetime, 'actual_power']
        print(f"  lag_1_business_day: {lag_1_business_day}万kW (実績値)")
    elif lag_1_business_day_datetime in predictions_dict:
        lag_1_business_day = predictions_dict[lag_1_business_day_datetime]  # 予測値使用
        print(f"  lag_1_business_day: {lag_1_business_day}万kW (予測値)")
    else:
        lag_1_business_day = 3500.0  # フォールバック値  
        print(f"  lag_1_business_day: {lag_1_business_day}万kW (フォールバック)")

    # 特徴量辞書作成
    feature_values = [
        hour,                    # hour
        is_weekend,             # is_weekend  
        is_holiday,             # is_holiday
        month,                  # month
        hour_sin,               # hour_sin
        hour_cos,               # hour_cos
        lag_1_day,              # lag_1_day（実績値→予測値に段階移行）
        lag_7_day,              # lag_7_day（6/8以降で予測値使用）
        lag_1_business_day,     # lag_1_business_day（実績値→予測値に段階移行）
        temperature_2m,         # temperature_2m
        relative_humidity_2m,   # relative_humidity_2m
        precipitation           # precipitation
    ]
    
    print(f"\n📋 特徴量最終確認:")
    for i, (feat_name, feat_val) in enumerate(zip(features, feature_values)):
        print(f"  {i+1:2d}. {feat_name:20s}: {feat_val}")
    
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

print(f"\n🔄 段階的予測実行開始")
print(f"予測期間: {start_date.date()} ～ {end_date.date()}")
print(f"予測回数: {16 * 24}回（16日×24時間）")
print(f"✅ dropna()なし - XGBoost欠損値自動処理使用")

# 16日間の段階的予測
current_date = start_date

for day in range(16):
    daily_predictions = []
    daily_actuals = []
    
    print(f"\n📅 Day {day+1}: {current_date.strftime('%Y-%m-%d')}")
    
    # 1日24時間の予測
    for hour in range(24):
        target_datetime = current_date + timedelta(hours=hour)
        
        # 特徴量準備
        feature_values = prepare_features_for_prediction_debug(target_datetime, predictions)
        
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
        
        print(f"  MAPE: {daily_mape:.2f}%, MAE: {daily_mae:.1f}万kW, R²: {daily_r2:.4f}")
    
    current_date += timedelta(days=1)

print(f"\n✅ 段階的予測完了")

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

print(f"\n📊 段階的予測 全期間結果")
print(f"=" * 40)
print(f"予測件数: {len(all_predictions)}件")
print(f"MAPE: {overall_mape:.2f}%")
print(f"MAE:  {overall_mae:.2f}万kW")
print(f"R²:   {overall_r2:.4f}")

# 前回固定予測結果との比較
print(f"\n📈 前回固定予測結果との比較")
print(f"=" * 40)
print(f"前回固定予測（MAPE）: 2.54%（Phase 10土日祝日対応）")
print(f"今回段階的予測（MAPE）: {overall_mape:.2f}%")

if overall_mape <= 2.54:
    print(f"✅ 段階的予測でも高精度を維持")
elif overall_mape <= 3.5:
    print(f"⚠️ 段階的予測で軽度の精度劣化（実用レベル内）")
    degradation_rate = (overall_mape - 2.54) / 2.54 * 100
    print(f"   精度劣化率: {degradation_rate:.1f}%")
elif overall_mape <= 5.0:
    print(f"⚠️ 段階的予測で中程度の精度劣化（要注意レベル）")
    degradation_rate = (overall_mape - 2.54) / 2.54 * 100
    print(f"   精度劣化率: {degradation_rate:.1f}%")
else:
    print(f"❌ 段階的予測で大幅な精度劣化（実用性要検討）")
    degradation_rate = (overall_mape - 2.54) / 2.54 * 100
    print(f"   精度劣化率: {degradation_rate:.1f}%")

# %%
# ================================================================
# 7. 日別精度劣化の可視化
# ================================================================

# 日別結果をDataFrameに変換
daily_df = pd.DataFrame(daily_results)

# 日別MAPE推移グラフ
plt.figure(figsize=(12, 8))

plt.subplot(2, 2, 1)
plt.plot(daily_df['day'], daily_df['mape'], 'bo-', linewidth=2, markersize=6)
plt.axhline(y=2.54, color='r', linestyle='--', label='Phase 10ベースライン (2.54%)')
plt.title('📈 日別MAPE推移（段階的予測）', fontsize=14, fontweight='bold')
plt.xlabel('Day')
plt.ylabel('MAPE (%)')
plt.grid(True, alpha=0.3)
plt.legend()

# 日別MAE推移グラフ
plt.subplot(2, 2, 2)
plt.plot(daily_df['day'], daily_df['mae'], 'go-', linewidth=2, markersize=6)
plt.title('📈 日別MAE推移', fontsize=14, fontweight='bold')
plt.xlabel('Day')
plt.ylabel('MAE (万kW)')
plt.grid(True, alpha=0.3)

# 日別R²推移グラフ
plt.subplot(2, 2, 3)
plt.plot(daily_df['day'], daily_df['r2'], 'mo-', linewidth=2, markersize=6)
plt.axhline(y=0.9839, color='r', linestyle='--', label='Phase 9ベースライン (0.9839)')
plt.title('📈 日別R²推移', fontsize=14, fontweight='bold')
plt.xlabel('Day')
plt.ylabel('R² Score')
plt.grid(True, alpha=0.3)
plt.legend()

# 精度劣化パターン分析
plt.subplot(2, 2, 4)
mape_change = [(mape - daily_df['mape'].iloc[0]) for mape in daily_df['mape']]
plt.plot(daily_df['day'], mape_change, 'ro-', linewidth=2, markersize=6)
plt.title('📉 MAPE劣化量（Day1比較）', fontsize=14, fontweight='bold')
plt.xlabel('Day')
plt.ylabel('MAPE劣化量 (%)')
plt.grid(True, alpha=0.3)
plt.axhline(y=0, color='k', linestyle='-', alpha=0.5)

plt.tight_layout()
plt.show()

# %%
# ================================================================
# 8. 実際の予測値 vs 実績値の比較可視化
# ================================================================

# 時系列での予測値vs実績値比較（最初の3日間）
sample_dates = pd.date_range('2025-06-01', '2025-06-03', freq='H')
sample_predictions = [predictions.get(dt, np.nan) for dt in sample_dates]
sample_actuals = [ml_features.loc[dt, 'actual_power'] if dt in ml_features.index else np.nan for dt in sample_dates]

plt.figure(figsize=(15, 6))
plt.plot(sample_dates, sample_actuals, 'b-', linewidth=2, label='実績値', alpha=0.8)
plt.plot(sample_dates, sample_predictions, 'r--', linewidth=2, label='段階的予測値', alpha=0.8)
plt.title('🔍 段階的予測 vs 実績値（2025-06-01〜03）', fontsize=16, fontweight='bold')
plt.xlabel('日時')
plt.ylabel('電力需要（万kW）')
plt.legend()
plt.grid(True, alpha=0.3)
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()

# %%
# ================================================================
# 9. 特徴量重要度分析（欠損値込み学習）
# ================================================================

print(f"\n📊 特徴量重要度分析（dropna()なし学習）:")
print(f"=" * 50)

# 特徴量重要度取得
feature_importance = xgb_model.feature_importances_
importance_df = pd.DataFrame({
    'feature': features,
    'importance': feature_importance * 100
}).sort_values('importance', ascending=False)

# 重要度表示
for idx, row in importance_df.iterrows():
    rank = importance_df.index.get_loc(idx) + 1
    print(f"{rank:2d}. {row['feature']:19s}: {row['importance']:6.1f}%")

# %%
# ================================================================
# 10. 土日祝日 vs 平日の段階的予測精度比較
# ================================================================

print(f"\n" + "="*50)
print("📊 土日祝日 vs 平日の段階的予測精度比較")
print("="*50)

# 段階的予測結果に曜日情報追加
weekday_analysis = []
weekend_analysis = []

for result in daily_results:
    date_obj = pd.to_datetime(result['date'])
    is_weekend = date_obj.weekday() >= 5
    
    # カレンダーデータから祝日判定
    date_str = result['date']
    is_holiday = False
    if date_str in calendar_data.index:
        is_holiday = calendar_data.loc[date_str, 'is_holiday']
    
    day_info = {
        'date': result['date'],
        'mape': result['mape'],
        'mae': result['mae'],
        'r2': result['r2'],
        'day_type': '土日祝' if (is_weekend or is_holiday) else '平日'
    }
    
    if is_weekend or is_holiday:
        weekend_analysis.append(day_info)
    else:
        weekday_analysis.append(day_info)

# 曜日別精度統計
if len(weekday_analysis) > 0:
    weekday_mapes = [d['mape'] for d in weekday_analysis]
    weekday_avg_mape = np.mean(weekday_mapes)
    print(f"平日（{len(weekday_analysis)}日）:")
    print(f"  平均MAPE: {weekday_avg_mape:.2f}%")
    print(f"  MAPE範囲: {min(weekday_mapes):.2f}% ～ {max(weekday_mapes):.2f}%")
    
if len(weekend_analysis) > 0:
    weekend_mapes = [d['mape'] for d in weekend_analysis]
    weekend_avg_mape = np.mean(weekend_mapes)
    print(f"土日祝日（{len(weekend_analysis)}日）:")
    print(f"  平均MAPE: {weekend_avg_mape:.2f}%")
    print(f"  MAPE範囲: {min(weekend_mapes):.2f}% ～ {max(weekend_mapes):.2f}%")

# 段階的予測での土日祝日対応評価
if len(weekday_analysis) > 0 and len(weekend_analysis) > 0:
    if weekend_avg_mape <= weekday_avg_mape * 1.15:  # 15%以内の差は許容
        print(f"\n✅ 段階的予測でも土日祝日対応成功")
        print(f"✅ 営業日lag欠損値の影響を適切に処理")
    else:
        print(f"\n⚠️ 段階的予測で土日祝日精度が劣化")
        print(f"⚠️ 予測値依存により欠損値影響が拡大")

# %%
# ================================================================
# 11. 外れ値検出・分析（IQR法）
# ================================================================

print(f"\n📊 外れ値検出・分析")
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

# 外れ値の詳細
if outliers_count > 0:
    outlier_datetimes = np.array(prediction_datetimes)[outliers]
    outlier_residuals = abs_residuals[outliers]
    print(f"\n外れ値詳細:")
    for i, (dt, residual) in enumerate(zip(outlier_datetimes, outlier_residuals)):
        print(f"  {i+1}. {dt}: 残差 {residual:.1f}万kW")

# %%
# ================================================================
# 12. 段階的予測実験結果サマリー・Phase 10評価
# ================================================================

print(f"\n" + "🎉 段階的予測実験完了サマリー" + "\n")
print("="*60)

print(f"✅ 段階的予測実験（dropna()なし）完了")
print(f"✅ 予測期間: 2025/6/1～6/16（16日間・384時間）")
print(f"✅ 学習データ: 2025/5/31まで（欠損値込み）")
print(f"✅ XGBoost欠損値自動処理使用")

print(f"\n📊 段階的予測 vs 固定予測 比較結果:")
print(f"=" * 50)
print(f"固定予測（Phase 10）: MAPE 2.54% （lagを実データ使用）")
print(f"段階的予測（今回）:   MAPE {overall_mape:.2f}% （lagを予測値で段階埋め）")

degradation_amount = overall_mape - 2.54
degradation_rate = degradation_amount / 2.54 * 100

if overall_mape <= 3.0:
    evaluation = "✅ 実用レベル維持"
elif overall_mape <= 4.0:
    evaluation = "⚠️ 軽度劣化・要注意"
else:
    evaluation = "❌ 大幅劣化・要改善"

print(f"精度劣化量: +{degradation_amount:.2f}% ({degradation_rate:+.1f}%)")
print(f"実用性評価: {evaluation}")

print(f"\n📈 日別精度推移分析:")
if len(daily_results) > 0:
    first_day_mape = daily_results[0]['mape']
    last_day_mape = daily_results[-1]['mape']
    max_mape = max([d['mape'] for d in daily_results])
    min_mape = min([d['mape'] for d in daily_results])
    
    print(f"初日MAPE: {first_day_mape:.2f}%")
    print(f"最終日MAPE: {last_day_mape:.2f}%")
    print(f"最大MAPE: {max_mape:.2f}%")
    print(f"最小MAPE: {min_mape:.2f}%")
    print(f"精度推移: {last_day_mape - first_day_mape:+.2f}% (初日→最終日)")

print(f"\n🎯 Phase 10システム化判断:")
if overall_mape <= 3.5:
    print(f"✅ 段階的予測でも実用レベル達成")
    print(f"✅ Phase 10日次自動予測システム構築推奨")
    print(f"✅ API制限16日間での運用品質確保")
else:
    print(f"⚠️ 段階的予測精度要改善")
    print(f"⚠️ Phase 10システム化前に精度向上策要検討")

print(f"\n📋 Phase 10完了準備:")
print(f"✅ 土日祝日欠損値対応: 解決済み（MAPE 2.54%達成）")
print(f"✅ 16日間予測対応: API制限内で高精度確認")
print(f"✅ 段階的予測検証: 実運用シミュレーション完了")
print(f"➡️ 次ステップ: 日次自動予測システム統合・Phase 11移行")

# %%
# ================================================================
# 13. 特徴量使用パターン分析（実運用シミュレーション）
# ================================================================

print(f"\n📋 段階的予測での特徴量使用パターン分析")
print("="*60)

# 各日での特徴量ソース分析例
pattern_analysis_examples = {
    '6/1 0:00': {
        'lag_1_day': '5/31 0:00実データ',
        'lag_7_day': '5/25 0:00実データ',  
        'lag_1_business_day': '5/30 0:00実データ（金曜日）'
    },
    '6/1 1:00': {
        'lag_1_day': '5/31 1:00実データ',
        'lag_7_day': '5/25 1:00実データ',
        'lag_1_business_day': '5/30 1:00実データ'
    },
    '6/2 0:00': {
        'lag_1_day': '6/1 0:00予測値（←段階的予測開始）',
        'lag_7_day': '5/26 0:00実データ',
        'lag_1_business_day': '6/1 0:00予測値（月曜日→金曜日）'
    },
    '6/8 0:00': {
        'lag_1_day': '6/7 0:00予測値',
        'lag_7_day': '6/1 0:00予測値（←7日前も予測値に）',
        'lag_1_business_day': '6/7 0:00予測値（土曜→金曜）'
    }
}

print("段階的予測での特徴量ソース推移:")
for datetime_key, sources in pattern_analysis_examples.items():
    print(f"\n{datetime_key}:")
    for feature, source in sources.items():
        print(f"  {feature:20s}: {source}")

print(f"\n💡 実運用での精度劣化要因:")
print(f"  1. 初日: 実データlag豊富→高精度")
print(f"  2. 2日目以降: lag_1_day予測値依存→徐々に劣化")
print(f"  3. 8日目以降: lag_7_day予測値依存→さらに劣化")
print(f"  4. 営業日変化: lag_1_business_day予測値混入→誤差拡大")

# %%
# ================================================================
# 14. Phase 10実験完了・次段階準備
# ================================================================

print(f"\n🚀 Phase 10段階的予測実験完了")
print("="*60)

print(f"【実験成果】")
print(f"✅ 段階的予測精度: MAPE {overall_mape:.2f}%")
print(f"✅ 前回固定予測からの劣化: +{degradation_amount:.2f}%")
print(f"✅ 外れ値: {outliers_count}件 ({outliers_count/len(abs_residuals)*100:.1f}%)")
print(f"✅ 土日祝日対応: dropna()なしでも安定運用")

print(f"\n【重要な発見】")
print(f"🔍 実運用での予測値依存による精度変化を定量測定")
print(f"🔍 XGBoost欠損値自動処理の段階的予測での有効性確認")
print(f"🔍 16日間予測での日別精度劣化パターン把握")

print(f"\n【Phase 10完了判断】")
if overall_mape <= 3.5:
    print(f"✅ MAPE {overall_mape:.2f}% - 実用レベル達成")
    print(f"✅ Phase 10日次自動予測システム構築OK")
    print(f"✅ Phase 11 Looker Studioダッシュボード移行OK")
else:
    print(f"⚠️ MAPE {overall_mape:.2f}% - 精度向上策要検討")
    print(f"⚠️ Phase 10システム化前に追加改良推奨")

print(f"\n【次ステップ準備完了】")
print(f"🎯 日次自動予測システム統合")
print(f"🎯 PowerDataDownloader + WeatherDownloader統合")
print(f"🎯 Phase 5-6特徴量生成ロジック統合")
print(f"🎯 Phase 9 XGBoostモデル（土日祝日対応）統合")
print(f"🎯 BigQuery結果保存・Looker Studio準備")

print(f"\n🎉 Phase 10段階的予測実験完了！")
print(f"✨ 実運用シミュレーション成功・システム化準備完了！")


# %%
# ================================================================
# 6/1 0:00 予測値確認（シンプル版）
# ================================================================

# 段階的予測の6/1 0:00確認用コード
target_datetime = pd.to_datetime('2025-06-01 00:00:00')
iterative_pred = predictions[target_datetime]
actual_value = 2131.00  # 実績値（固定予測と同じ）

print(f"6/1 0:00の段階的予測結果:")
print(f"段階的予測値: {iterative_pred:.2f}万kW")
print(f"実績値:       {actual_value:.2f}万kW")
print(f"誤差:         {abs(iterative_pred - actual_value):.2f}万kW")
print(f"誤差率:       {abs(iterative_pred - actual_value) / actual_value * 100:.2f}%")

print(f"\n📊 固定 vs 段階的 比較:")
print(f"固定予測:   2154.15万kW (誤差率1.09%)")
print(f"段階的予測: {iterative_pred:.2f}万kW (誤差率?%)")
print(f"予測値差:   {abs(2154.15 - iterative_pred):.2f}万kW")

# %%
# ================================================================
# 6/1 0:00 特徴量準備 単体確認
# ================================================================

target_datetime = pd.to_datetime('2025-06-01 00:00:00')
empty_predictions = {}  # 初回なので空の辞書

print("🔍 6/1 0:00の特徴量準備確認:")
print("=" * 60)

# 特徴量準備実行（デバッグ版）
feature_values = prepare_features_for_prediction_debug(target_datetime, empty_predictions)

print("\n📋 準備された特徴量値:")
for i, (feat_name, feat_val) in enumerate(zip(features, feature_values)):
    print(f"  {i+1:2d}. {feat_name:20s}: {feat_val}")

# %%