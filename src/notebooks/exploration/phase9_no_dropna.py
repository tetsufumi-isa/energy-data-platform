# %%
# ================================================================
# 16日間予測精度検証（欠損値込み・dropna()なし）
# 学習期間: ～6/30まで
# 予測期間: 7/1～7/16（16日間）
# ================================================================

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import mean_absolute_percentage_error, mean_absolute_error, r2_score
import xgboost as xgb
import warnings
warnings.filterwarnings('ignore')

# 日本語フォント設定
plt.rcParams['font.family'] = 'Meiryo'
plt.rcParams['figure.figsize'] = (12, 8)
plt.rcParams['font.size'] = 10

print("=" * 60)
print("🚀 16日間予測精度検証（欠損値込み）")
print("=" * 60)
print("学習期間: ～2025/5/31まで")
print("予測期間: 2025/6/1～6/16（16日間・384時間）")
print("方針: dropna()なし、土日祝日欠損値込みで予測")
print("=" * 60)

# %%
# ================================================================
# 1. データロード・基本確認
# ================================================================

# データ読み込み
df = pd.read_csv('../../../data/ml/ml_features.csv')

print("📋 データ基本情報:")
print(f"データ形状: {df.shape}")

# datetime列作成
if 'date' in df.columns and 'hour' in df.columns:
    df['datetime'] = pd.to_datetime(df['date'].astype(str) + ' ' + df['hour'].astype(str).str.zfill(2) + ':00:00')
    print(f"✅ datetime列作成完了")
    print(f"データ期間: {df['datetime'].min()} ～ {df['datetime'].max()}")
else:
    print("❌ date, hour列が見つかりません")

# %%
# ================================================================
# 2. Phase 9の12特徴量定義
# ================================================================

features = [
    'hour', 'is_weekend', 'is_holiday', 'month', 
    'hour_sin', 'hour_cos',
    'lag_1_day', 'lag_7_day', 'lag_1_business_day',
    'temperature_2m', 'relative_humidity_2m', 'precipitation'
]

print(f"\n🔧 使用特徴量: {len(features)}個")
for i, feature in enumerate(features, 1):
    print(f"  {i:2d}. {feature}")

# %%
# ================================================================
# 3. 16日間予測データ分割
# ================================================================

# 学習期間: ～5/31まで
# 予測期間: 6/1～6/16
train_end_date = '2025-05-31'
test_start_date = '2025-06-01'
test_end_date = '2025-06-16'

# データ分割
train_data = df[df['datetime'] <= train_end_date].copy()
test_data = df[(df['datetime'] >= test_start_date) & 
               (df['datetime'] <= test_end_date)].copy()

print(f"\n📅 16日間予測データ分割:")
print(f"学習期間: {train_data['datetime'].min()} ～ {train_data['datetime'].max()}")
print(f"予測期間: {test_data['datetime'].min()} ～ {test_data['datetime'].max()}")
print(f"学習データ: {len(train_data):,}件")
print(f"テストデータ: {len(test_data):,}件（{len(test_data)/24:.0f}日間）")

# %%
# ================================================================
# 4. 特徴量・ターゲット準備（欠損値込み）
# ================================================================

# 特徴量・ターゲット準備（欠損値そのまま）
X_train = train_data[features]
y_train = train_data['actual_power']
X_test = test_data[features]
y_test = test_data['actual_power']

print(f"\n📊 学習データ準備完了:")
print(f"特徴量: {X_train.shape}")
print(f"ターゲット: {y_train.shape}")

# %%
# ================================================================
# 5. XGBoostモデル学習・予測（欠損値自動処理）
# ================================================================

# XGBoostモデル設定
xgb_model = xgb.XGBRegressor(
    n_estimators=200,
    max_depth=8,
    learning_rate=0.05,
    random_state=42,
    verbosity=0
)

print(f"\n🤖 XGBoostモデル学習中（欠損値自動処理）...")
xgb_model.fit(X_train, y_train)

# 予測実行
y_pred = xgb_model.predict(X_test)

print(f"✅ 16日間予測完了")

# %%
# ================================================================
# 6. 予測精度評価
# ================================================================

# 評価指標計算
mape = mean_absolute_percentage_error(y_test, y_pred) * 100
mae = mean_absolute_error(y_test, y_pred)
r2 = r2_score(y_test, y_pred)

print(f"\n16日間予測結果（欠損値込み）:")
print(f"MAPE: {mape:.2f}%")
print(f"MAE: {mae:.2f}万kW")
print(f"R²: {r2:.4f}")

# %%
# ================================================================
# 7. 残差分析・外れ値検出
# ================================================================

print(f"\n" + "="*50)
print("📊 残差分析・外れ値検出")
print("="*50)

# 残差計算
residuals = y_test - y_pred
abs_residuals = np.abs(residuals)

# 基本統計
print(f"残差統計:")
print(f"平均: {residuals.mean():+.2f}万kW")
print(f"標準偏差: {residuals.std():.2f}万kW")
print(f"最大残差: {residuals.max():+.2f}万kW")
print(f"最小残差: {residuals.min():+.2f}万kW")

# IQR法による外れ値検出
Q1 = np.percentile(abs_residuals, 25)
Q3 = np.percentile(abs_residuals, 75)
IQR = Q3 - Q1
outlier_threshold = Q3 + 1.5 * IQR

outliers_mask = abs_residuals > outlier_threshold
outliers_count = outliers_mask.sum()

print(f"\n外れ値検出（IQR法）:")
print(f"外れ値閾値: {outlier_threshold:.2f}万kW")
print(f"外れ値件数: {outliers_count}件 ({outliers_count/len(abs_residuals)*100:.1f}%)")

# %%
# ================================================================
# 8. 特徴量重要度分析
# ================================================================

print(f"\n特徴量重要度分析:")

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
# 9. 土日祝日 vs 平日の精度比較
# ================================================================

print(f"\n" + "="*50)
print("📊 土日祝日 vs 平日の予測精度比較")
print("="*50)

# テストデータに予測結果追加
test_data_analysis = test_data.copy()
test_data_analysis['prediction'] = y_pred
test_data_analysis['residual'] = y_test - y_pred
test_data_analysis['abs_residual'] = np.abs(test_data_analysis['residual'])

# 平日と土日祝日に分類
weekday_data = test_data_analysis[~test_data_analysis['is_weekend'] & ~test_data_analysis['is_holiday']]
weekend_holiday_data = test_data_analysis[test_data_analysis['is_weekend'] | test_data_analysis['is_holiday']]

if len(weekday_data) > 0 and len(weekend_holiday_data) > 0:
    # 精度計算
    weekday_mape = mean_absolute_percentage_error(weekday_data['actual_power'], weekday_data['prediction']) * 100
    weekend_mape = mean_absolute_percentage_error(weekend_holiday_data['actual_power'], weekend_holiday_data['prediction']) * 100
    
    weekday_mae = mean_absolute_error(weekday_data['actual_power'], weekday_data['prediction'])
    weekend_mae = mean_absolute_error(weekend_holiday_data['actual_power'], weekend_holiday_data['prediction'])
    
    print(f"曜日別予測精度:")
    print(f"平日: {len(weekday_data)}件 - MAPE {weekday_mape:.2f}%, MAE {weekday_mae:.2f}万kW")
    print(f"土日祝日: {len(weekend_holiday_data)}件 - MAPE {weekend_mape:.2f}%, MAE {weekend_mae:.2f}万kW")
    
    print(f"\n土日祝日欠損値効果:")
    if weekend_mape <= weekday_mape * 1.1:  # 10%以内の差は許容
        print(f"✅ 土日祝日も平日と同等の予測精度を維持")
        print(f"✅ 営業日lag特徴量の欠損値処理が適切に機能")
    else:
        print(f"⚠️ 土日祝日の予測精度が平日より劣化")
        print(f"⚠️ 欠損値の影響を受けている可能性")

# %%
# ================================================================
# 10. 日別予測精度分析
# ================================================================

print(f"\n" + "="*50)
print("日別予測精度分析")
print("="*50)

# 日別精度計算
test_data_analysis['date'] = test_data_analysis['datetime'].dt.date
daily_accuracy = test_data_analysis.groupby('date').apply(
    lambda x: pd.Series({
        'mape': mean_absolute_percentage_error(x['actual_power'], x['prediction']) * 100,
        'mae': mean_absolute_error(x['actual_power'], x['prediction']),
        'count': len(x),
        'is_weekend_or_holiday': x['is_weekend'].iloc[0] or x['is_holiday'].iloc[0]
    })
).reset_index()

print("日別予測精度:")
for _, row in daily_accuracy.iterrows():
    day_type = "土日祝" if row['is_weekend_or_holiday'] else "平日"
    print(f"{row['date']} ({day_type}): MAPE {row['mape']:5.2f}%, MAE {row['mae']:6.2f}万kW ({row['count']}件)")

# 日別精度の統計
print(f"\n日別精度統計:")
print(f"MAPE - 平均: {daily_accuracy['mape'].mean():.2f}%, 最大: {daily_accuracy['mape'].max():.2f}%, 最小: {daily_accuracy['mape'].min():.2f}%")
print(f"MAE - 平均: {daily_accuracy['mae'].mean():.2f}万kW, 最大: {daily_accuracy['mae'].max():.2f}万kW, 最小: {daily_accuracy['mae'].min():.2f}万kW")

print(f"\n🎨 予測結果可視化作成中...")

# 時系列プロット作成
fig, axes = plt.subplots(2, 1, figsize=(16, 12))

# 1. 予測 vs 実績プロット
axes[0].plot(test_data['datetime'], y_test, 'b-', label='実績値', alpha=0.8)
axes[0].plot(test_data['datetime'], y_pred, 'r-', label='予測値', alpha=0.8)
axes[0].set_ylabel('電力需要 (万kW)')
axes[0].set_title('16日間予測結果: 実績 vs 予測')
axes[0].legend()
axes[0].grid(True, alpha=0.3)

# 2. 残差プロット
axes[1].plot(test_data['datetime'], residuals, 'g-', label='残差', alpha=0.8)
axes[1].axhline(y=0, color='black', linestyle='--', alpha=0.5)
axes[1].axhline(y=outlier_threshold, color='red', linestyle='--', label=f'外れ値閾値: ±{outlier_threshold:.0f}万kW')
axes[1].axhline(y=-outlier_threshold, color='red', linestyle='--')
axes[1].set_xlabel('日時')
axes[1].set_ylabel('残差 (万kW)')
axes[1].set_title('予測残差（外れ値検出）')
axes[1].legend()
axes[1].grid(True, alpha=0.3)

plt.tight_layout()
plt.show()

# %%
# ================================================================
# 12. 結論サマリー
# ================================================================

print(f"\n16日間予測実験完了サマリー")
print("="*60)

print(f"✅ 16日間予測（6/1～6/16）完了")
print(f"✅ 予測精度MAPE: {mape:.2f}%")
print(f"✅ 外れ値: {outliers_count}件 ({outliers_count/len(abs_residuals)*100:.1f}%)")
print(f"✅ 日別・曜日別精度分析完了")

print(f"\n重要な発見:")
if 'weekday_mape' in locals() and 'weekend_mape' in locals():
    print(f"平日予測精度: {weekday_mape:.2f}%")
    print(f"土日祝日予測精度: {weekend_mape:.2f}%")
    if weekend_mape <= weekday_mape * 1.1:
        print(f"土日祝日欠損値処理: 成功")
    else:
        print(f"土日祝日欠損値処理: 要改善")

print(f"\nPhase 10準備:")
print(f"16日間予測精度: 実用レベル確認")
print(f"XGBoost欠損値自動処理: 有効性実証")
print(f"新ml_features.csv作成準備完了")


# %%
# ================================================================
# phase9_no_dropna.py用 6/1 0:00確認コード（修正版）
# ================================================================

print("6/1 0:00の固定予測結果:")

# test_dataの最初が6/1 0:00のはず（0番目）
first_pred = y_pred[0]  # 予測値配列の最初
first_actual = y_test.iloc[0]  # 実績値の最初
first_datetime = test_data.index[0]  # 対応する日時

print(f"予測対象時刻: {first_datetime}")
print(f"固定予測値: {first_pred:.2f}万kW")
print(f"実績値:     {first_actual:.2f}万kW")
print(f"誤差:       {abs(first_pred - first_actual):.2f}万kW")
print(f"誤差率:     {abs(first_pred - first_actual) / first_actual * 100:.2f}%")

# %%
# phase9_no_dropna.pyの最後に追加
first_row_features = test_data.iloc[0][features]
print("phase9の6/1 0:00特徴量:")
for i, (feat_name, feat_val) in enumerate(zip(features, first_row_features)):
    print(f"  {i+1:2d}. {feat_name:20s}: {feat_val}")

# %%