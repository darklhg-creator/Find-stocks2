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
    today_str = datetime.now().strftime('%Y-%m-%d %A')
    print(f"--- {today_str} 분석 시작 ---")
    
    try:
        # 1. KRX 전체 종목 리스트 호출 (가장 최신 규격 반영)
        df_krx = fdr.StockListing('KRX')

        # 2. 컬럼명 유연하게 대처 (Sector가 없으면 Industry나 다른 이름 확인)
        target_col = None
        for col in ['Sector', 'Industry', 'Category', '업종']:
            if col in df_krx.columns:
                target_col = col
                break
        
        if not target_col:
            # 컬럼을 못 찾으면 현재 컬럼 목록을 디코로 보내고 종료
            cols = ", ".join(df_krx.columns)
            send_discord_message(f"❌ 데이터 구조 오류: 업종 컬럼을 찾을 수 없습니다.\n현재 컬럼: {cols}")
            return

        # 3. 업종명에 '반도체'가 포함된 종목 필터링
        semi_df = df_krx[df_krx[target_col].str.contains('반도체', na=False)].copy()
        
    except Exception as e:
        send_discord_message(f"❌ 데이터 로드 실패: {e}")
        return

    target_list = []
    
    # 4. 이격도 분석 (상위 50개 종목으로 제한하여 안정성 확보)
    for index, row in semi_df.head(50).iterrows():
        ticker = row['Code'] if 'Code' in row else row['Symbol']
        name = row['Name']
        
        # 시장 구분 (KOSPI/KOSDAQ)에 따른 티커 설정
        market = row.get('Market', '')
        suffix = ".KS" if "KOSPI" in market.upper() else ".KQ"
        full_ticker = ticker + suffix
        
        try:
            # 데이터 가져오기
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

    # 5. 결과 전송
    if target_list:
        msg = f"📢 **{today_str} 반도체 이격도 90 이하 종목**\n\n" + "\n".join(target_list)
        msg += "\n\n💡 *영업이익 흑자 및 수급(외인/기관)을 꼭 확인하세요!*"
    else:
        msg = f"ℹ️ **{today_str}**\n현재 이격도 90 이하인 반도체 종목이 없습니다."

    send_discord_message(msg)

if __name__ == "__main__":
    run_analysis()
