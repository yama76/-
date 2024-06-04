import os
import json
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import streamlit as st
import plotly.express as px

# SecretsからJSONキーを読み込む
credentials_json = st.secrets["gcp_service_account"]

# JSONキーを辞書に変換
credentials_dict = json.loads(json.dumps(credentials_json))

# Google Sheetsに接続するための設定
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(credentials_dict, scope)
client = gspread.authorize(creds)

# スプレッドシートを開く
spreadsheet = client.open('summo スクレイピング')

# ワークシートを選択
worksheet = spreadsheet.worksheet('Sheet1')

# ワークシートのデータを取得
rows = worksheet.get_all_values()

# DataFrameに変換
data = pd.DataFrame(rows[1:], columns=rows[0])  # ヘッダーを設定

# アプリのメイン関数
st.title('Opti Home')

# 築年数が文字列として扱われている場合、数値に変換する
data['築年数_数値'] = pd.to_numeric(data['築年数_数値'], errors='coerce')

# 家賃が文字列として扱われている場合、数値に変換する
data['家賃（管理費込み）_円'] = data['家賃（管理費込み）_円'].str.replace(',', '').astype(float)

# 面積が文字列として扱われている場合、数値に変換する
data['面積_数字'] = pd.to_numeric(data['面積_数字'], errors='coerce')

# 徒歩が文字列として扱われている場合、数値に変換する
data['徒歩_分'] = pd.to_numeric(data['徒歩_分'], errors='coerce')

# 必要な列が存在するか確認
required_columns = ['築年数_数値', '家賃（管理費込み）_円', '面積_数字', '徒歩_分', '市区町村', '名称', 'URL']
missing_columns = [col for col in required_columns if col not in data.columns]
if missing_columns:
    st.error(f"以下の必要な列がデータに存在しません: {', '.join(missing_columns)}")
    st.stop()

# フロント表示のテキストを定義
data['築年数(年)'] = data['築年数_数値']
data['家賃（円）'] = data['家賃（管理費込み）_円']
data['平米数'] = data['面積_数字']
data['徒歩(駅)'] = data['徒歩_分']

# HTMLを使って条件入力の文字を大きく表示
st.sidebar.markdown("<h1>コンシェルジュサービス</h1>", unsafe_allow_html=True)

# 最低居住スペース計算
adults = st.sidebar.number_input("大人の人数を入力してください:", min_value=0, value=1)
children = st.sidebar.number_input("子供の人数を入力してください:", min_value=0, value=0)
Number_of_residents = adults + children
minimum_living_space = 10 * Number_of_residents + 10

# 家賃の目安計算
annual_income = st.sidebar.number_input("年収を入力してください（万円）:", min_value=0, value=500)
rent_option = st.sidebar.selectbox(
    "家賃にどれくらいお金をかけますか？",
    ("なるべく抑えたい（年収20％）", "平均的な水準（年収25％）", "いい所に住みたい（年収30％）")
)

rent_percentage = {'なるべく抑えたい（年収20％）': 0.20, '平均的な水準（年収25％）': 0.25, 'いい所に住みたい（年収30％）': 0.30}
monthly_rent_budget = annual_income * 10000 * rent_percentage[rent_option] / 12

# 各区の家賃相場（円/平米）
district_rent_rates = {
    '渋谷区': 5337,
    '目黒区': 3685,
    '新宿区': 3661,
    '品川区': 3652,
    '世田谷区': 2993
}

# 選択された区の家賃相場
selected_district = st.sidebar.selectbox(
    "市区町村を選択してください:",
    data['市区町村'].unique()
)

if selected_district in district_rent_rates:
    rent_rate = district_rent_rates[selected_district]
    district_rent = minimum_living_space * rent_rate
    st.sidebar.write(f"{selected_district}の家賃相場: {district_rent:.0f} 円")
else:
    st.sidebar.write("選択された区の家賃相場データがありません")
st.sidebar.write(f"月額家賃の目安: {monthly_rent_budget:.0f} 円")
st.sidebar.write(f"最低居住スペース: {minimum_living_space} 平米")

# HTMLを使って条件入力の文字を大きく表示
st.sidebar.markdown("<h1>詳細検索</h1>", unsafe_allow_html=True)

# 各種範囲指定スライダー
rent_range = st.sidebar.slider(
    '家賃範囲を選択してください',
    min_value=0,
    max_value=300000,
    value=(50000, 150000),
    step=1000
)
(min_rent, max_rent) = rent_range

construction_year_range = st.sidebar.slider(
    '築年数の範囲を選択してください',
    min_value=0,
    max_value=100,
    value=(0, 30),
    step=1
)
(min_age, max_age) = construction_year_range

walking_time = st.sidebar.slider(
    '駅からの徒歩時間（分）を選択してください',
    min_value=0,
    max_value=30,
    value=(0, 10),
    step=1
)
(min_time, max_time) = walking_time

area_range = st.sidebar.slider(
    '面積の範囲を選択してください（平米）',
    min_value=0,
    max_value=200,
    value=(20, 100),
    step=1
)
(min_area, max_area) = area_range

# 比較したい項目の選択
selected_vars = st.sidebar.multiselect(
    "比較したい項目を選択してください。（2つ以上選択）:",
    ["家賃（円）", "平米数", "徒歩(駅)", "築年数(年)"],
    default=["家賃（円）", "平米数"]
)

# 比較ボタン
compare_button = st.sidebar.button('比較')

# データベースから対象の物件を取得
edited_data = data[
    (data['市区町村'] == selected_district) &
    (data['家賃（管理費込み）_円'] >= min_rent) &
    (data['家賃（管理費込み）_円'] <= max_rent) &
    (data['徒歩_分'] >= min_time) &
    (data['徒歩_分'] <= max_time) &
    (data['築年数_数値'] >= min_age) &
    (data['築年数_数値'] <= max_age) &
    (data['面積_数字'] >= min_area) &
    (data['面積_数字'] <= max_area)
]

# 比較ボタンが押されたらプロットを表示
if compare_button:
    if len(selected_vars) < 2:
        st.error("少なくとも2つの変数を選択してください。")
    else:
        hover_data = ['市区町村', '築年数(年)']  # 'No' を削除し、存在するカラム名を使用
        if len(selected_vars) == 2:
            fig = px.scatter(edited_data, x=selected_vars[0], y=selected_vars[1], hover_data=hover_data)
        elif len(selected_vars) == 3:
            fig = px.scatter(edited_data, x=selected_vars[0], y=selected_vars[1], color=selected_vars[2], hover_data=hover_data)
        elif len(selected_vars) == 4:
            fig = px.scatter(edited_data, x=selected_vars[0], y=selected_vars[1], size=selected_vars[3], color=selected_vars[2], hover_data=hover_data)

        st.plotly_chart(fig)
        st.write("対象物件リスト:")
        # 表の作成
        display_columns = ['市区町村', '築年数(年)', '家賃（円）', '平米数', '徒歩(駅)', 'URL']
        edited_data['URL'] = edited_data['URL'].apply(lambda x: f"<a href='{x}' target='_blank'>SUUMOで見る</a>")
        st.write(edited_data[display_columns].to_html(escape=False), unsafe_allow_html=True)
