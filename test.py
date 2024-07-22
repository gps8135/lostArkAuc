import requests
import pandas as pd
import schedule
import time
import winsound
from plyer import notification
import threading
from datetime import datetime

# 알림을 보낼 가격 임계값 설정
PRICE_THRESHOLD = 1400000  # 예시로 2,500,000으로 설정
interval = 0.01 # 주기 설정 (초 단위)
alert_interval = 5  # 같은 항목에 대해 알림을 보내지 않는 최소 시간 간격 (초 단위)

# 요청을 위한 헤더 설정
headers = {
    'accept': 'application/json',
    'authorization': 'bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsIng1dCI6IktYMk40TkRDSTJ5NTA5NWpjTWk5TllqY2lyZyIsImtpZCI6IktYMk40TkRDSTJ5NTA5NWpjTWk5TllqY2lyZyJ9.eyJpc3MiOiJodHRwczovL2x1ZHkuZ2FtZS5vbnN0b3ZlLmNvbSIsImF1ZCI6Imh0dHBzOi8vbHVkeS5nYW1lLm9uc3RvdmUuY29tL3Jlc291cmNlcyIsImNsaWVudF9pZCI6IjEwMDAwMDAwMDAwMDAxNTcifQ.bAFoaxzbSnZoddBywXPGgigK6yFeticxO905ziglUxdCc4ELeZN9j0M1Ze0tsU2RdiU4eRj4omtCSMQgZzAYyzeEYpQ2K0mIZxhqrYQxuUApAgMc8Yp02H7W60uHow9db3D8oxT8gFLyehUODTmrotUXRkACwMauM6yWkMI0za8mod-0lzEDJR6g0R-XA_3gyaiyecspRmtpxAI1Vo790phbRyOTTK8khFVWseo7w8hxp7T7NU8U19aM8k61dlMQQwfkOjVjO1o-g25xWePIbQII7Gx8B3t9_itw-v1WHtX2s2iA1BurAAJAs58u89FkJjEYi7T4TbrERrELVTrahg',  
    # 토큰을 여기에 넣으세요
    'Content-Type': 'application/json',
}

# 요청을 위한 JSON 데이터 설정
json_data = {
    'ItemLevelMin': 0,
    'ItemLevelMax': 0,
    'ItemGradeQuality': None,
    'SkillOptions': [
        {
            'FirstOption': None,
            'SecondOption': None,
            'MinValue': None,
            'MaxValue': None,
        },
    ],
    'EtcOptions': [
        {
            'FirstOption': None,
            'SecondOption': None,
            'MinValue': None,
            'MaxValue': None,
        },
    ],
    'Sort': 'BUY_PRICE',
    'CategoryCode': 210000,
    'CharacterClass': '',
    'ItemTier': 4,
    'ItemGrade': None,
    'ItemName': '10레벨 겁화',
    'PageNo': 1,
    'SortCondition': 'ASC',
}

run_count = 0
stop_flag = False
last_alert_time = {}  # 최근에 알림을 보낸 항목과 시간을 저장

def format_price(price):
    return f"{price:,}"

def check_prices():
    global run_count
    global stop_flag
    global last_alert_time

    if stop_flag:
        return

    try:
        # API 요청을 보내고 응답을 JSON으로 파싱
        response = requests.post('https://developer-lostark.game.onstove.com/auctions/items', headers=headers, json=json_data)

        # 응답 상태 코드 확인
        if response.status_code != 200:
            print(f"API 요청 실패. 상태 코드: {response.status_code}")
            return

        response_json = response.json()
        x_ratelimit_remaining = response.headers.get('x-ratelimit-remaining')

        # 응답 JSON에서 Items 키가 있는지 확인
        if 'Items' not in response_json:
            print("응답 JSON에 'Items' 키가 없습니다.")
            return

        items = response_json['Items']
        df_items = pd.json_normalize(items)

        # 데이터 타입을 확인하고 필요한 경우 변환
        if 'AuctionInfo.BuyPrice' in df_items.columns:
            df_items['AuctionInfo.BuyPrice'] = pd.to_numeric(df_items['AuctionInfo.BuyPrice'], errors='coerce')

        # Options 필드를 개별 컬럼으로 변환 (여러 옵션을 하나의 데이터프레임으로 병합)
        options_list = []
        for index, row in df_items.iterrows():
            for option in row['Options']:
                option_row = option.copy()
                option_row['Name'] = row['Name']
                options_list.append(option_row)

        df_options = pd.DataFrame(options_list)

        # 기본 아이템 정보에서 Icon 및 Options 컬럼 제거
        df_items = df_items.drop(columns=['Icon', 'Options'])

        # 최종 데이터프레임 합치기
        df_items = df_items.merge(df_options, on='Name')

        # 컬럼 순서 재정렬 (Name, AuctionInfo.BuyPrice, 나머지)
        columns_order = ['Name', 'AuctionInfo.BuyPrice'] + [col for col in df_items.columns if col not in ['Name', 'AuctionInfo.BuyPrice']]
        df_items = df_items[columns_order]

        # 컬럼 이름 수정 (AuctionInfo.BuyPrice를 BuyPrice로 변경)
        df_items.rename(columns={'AuctionInfo.BuyPrice': 'BuyPrice'}, inplace=True)

        # 가격 임계값을 확인하여 알림 보내기
        current_time = datetime.now()
        min_price = df_items['BuyPrice'].min()
        for _, row in df_items.iterrows():
            item_name = row['Name']
            if row['BuyPrice'] <= PRICE_THRESHOLD:
                # 마지막 알림 시간 확인
                if item_name in last_alert_time:
                    last_alert = last_alert_time[item_name]
                    if (current_time - last_alert).total_seconds() < alert_interval:
                        continue  # 알림 간격이 충분하지 않으면 건너뜀

                # 소리 알림
                if not stop_flag:
                    winsound.Beep(1000, 1000)  # 1000 Hz 주파수의 소리를 1초 동안 재생
                # 화면 알림
                if not stop_flag:
                    notification.notify(
                        title='가격 알림',
                        message=f"{row['Name']}의 가격이 {row['BuyPrice']}원 이하로 떨어졌습니다!",
                        timeout=10
                    )
                # 알림 시간 업데이트
                last_alert_time[item_name] = current_time

        # CSV 파일로 저장
        df_items.to_csv('lostark_items.csv', index=False, encoding='utf-8-sig')
        run_count += 1
        print(f"현재 임계가{PRICE_THRESHOLD: ,} 실행 횟수: {run_count}, 현재 최저가: {format_price(min_price)}, 남은 요청 수: {x_ratelimit_remaining}")
    except Exception as e:
        print(f"오류 발생: {e}")

# 처음 실행
check_prices()

# 주기적으로 실행 (interval 변수 사용)
schedule.every(interval).seconds.do(check_prices)

def monitor_input():
    global stop_flag
    while True:
        user_input = input("프로그램을 종료하려면 'stop'을 입력하세요: \n")
        if user_input.lower() == 'stop':
            stop_flag = True
            print("프로그램을 종료합니다.")
            break

# 사용자 입력을 모니터링하는 스레드 시작
input_thread = threading.Thread(target=monitor_input)
input_thread.start()

print("프로그램이 실행 중입니다. 주기적으로 가격을 확인합니다.")

while not stop_flag:
    schedule.run_pending()
    time.sleep(1)

input_thread.join()
print("프로그램이 정상적으로 종료되었습니다.\n")
