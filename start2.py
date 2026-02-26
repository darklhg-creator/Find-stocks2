import FinanceDataReader as fdr
import yfinance as yf
import pandas as pd
import requests
from datetime import datetime

# 사용자 디스코드 웹후크 URL
DISCORD_WEBHOOK_URL = 'https://discord.com/api/webhooks/1474739516177911979/IlrMnj_UABCGYJiVg9NcPpSVT2HoT9aMNpTsVyJzCK3yS9LQH9E0WgbYB99FHVS2SUWT'

def send_discord_message(content):
    data = {"content": content}
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=data)
    except Exception as e:
        print(f"메시지 전송 에러: {e}")

def run_analysis():
    # 현재 시점: 2026-02-26 목요일
    today_str = datetime.now().strftime('%Y-%m-%d %A')
    print(f"--- {today_str} 분석 시작 ---")
    
    try:
        # 1. 시세 데이터(Code 포함)와 상세 데이터(Sector 포함) 가져오기
        df_list = fdr.StockListing('KRX')
        df_desc = fdr.StockListing('KRX-DESC')

        # 2. 컬럼명이 달라도 대응할 수 있도록 이름 변경 후 병합
        # df_list는 'Code'를 사용, df_desc는 'Symbol'을 사용함
        df_desc = df_desc[['Symbol', 'Sector']].rename(columns={'Symbol': 'Code'})
        
        # 'Code' 컬럼을 기준으로 두 데이터 합치기
        df_krx = pd.merge(df_list, df_desc, on='Code', how='left')

        # 3. 반도체 종목 필터링
        semi_df = df_krx[df_krx['Sector'].str.contains('반도체', na=False)].copy()
        
        if semi_df.empty:
            # 만약 '반도체'로 검색이 안 되면 '전자부품' 등 유사 업종까지 포함 시도
            semi_df = df_krx[df_krx['Sector'].str.contains('전자부품|반도체', na=False)].copy()
            
    except Exception as e:
        send_discord_message(f"❌ 데이터 병합 실패: {e}\n(현재 사용 중인 데이터 컬럼 확인이 필요합니다)")
        return

    target_list = []
    
    # 4. 분석 대상 추출 (효율성을 위해 시가총액 상위 50개 우선)
    # Marcap(시가총액) 기준으로 내림차순 정렬
    semi_df = semi_df.sort_values(by='Marcap', ascending=False)

    for index, row in semi_df.head(50).iterrows():
        ticker = row['Code']
        name = row['Name']
        
        # MarketId를 기준으로 .KS(코스피) / .KQ(코스닥) 구분
        market_id = row.get('MarketId', '')
        suffix = ".KS" if market_id == "STK" else ".KQ"
        full_ticker = ticker + suffix
        
        try:
            data = yf.download(full_ticker, period="40d", progress=False)
            if len(data) < 20: continue

            data['MA20'] = data['Close'].rolling(window=20).mean()
            current_price = float(data['Close'].iloc[-1])
            ma20 = float(data['MA20'].iloc[-1])
            disparity = (current_price / ma20) * 100

            # 사용자 매매 기준: 이격도 90 이하
            if disparity <= 90:
                target_list.append(f"✅ **{name}** ({ticker})\n   └ 이격도: {disparity:.2f}% | 현재가: {int(current_price):,}원")
        except:
            continue

    # 5. 결과 전송
    if target_list:
        msg = f"📢 **{today_str} 반도체 이격도 90 이하 종목**\n\n" + "\n".join(target_list)
        msg += "\n\n💡 *영업이익 흑자 및 수급(외인/기관)을 꼭 확인하세요!*"
    else:
        msg = f"ℹ️ **{today_str}**\n현재 이격도 90 이하인 반도체 종목이 없습니다."

    send_discord_message(msg)

if __name__ == "__main__":
    run_analysis()
