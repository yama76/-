import os
from dotenv import load_dotenv
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv
import streamlit as st
import plotly.express as px

# .envファイルから環境変数を読み込む
load_dotenv()

# 環境変数からJSONファイルのパスを取得
credentials_file_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

# 環境変数が正しく読み込まれているか確認
if credentials_file_path is None:
    raise ValueError("GOOGLE_APPLICATION_CREDENTIALS環境変数が設定されていません。")
else:
    print(f"Credentials file path: {credentials_file_path}")

# Google Sheetsに接続するための設定
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(credentials_file_path, scope)
client = gspread.authorize(creds)

# スプレッドシートを開く
spreadsheet = client.open('summo スクレイピング')

# ワークシートを選択
worksheet = spreadsheet.worksheet('Sheet1')

# ワークシートのデータを取得
rows = worksheet.get_all_values()
# ここまで

# DataFrameに変換
data = pd.DataFrame(rows[1:], columns=rows[0])  # ヘッダーを設定

# データの型変換（必要に応じて）
data['家賃（管理費込み）_円'] = pd.to_numeric(data['家賃（管理費込み）_円'], errors='coerce')
data['面積_数字'] = pd.to_numeric(data['面積_数字'], errors='coerce')
data['築年数_数値'] = pd.to_numeric(data['築年数_数値'], errors='coerce')
data['徒歩_分'] = pd.to_numeric(data['徒歩_分'], errors='coerce')

# アプリのメイン関数
st.title('Opti Home')

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

# 行番号をデータに追加
data.insert(0, 'No', data.index + 1)  # 一番左に行番号の列を追加

# HTMLを使って条件入力の文字を大きく表示
st.sidebar.markdown("<h1>不動産を比較検討</h1>", unsafe_allow_html=True)

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

# 区の選択
selected_district = st.sidebar.selectbox(
    "市区町村を選択してください:",
    data['市区町村'].unique()
)

# 比較したい項目の選択
selected_vars = st.sidebar.multiselect(
    "比較したい項目を選択してください。（2つ以上選択）:",
    ["家賃（円）", "平米数", "徒歩(駅)", "築年数(年)"],
    default=["家賃（円）", "平米数"]
)

# 比較ボタン
compare_button = st.sidebar.button('比較')

# コンシェルジュサービスに関する情報入力
st.sidebar.markdown("### コンシェルジュサービス")

# 最低居住スペース計算
adults = st.sidebar.number_input("大人の人数を入力してください:", min_value=0, value=1)
children = st.sidebar.number_input("子供の人数を入力してください:", min_value=0, value=0)
Number_of_residents = adults + children
minimum_living_space = 10 * Number_of_residents + 10
st.sidebar.write(f"最低居住スペース: {minimum_living_space} 平米")

# 家賃の目安計算
annual_income = st.sidebar.number_input("年収を入力してください（万円）:", min_value=0, value=500)
rent_option = st.sidebar.selectbox(
    "家賃にどれくらいお金をかけますか？",
    ("なるべく抑えたい（年収20％）", "平均的な水準（年収25％）", "いい所に住みたい（年収30％）")
)
rent_percentage = {'なるべく抑えたい（年収20％）': 0.20, '平均的な水準（年収25％）': 0.25, 'いい所に住みたい（年収30％）': 0.30}
monthly_rent_budget = annual_income * 10000 * rent_percentage[rent_option] / 12
st.sidebar.write(f"月額家賃の目安: {monthly_rent_budget:.0f} 円")

# 各区の家賃相場（円/平米）
district_rent_rates = {
    '渋谷区': 5337,
    '目黒区': 3685,
    '新宿区': 3661,
    '品川区': 3652,
    '世田谷区': 2993
}

# 選択された区の家賃相場
if selected_district in district_rent_rates:
    rent_rate = district_rent_rates[selected_district]
    district_rent = minimum_living_space * rent_rate
    st.sidebar.write(f"{selected_district}の最低居住スペースにおける家賃相場: {district_rent:.0f} 円")
else:
    st.sidebar.write("選択された区の家賃相場データがありません")

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

# お気に入りリストの初期化
if 'favorites' not in st.session_state:
    st.session_state.favorites = []

# お気に入りに追加する関数
def add_to_favorites(index):
    if index not in st.session_state.favorites:
        st.session_state.favorites.append(index)
        st.success(f"物件 {index} をお気に入りに追加しました")

# 比較ボタンが押されたらプロットを表示
if compare_button:
    if len(selected_vars) < 2:
        st.error("少なくとも2つの変数を選択してください。")
    else:
        hover_data = ['名称', 'URL', 'No']
        if len(selected_vars) == 2:
            fig = px.scatter(edited_data, x=selected_vars[0], y=selected_vars[1], hover_data=hover_data)
        elif len(selected_vars) == 3:
            fig = px.scatter(edited_data, x=selected_vars[0], y=selected_vars[1], color=selected_vars[2], hover_data=hover_data)
        elif len(selected_vars) == 4:
            fig = px.scatter(edited_data, x=selected_vars[0], y=selected_vars[1], size=selected_vars[3], color=selected_vars[2], hover_data=hover_data)

        st.plotly_chart(fig)
        st.write("対象物件リスト:")

        # 表の作成
        favorite_col = st.container()
        for index, row in edited_data.iterrows():
            col1, col2, col3, col4, col5, col6, col7, col8 = st.columns([0.5, 1, 1, 1, 1, 1, 2, 1])
            col1.write(row['No'])
            col2.write(row['名称'])
            col3.write(row['市区町村'])
            col4.write(row['築年数(年)'])
            col5.write(row['家賃（円）'])
            col6.write(row['平米数'])
            col7.write(row['徒歩(駅)'])
            col8.write(f"[リンク]({row['URL']})")
            if col1.button('⭐️', key=row['No']):
                add_to_favorites(row['No'])

# お気に入りリストの表示
if st.session_state.favorites:
    st.write("お気に入りリスト:")
    st.write(data[data['No'].isin(st.session_state.favorites)])
