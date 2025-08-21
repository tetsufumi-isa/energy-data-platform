### 1. データ読み込み・基本確認
- ml_featuresとして学習用データ読み込み
- calendar_dataとしてカレンダーデータ読み込み
- 上記のdfでdateやdatetimeなどの型を作成
- 上記それぞれのdateをインデックスに設定

### 2. Phase 9特徴量定義（12特徴量）
- 特徴量作成

### 3. Phase 9ベースラインモデル学習（2025-05-31まで）
- 5/31までのデータでPhase 9と同様に学習

### 4. 営業日マッピング関数の準備
- get_prev_business_day
  - calendar_dataを使って引数の前営業日を返す、calendar_dataに無ければ前日の日付を返す

- prepare_features_for_prediction
  - 引数はtarget_datetimeとpredictions_dict
    - target_datetime：6/1から開始して6/16までカウントアップして日付を渡す
    - predictions_dict：predictionsを渡している
      - predictions：初回と2回目以降で違う
        - 初回：空のデータ
        - 2回目以降：予測値
  - 基本カレンダー特徴量は前回と同じ内容で設定
  - 祝日フラグを前回と同じ内容で設定
  - 気象データを前回と同じ内容で設定
  - lag_1_dayは初回に実データ、2回目以降は予測値が入る
  - lag_7_dayは7日前のデータ、6/8以降は予測値が入る
  - lag_1_business_day
    - prev_business_date：前営業日の日付
    - lag_1_business_day_datetime：前営業日の同時刻
    - 初回に実データ、2回目以降は予測値が入る
  - feature_valuesで特徴量を設定。lag_1_business_dayなど予測値を使った

### 5. 段階的予測実行（2025-06-01 ～ 2025-06-16）
  - 予測を1日ずつ実行。結果をpredictionsに追加していく。
  - 実績も取得し評価も1日ずつ行っていく

### 6. 全期間精度計算・結果分析
  - 全期間の精度計算

### 7. 日別精度劣化の可視化
  - 可視化