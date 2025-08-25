import pandas as pd
import numpy as np
import os

# データ読み込み
df = pd.read_csv(os.path.join(os.getenv('ENERGY_ENV_PATH'), 'data', 'ml', 'ml_features.csv'))
df['datetime'] = pd.to_datetime(df['date'].astype(str) + ' ' + df['hour'].astype(str) + ':00:00')
df['date'] = df['datetime'].dt.date
df['weekday'] = df['datetime'].dt.dayofweek  # 0=月曜, 6=日曜

print("=== データ期間 ===")
print(f"開始: {df['datetime'].min()}")
print(f"終了: {df['datetime'].max()}")
print(f"総レコード数: {len(df)}")

# 前営業日列を指定
main_lag_col = 'lag_1_business_day'
print(f"\n=== 調査対象列: {main_lag_col} ===")

# 前営業日データの欠損パターン分析
print(f"\n=== {main_lag_col} 欠損分析 ===")

# 日付別の欠損数をカウント
daily_missing_count = df.groupby('date')[main_lag_col].apply(lambda x: x.isnull().sum())
missing_dates_info = daily_missing_count[daily_missing_count > 0]

print(f"前営業日データに欠損がある日数: {len(missing_dates_info)}")

if len(missing_dates_info) > 0:
    print(f"\n=== 欠損日の全リスト（欠損数付き） ===")
    for date, missing_count in missing_dates_info.items():
        date_data = df[df['date'] == date].iloc[0]
        weekday_name = ['月', '火', '水', '木', '金', '土', '日'][date_data['weekday']]
        print(f"{date} ({weekday_name}): {missing_count}件欠損")

# 前日が祝日かどうかでの欠損パターン
print(f"\n=== 前日の祝日状況別欠損パターン ===")
missing_dates = missing_dates_info.index
missing_df = df[df['date'].isin(missing_dates)]

if len(missing_df) > 0:
    # 前日のis_holiday状況を調べる簡易版
    holiday_pattern = []
    for date in missing_dates:
        prev_date = pd.to_datetime(date) - pd.Timedelta(days=1)
        prev_date_only = prev_date.date()
        
        # 前日のデータを探す
        prev_data = df[df['date'] == prev_date_only]
        if len(prev_data) > 0:
            is_prev_holiday = prev_data['is_holiday'].iloc[0]
            holiday_pattern.append(is_prev_holiday)
        else:
            holiday_pattern.append(None)  # 前日データなし
    
    # 集計
    prev_holiday_count = sum(1 for x in holiday_pattern if x == True)
    prev_workday_count = sum(1 for x in holiday_pattern if x == False)
    prev_unknown_count = sum(1 for x in holiday_pattern if x is None)
    
    print(f"前日が平日での欠損: {prev_workday_count}日")
    print(f"前日が祝日での欠損: {prev_holiday_count}日")
    if prev_unknown_count > 0:
        print(f"前日データなしでの欠損: {prev_unknown_count}日")

# データ開始時期の確認（参考情報）
print(f"\n=== データ開始時期の確認 ===")
jan_2023 = df[(df['datetime'].dt.year == 2023) & (df['datetime'].dt.month == 1)]
if len(jan_2023) > 0:
    jan_missing_count = jan_2023.groupby('date')[main_lag_col].apply(lambda x: x.isnull().sum())
    jan_missing_dates = jan_missing_count[jan_missing_count > 0]
    print(f"2023年1月の欠損日数: {len(jan_missing_dates)}日")
else:
    print("2023年1月のデータがありません")