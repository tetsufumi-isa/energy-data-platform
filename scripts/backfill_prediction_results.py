#!/usr/bin/env python3
"""
prediction_results バックフィルスクリプト

10/24-26のCSVファイルからprediction_run_dateを追加してBigQueryに投入
"""

import pandas as pd
from google.cloud import bigquery
from datetime import datetime
from pathlib import Path

def main():
    # BigQueryクライアント初期化
    client = bigquery.Client(project='energy-env')
    dataset_id = 'prod_energy_data'
    table_id = 'prediction_results'
    table_ref = f"{client.project}.{dataset_id}.{table_id}"

    # 処理対象ファイル
    base_dir = Path('/home/teisa/dev/energy-prediction-pipeline/data/predictions')
    files = [
        ('predictions_20251024_070100.csv', '2025-10-24'),
        ('predictions_20251025_070100.csv', '2025-10-25'),
        ('predictions_20251026_070057.csv', '2025-10-26')
    ]

    print("prediction_results バックフィル開始")
    print("=" * 60)

    total_inserted = 0

    for filename, prediction_run_date in files:
        file_path = base_dir / filename

        if not file_path.exists():
            print(f"ファイルが見つかりません: {file_path}")
            continue

        print(f"\n処理中: {filename}")
        print(f"  prediction_run_date: {prediction_run_date}")

        # CSVファイル読み込み
        df = pd.read_csv(file_path)

        # prediction_run_dateカラムを追加
        df['prediction_run_date'] = pd.to_datetime(prediction_run_date).date()

        # カラム順を調整（prediction_run_dateをexecution_idの次に配置）
        columns = ['execution_id', 'prediction_run_date', 'prediction_date',
                   'prediction_hour', 'predicted_power_kwh', 'created_at']
        df = df[columns]

        # データ型変換
        df['prediction_date'] = pd.to_datetime(df['prediction_date']).dt.date
        df['created_at'] = pd.to_datetime(df['created_at'])

        print(f"  レコード数: {len(df)}")

        # BigQueryに投入
        try:
            job = client.load_table_from_dataframe(
                df,
                table_ref,
                job_config=bigquery.LoadJobConfig(
                    write_disposition="WRITE_APPEND"
                )
            )
            job.result()  # 完了を待機

            print(f"  ✓ BigQuery投入成功: {len(df)}件")
            total_inserted += len(df)

        except Exception as e:
            print(f"  ✗ BigQuery投入失敗: {e}")
            continue

    print("\n" + "=" * 60)
    print(f"バックフィル完了: 合計 {total_inserted}件を投入")
    print("=" * 60)

    if total_inserted > 0:
        print("\n次のステップ:")
        print("  1. prediction_accuracy_updaterを実行して精度分析テーブルを更新")
        print("     $ python -m src.data_processing.prediction_accuracy_updater")

if __name__ == "__main__":
    main()
