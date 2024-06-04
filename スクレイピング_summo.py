import os
from retry import retry
import requests
from bs4 import BeautifulSoup
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re
import numpy as np
import time

# Streamlit Secretsから環境変数を取得
credentials = st.secrets["gcp_service_account"]

# 環境変数が正しく読み込まれているか確認
if credentials_file_path is None:
    raise ValueError("GOOGLE_APPLICATION_CREDENTIALS環境変数が設定されていません。")
else:
    print(f"Credentials file path: {credentials_file_path}")


# 東京23区の賃貸物件一覧ページのベースURL
base_url = "https://suumo.jp/jj/chintai/ichiran/FR301FC001/?ar=030&bs=040&ta=13&sc=13104&sc=13113&sc=13109&sc=13110&sc=13112&cb=0.0&ct=9999999&et=9999999&cn=9999999&mb=0&mt=9999999&shkr1=03&shkr2=03&shkr3=03&shkr4=03&fw2=&page={}"


def get_html(url):
    r = requests.get(url)
    soup = BeautifulSoup(r.content, "html.parser")
    return soup

all_data = []
max_page = 5  # 取得する最大ページ数

for page in range(1, max_page + 1):
    # ページごとのURLを定義
    url = base_url.format(page)
    
    # HTMLを取得
    soup = get_html(url)
    
    # 物件情報を含むすべてのアイテムを抽出
    items = soup.findAll("div", {"class": "cassetteitem"})
    print("page", page, "items", len(items))
    
    # 各アイテムを処理
    for item in items:
        stations = item.findAll("div", {"class": "cassetteitem_detail-text"})
        
        # 各駅情報を処理
        for station in stations:
            # ベースとなる情報を格納する辞書を定義
            base_data = {}

            # 基本情報を収集
            base_data["名称"] = item.find("div", {"class": "cassetteitem_content-title"}).getText().strip()
            base_data["カテゴリー"] = item.find("div", {"class": "cassetteitem_content-label"}).getText().strip()
            base_data["アドレス"] = item.find("li", {"class": "cassetteitem_detail-col1"}).getText().strip()
            base_data["アクセス"] = station.getText().strip()
            base_data["築年数"] = item.find("li", {"class": "cassetteitem_detail-col3"}).findAll("div")[0].getText().strip()
            base_data["構造"] = item.find("li", {"class": "cassetteitem_detail-col3"}).findAll("div")[1].getText().strip()         
            # 画像URLを取得、存在しない場合は空文字
            img_tag = item.find("div", {"class": "cassetteitem_object-item"}).find("img")
            base_data["画像URL"] = img_tag['rel'] if 'rel' in img_tag.attrs else img_tag['src'] if 'src' in img_tag.attrs else ""
            
            # 各部屋情報を処理
            tbodys = item.find("table", {"class": "cassetteitem_other"}).findAll("tbody")
            
            for tbody in tbodys:
                data = base_data.copy()

                data["階数"] = tbody.findAll("td")[2].getText().strip()
                data["家賃"] = tbody.findAll("td")[3].findAll("li")[0].getText().strip()
                data["管理費"] = tbody.findAll("td")[3].findAll("li")[1].getText().strip()
                data["敷金"] = tbody.findAll("td")[4].findAll("li")[0].getText().strip()
                data["礼金"] = tbody.findAll("td")[4].findAll("li")[1].getText().strip()
                data["間取り"] = tbody.findAll("td")[5].findAll("li")[0].getText().strip()
                data["面積"] = tbody.findAll("td")[5].findAll("li")[1].getText().strip()
                data["URL"] = "https://suumo.jp" + tbody.findAll("td")[8].find("a").get("href")
                
                # データをリストに追加
                all_data.append(data) 

# 各ページの処理後に3秒の遅延を挿入
time.sleep(3)

# データをDataFrameに変換
df = pd.DataFrame(all_data)

# "築年数"から数字部分だけを抽出して新しいカラム "築年数_数値" を作成
def extract_years(value):
    if value == "新築":
        return 0
    match = re.search(r'\d+', value)
    return int(match.group()) if match else 0  # マッチしない場合は0を返す

df['築年数_数値'] = df['築年数'].apply(extract_years)

# "構造"カラムから階数を抽出して新しいカラム "構造_数値" を作成する関数
def extract_storys(value):
    # 地上階数を抽出
    above_ground_match = re.search(r'地上(\d+)階建', value)
    if above_ground_match:
        above_ground_floors = int(above_ground_match.group(1))
    else:
        # 地上階数が直接書かれている場合の処理
        general_match = re.search(r'(\d+)階建', value)
        above_ground_floors = int(general_match.group(1)) if general_match else 0

    # 地下階数を抽出
    below_ground_match = re.search(r'地下(\d+)階', value)
    below_ground_floors = int(below_ground_match.group(1)) if below_ground_match else 0

    # 最大の階数を返す
    return above_ground_floors

# "構造_数値"カラムを作成
df['構造_数値'] = df['構造'].apply(extract_storys)

# 20階建て以上をタワーマンションとして抽出
df['タワーマンション'] = np.where(df['構造_数値'] >= 20, '1', '')


# "階数"カラムから階を削除して数字だけを抽出して新しいカラム "階数_数値" を作成
def extract_floors(value):
    match = re.search(r'\d+', value)
    return int(match.group()) if match else None  # マッチしない場合はNoneを返す

df['階数_数値'] = df['階数'].apply(extract_floors)


# "家賃"カラムから万円を削除して数字だけを抽出し、円単位に変換して新しいカラム "家賃_円" を作成
def extract_rent(value):
    match = re.search(r'(\d+\.\d+|\d+)', value)
    rent = float(match.group()) * 10000 if match else None  # マッチしない場合はNoneを返す
    return int(rent) if rent else None

df['家賃_円'] = df['家賃'].apply(extract_rent)

# "管理費"カラムから円を削除して数字だけを抽出して新しいカラム "管理費_数値" を作成
def extract_management_fee(value):
    if value in ["-", "なし"]:
        return 0  # "なし"や"-"の場合は0を返す
    match = re.search(r'\d+', value)
    return int(match.group()) if match else None  # マッチしない場合はNoneを返す

df['管理費_円'] = df['管理費'].apply(extract_management_fee)
df['家賃（管理費込み）_円']=df['家賃_円']+df['管理費_円']

# "敷金"カラムから万円を削除して数字だけを抽出し、円単位に変換して新しいカラム "敷金_円" を作成
def extract_deposit(value):
    if value in ["-", "なし"]:
        return 0  # "なし"や"-"の場合は0を返す
    match = re.search(r'(\d+\.\d+|\d+)', value)
    rent = float(match.group()) * 10000 if match else None  # マッチしない場合はNoneを返す
    return int(rent) if rent else None

df['敷金_円'] = df['敷金'].apply(extract_deposit)

# "礼金"カラムから万円を削除して数字だけを抽出し、円単位に変換して新しいカラム "礼金_円" を作成
def key_money(value):
    if value in ["-", "なし"]:
        return 0  # "なし"や"-"の場合は0を返す
    match = re.search(r'(\d+\.\d+|\d+)', value)
    rent = float(match.group()) * 10000 if match else None  # マッチしない場合はNoneを返す
    return int(rent) if rent else None

df['礼金_円'] = df['礼金'].apply(key_money)

# "面積"カラムからm2を削除して数字だけを抽出し、新しいカラム "面積_数字" を作成
def extract_area_numeric(value):
    # 正規表現を使用して数字のみを抽出
    match = re.search(r'(\d+\.\d+|\d+)', value)
    area = float(match.group()) if match else None  # マッチしない場合はNoneを返す
    return area

# '面積'カラムから数字のみを抽出して'面積_数字'カラムを作成
df['面積_数字'] = df['面積'].apply(extract_area_numeric)
df.fillna(0, inplace=True)


# "サービスルームあり"を含む行の抽出と新しいカラムの追加
df['Service_room'] = df['間取り'].apply(lambda x: '1' if 'S' in x else '')

# アドレスを分割する関数
def split_address(address):
    # 都道府県を取得
    prefecture_match = re.match(r'(東京都|北海道|(?:京都|大阪)府|.{2,3}県)', address)
    prefecture = prefecture_match.group(0) if prefecture_match else ''
    
    # 都道府県を除いた残りの部分
    remaining_address = address[len(prefecture):]
    
    # 市区町村を取得
    city_match = re.match(r'.*?[市区町村]', remaining_address)
    city = city_match.group(0) if city_match else remaining_address  # 市区町村が見つからない場合は全体を市区町村とする
    
    return prefecture, city

# アドレスを分割して新しいカラムに格納
df[['都道府県', '市区町村']] = df['アドレス'].apply(lambda x: pd.Series(split_address(x)))

def split_access(value):
    match = re.match(r'(.+)駅 歩(\d+)分', value)
    if match:
        line_station = match.group(1)
        minutes = match.group(2)
        # '/'で路線名と駅名を分割
        line, station = line_station.split('/')
        return pd.Series([line, station, minutes])
    return pd.Series([0, 0, 0])

# 新しいカラムを追加
df[['路線', '駅', '徒歩_分']] = df['アクセス'].apply(split_access)

# データの削除
# 重複データの削除
df = df.drop_duplicates(subset=['名称', '階数', '家賃'], keep='first')


# Google Sheetsに接続するための設定
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(credentials_file_path, scope)
client = gspread.authorize(creds)

# スプレッドシートを開く
spreadsheet = client.open('summo スクレイピング')

# ワークシートを選択（存在しない場合は作成）
try:
    worksheet = spreadsheet.worksheet('Sheet1')
except gspread.exceptions.WorksheetNotFound:
    worksheet = spreadsheet.add_worksheet(title='Sheet1', rows=df.shape[0], cols=df.shape[1])

# ワークシートにデータを書き込む
worksheet.clear()
worksheet.update([df.columns.values.tolist()] + df.values.tolist())

print("データがGoogleスプレッドシートに保存されました。")
