import FinanceDataReader as fdr
import yfinance as yf
import pandas as pd
import requests
from datetime import datetime

# 사용자님이 제공하신 디스코드 웹후크 URL
DISCORD_WEBHOOK_URL = 'https://discord.com/api/webhooks/1474739516177911979/IlrMnj_UABCGYJiVg9NcPpSVT2HoT9aMNpTsVyJzCK3yS9LQH9E0WgbYB99FHVS2SUWT'

def send_discord_message(content):
    data = {"content": content}
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=data)
        return response.status_code
    except Exception as e:
        print(f"메시지 전송 에러: {e}")

def run_analysis():
    # 2026-02-26 목요일 체크
    today_str = datetime.now().strftime('%Y-%m-%d %A')
    print(f"--- {today_str} 반도체 이격도 분석 시작 ---")
    
    try:
        # 한국거래소 종목 리스트
        df_krx = fdr.StockListing('KRX')
        # 업종명에 '반도체'가 포함된 종목만 추출
        semi_df = df_krx[df_krx['Sector'].str.contains('반도체', na=False)].copy()
    except Exception as e:
        send_discord_message(f"❌ 데이터 로드 실패: {e}")
        return

    target_list = []
    
    # 시가총액 상위 100개 중 이격도 낮은 것 탐색 (실행 시간 고려)
    for _, row in semi_df.head(100).iterrows():
        ticker = row['Symbol']
        name = row['Name']
        full_ticker = ticker + (".KS" if row['Market'] == 'KOSPI' else ".KQ")
        
        try:
            # 최근 40일치 데이터로 20일 이동평균 계산
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

    # 디스코드 전송
    if target_list:
        msg = f"📢 **{today_str} 반도체 이격도 90 이하 종목**\n\n" + "\n".join(target_list)
        msg += "\n\n💡 *영업이익 흑자 및 수급(외인/기관)을 꼭 확인하세요!*"
    else:
        msg = f"ℹ️ **{today_str}**\n현재 이격도 90 이하인 반도체 종목이 없습니다."

    send_discord_message(msg)

if __name__ == "__main__":
    run_analysis()
