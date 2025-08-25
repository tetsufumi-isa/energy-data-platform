#!/usr/bin/env python3
"""
ml_features.csvの欠損値確認スクリプト
目的: ml_features.csvファイルの欠損値状況を詳細に確認
"""

import pandas as pd
import numpy as np
from pathlib import Path
import os

def check_missing_values():
    """ml_features.csvの欠損値を詳細確認"""
    
    # 環境変数からパスを取得
    env_path = os.environ.get('ENERGY_ENV_PATH')
    if not env_path:
        print("❌ 環境変数ENERGY_ENV_PATHが設定されていません")
        return
    
    # ファイルパスの構築
    file_path = Path(env_path) / "data" / "ml" / "ml_features.csv"
    
    print(f"🔍 チェック対象ファイル: {file_path}")
    print("=" * 60)
    
    # ファイル存在確認
    if not file_path.exists():
        print(f"❌ ファイルが見つかりません: {file_path}")
        return
    
    try:
        # データ読み込み
        print("📂 データ読み込み中...")
        df = pd.read_csv(file_path)
        print(f"✅ 読み込み完了: {len(df):,}行 × {len(df.columns)}列")
        print()
        
        # 基本情報
        print("📊 基本情報")
        print("-" * 30)
        print(f"データ形状: {df.shape}")
        print(f"ファイルサイズ: {file_path.stat().st_size / 1024 / 1024:.2f} MB")
        print()
        
        # 列名確認
        print("📋 列名一覧")
        print("-" * 30)
        for i, col in enumerate(df.columns, 1):
            print(f"{i:2d}. {col}")
        print()
        
        # 欠損値の全体サマリー
        total_cells = df.shape[0] * df.shape[1]
        total_missing = df.isnull().sum().sum()
        missing_percentage = (total_missing / total_cells) * 100
        
        print("🔍 欠損値サマリー")
        print("-" * 30)
        print(f"総セル数: {total_cells:,}")
        print(f"欠損値総数: {total_missing:,}")
        print(f"欠損値割合: {missing_percentage:.2f}%")
        print()
        
        # 各列の欠損値詳細
        print("📈 各列の欠損値状況")
        print("-" * 50)
        missing_info = []
        
        for col in df.columns:
            missing_count = df[col].isnull().sum()
            missing_pct = (missing_count / len(df)) * 100
            missing_info.append({
                'column': col,
                'missing_count': missing_count,
                'missing_percentage': missing_pct,
                'data_type': str(df[col].dtype)
            })
        
        # 欠損値が多い順にソート
        missing_info.sort(key=lambda x: x['missing_count'], reverse=True)
        
        print(f"{'列名':<25} {'欠損数':<8} {'欠損率':<8} {'データ型':<12}")
        print("-" * 60)
        
        for info in missing_info:
            if info['missing_count'] > 0:
                print(f"{info['column']:<25} {info['missing_count']:<8} {info['missing_percentage']:<7.2f}% {info['data_type']:<12}")
        
        # 欠損値がない列の確認
        no_missing_cols = [info['column'] for info in missing_info if info['missing_count'] == 0]
        if no_missing_cols:
            print()
            print(f"✅ 欠損値なしの列: {len(no_missing_cols)}個")
            for col in no_missing_cols[:10]:  # 最初の10個まで表示
                print(f"   - {col}")
            if len(no_missing_cols) > 10:
                print(f"   ... その他{len(no_missing_cols) - 10}個")
        
        # 欠損値パターンの分析
        if total_missing > 0:
            print()
            print("🔍 欠損値パターン分析")
            print("-" * 30)
            
            # 完全に欠損している行の確認
            completely_missing_rows = df.isnull().all(axis=1).sum()
            print(f"全列が欠損の行: {completely_missing_rows}行")
            
            # 一部が欠損している行の確認
            partially_missing_rows = (df.isnull().any(axis=1) & ~df.isnull().all(axis=1)).sum()
            print(f"一部が欠損の行: {partially_missing_rows}行")
            
            # 完全なデータの行
            complete_rows = (~df.isnull().any(axis=1)).sum()
            complete_percentage = (complete_rows / len(df)) * 100
            print(f"完全なデータの行: {complete_rows}行 ({complete_percentage:.2f}%)")
            
            # 日付列がある場合の欠損パターン確認
            date_columns = [col for col in df.columns if 'date' in col.lower() or 'time' in col.lower()]
            if date_columns:
                print()
                print("📅 日付ベースの欠損確認")
                print("-" * 30)
                for date_col in date_columns:
                    if date_col in df.columns:
                        print(f"日付列: {date_col}")
                        # 日付ごとの欠損パターンを確認
                        df_with_missing = df.copy()
                        df_with_missing['has_missing'] = df_with_missing.isnull().any(axis=1)
                        if date_col in df_with_missing.columns:
                            try:
                                df_with_missing[date_col] = pd.to_datetime(df_with_missing[date_col])
                                
                                # 日別の欠損行数
                                missing_by_date = df_with_missing.groupby(df_with_missing[date_col].dt.date)['has_missing'].sum()
                                
                                # 日別の欠損セル数
                                missing_cells_by_date = df_with_missing.groupby(df_with_missing[date_col].dt.date).apply(
                                    lambda x: x.drop(columns=['has_missing']).isnull().sum().sum()
                                )
                                
                                if missing_by_date.sum() > 0:
                                    print(f"欠損がある日数: {(missing_by_date > 0).sum()}日")
                                    print()
                                    
                                    # 日別の列ごと欠損数
                                    missing_by_date_column = df_with_missing.groupby(df_with_missing[date_col].dt.date).apply(
                                        lambda x: x.drop(columns=['has_missing']).isnull().sum()
                                    )
                                    
                                    print("📊 日別欠損行数（上位10日）:")
                                    print(f"{'日付':<12} {'欠損行数':<8}")
                                    print("-" * 25)
                                    
                                    # 欠損行数でソートして上位10日を表示
                                    top_dates_rows = missing_by_date.nlargest(10)
                                    for date, rows in top_dates_rows.items():
                                        if rows > 0:
                                            print(f"{str(date):<12} {rows:<8}")
                                    
                                    print()
                                    print("📊 日別欠損セル数（上位10日）:")
                                    print(f"{'日付':<12} {'欠損セル数':<10}")
                                    print("-" * 25)
                                    
                                    # 欠損セル数でソートして上位10日を表示
                                    top_dates_cells = missing_cells_by_date.nlargest(10)
                                    for date, cells in top_dates_cells.items():
                                        if cells > 0:
                                            print(f"{str(date):<12} {cells:<10}")
                                    
                                    print()
                                    print("📊 日別列ごと欠損数（欠損セル数上位5日）:")
                                    print("-" * 40)
                                    
                                    # 欠損セル数上位5日の列別詳細を表示
                                    top_5_dates = missing_cells_by_date.nlargest(5).index
                                    for date in top_5_dates:
                                        if missing_by_date[date] > 0:
                                            print(f"\n📅 {date} (欠損行数: {missing_by_date[date]}, 欠損セル数: {missing_cells_by_date[date]})")
                                            column_missing = missing_by_date_column.loc[date]
                                            column_missing_filtered = column_missing[column_missing > 0].sort_values(ascending=False)
                                            
                                            if len(column_missing_filtered) > 0:
                                                for col, count in column_missing_filtered.items():
                                                    print(f"  {col}: {count}個")
                                            else:
                                                print("  （欠損なし）")
                                    
                                    print()
                                    print("📈 欠損パターン分析:")
                                    total_missing_rows = missing_by_date.sum()
                                    total_missing_cells = missing_cells_by_date.sum()
                                    overall_avg = total_missing_cells / total_missing_rows if total_missing_rows > 0 else 0
                                    print(f"  総欠損行数: {total_missing_rows}")
                                    print(f"  総欠損セル数: {total_missing_cells}")
                                    print(f"  平均セル/行: {overall_avg:.1f}")
                                    
                                    # パターン判定
                                    total_columns = len([col for col in df.columns if col != 'has_missing'])
                                    if overall_avg >= total_columns * 0.8:  # 80%以上の列で欠損
                                        print("  🚨 パターン: 全列欠損型（API障害の可能性）")
                                    elif overall_avg <= 3:
                                        print("  ⚠️  パターン: 部分欠損型（特定列の問題）")
                                    else:
                                        print("  📊 パターン: 混在型（複合的な問題）")
                            except:
                                print(f"  {date_col}を日付として解析できませんでした")
        
        else:
            print("🎉 欠損値は見つかりませんでした！")
            print("✅ すべてのデータが完全に揃っています")
        
        print()
        print("=" * 60)
        print("✅ 欠損値確認完了")
        
        return {
            'total_rows': len(df),
            'total_columns': len(df.columns),
            'total_missing': total_missing,
            'missing_percentage': missing_percentage,
            'columns_with_missing': [info['column'] for info in missing_info if info['missing_count'] > 0],
            'complete_rows': len(df) - df.isnull().any(axis=1).sum() if total_missing > 0 else len(df)
        }
        
    except Exception as e:
        print(f"❌ エラーが発生しました: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    print("🔍 ml_features.csv 欠損値確認ツール")
    print("=" * 60)
    result = check_missing_values()
    
    if result:
        print()
        print("📊 確認結果サマリー")
        print("-" * 30)
        print(f"データ行数: {result['total_rows']:,}")
        print(f"データ列数: {result['total_columns']}")
        print(f"欠損値総数: {result['total_missing']:,}")
        print(f"欠損値割合: {result['missing_percentage']:.2f}%")
        print(f"完全なデータ行数: {result['complete_rows']:,}")
        
        if result['columns_with_missing']:
            print(f"欠損がある列数: {len(result['columns_with_missing'])}")
        else:
            print("🎉 全列で欠損値なし")