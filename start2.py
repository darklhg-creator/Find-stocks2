import FinanceDataReader as fdr
import yfinance as yf
import pandas as pd
import requests
from datetime import datetime

# 디스코드 웹후크 URL
DISCORD_WEBHOOK_URL = 'https://discord.com/api/webhooks/1474739516177911979/IlrMnj_UABCGYJiVg9NcPpSVT2HoT9aMNpTsVyJzCK3yS9LQH9E0WgbYB99FHVS2SUWT'

def send_discord_message(content):
    data = {"content": content}
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=data)
    except Exception as e:
        print(f"메시지 전송 에러: {e}")

def run_analysis():
    today_str = datetime.now().strftime('%Y-%m-%d %A')
    print(f"--- {today_str} 분석 시작 ---")
    
    try:
        # 가장 안정적인 'KRX' 리스트를 가져옵니다.
        # 만약 여기서 Sector가 안나오면 'NAVER' 리스트를 대안으로 사용합니다.
        df_krx = fdr.StockListing('KRX')
        
        # 만약 Sector 컬럼이 없다면, 업종 정보가 포함된 다른 리스트를 시도합니다.
        if 'Sector' not in df_krx.columns:
            print("KRX 데이터에 Sector가 없어 NAVER 데이터를 시도합니다.")
            df_krx = fdr.StockListing('NAVER')

        # '반도체'라는 글자가 포함된 종목 필터링
        # 컬럼명이 'Sector'가 아닐 경우를 대비해 'Industry' 등도 체크합니다.
        col_name = 'Sector' if 'Sector' in df_krx.columns else 'Industry'
        semi_df = df_krx[df_krx[col_name].str.contains('반도체', na=False)].copy()
        
    except Exception as e:
        send_discord_message(f"❌ 데이터 로드 실패: {e}")
        return

    target_list = []
    
    # 분석 대상 (상위 50개)
    for index, row in semi_df.head(50).iterrows():
        # 종목코드는 'Symbol' 또는 'Code'라는 이름으로 들어있습니다.
        ticker = row['Symbol'] if 'Symbol' in row else row['Code']
        name = row['Name']
        
        # 시장 구분 (yfinance용 접미사)
        # MarketId나 Market 컬럼을 확인
        market = str(row.get('Market', ''))
        suffix = ".KS" if "KOSPI" in market.upper() else ".KQ"
        full_ticker = ticker + suffix
        
        try:
            # yfinance로 가격 데이터 가져오기
            data = yf.download(full_ticker, period="40d", progress=False)
            if len(data) < 20: continue

            # 이격도 계산
            data['MA20'] = data['Close'].rolling(window=20).mean()
            current_price = float(data['Close'].iloc[-1])
            ma20 = float(data['MA20'].iloc[-1])
            disparity = (current_price / ma20) * 100

            # 사용자 매매 기준: 이격도 90 이하
            if disparity <= 90:
                target_list.append(f"✅ **{name}** ({ticker})\n   └ 이격도: {disparity:.2f}% | 현재가: {int(current_price):,}원")
        except:
            continue

    # 결과 전송
    if target_list:
        msg = f"📢 **{today_str} 반도체 이격도 90 이하 종목**\n\n" + "\n".join(target_list)
    else:
        msg = f"ℹ️ **{today_str}**\n현재 이격도 90 이하인 반도체 종목이 없습니다."

    send_discord_message(msg)

if __name__ == "__main__":
    run_analysis()
