import FinanceDataReader as fdr
import OpenDartReader
import requests
import pandas as pd
from datetime import datetime, timedelta
import time

# 설정
DART_API_KEY = '732bd7e69779f5735f3b9c6aae3c4140f7841c3e'
DISCORD_WEBHOOK_URL = 'https://discord.com/api/webhooks/1474739516177911979/IlrMnj_UABCGYJiVg9NcPpSVT2HoT9aMNpTsVyJzCK3yS9LQH9E0WgbYB99FHVS2SUWT'
dart = OpenDartReader(DART_API_KEY)

def send_discord_message(content):
    # 메시지가 너무 길 경우를 대비해 2000자씩 끊어서 발송
    if len(content) > 1900:
        chunks = [content[i:i+1900] for i in range(0, len(content), 1900)]
        for chunk in chunks:
            requests.post(DISCORD_WEBHOOK_URL, json={"content": chunk})
    else:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": content})

def get_disparity(code):
    try:
        # 최근 40일치 데이터 로드 (20일 이격도 계산용)
        df = fdr.DataReader(code, (datetime.now() - timedelta(days=50)).strftime('%Y-%m-%d'))
        if len(df) < 20: return None
        
        ma20 = df['Close'].rolling(window=20).mean()
        current_price = df['Close'].iloc[-1]
        disparity = (current_price / ma20.iloc[-1]) * 100
        return disparity
    except:
        return None

def check_profit_fact(corp_name):
    """최근 공시 기준 영업이익 흑자 여부 팩트체크"""
    try:
        # 2024년 사업보고서(연간) 및 2025년 3분기보고서(분기) 조회
        # 2026년 2월 기준 가장 신뢰도 높은 최신 데이터
        annual = dart.finstate_all(corp_name, 2024, '11011')
        a_op = annual[annual['account_nm'] == '영업이익']['thstrm_amount'].values[0]
        
        quarter = dart.finstate_all(corp_name, 2025, '11014')
        q_op = quarter[quarter['account_nm'] == '영업이익']['thstrm_amount'].values[0]
        
        a_val = int(a_op.replace(',', ''))
        q_val = int(q_op.replace(',', ''))
        
        # 둘 다 흑자인 경우만 통과
        if a_val > 0 and q_val > 0:
            return True, format(a_val, ','), format(q_val, ',')
        return False, 0, 0
    except:
        return False, 0, 0

def main():
    print("스크리닝 시작 (KOSPI 500 / KOSDAQ 1000)...")
    
    # 1. 대상 종목 수집 및 필터링 (ETF 제외)
    kospi = fdr.StockListing('KOSPI')
    kosdaq = fdr.StockListing('KOSDAQ')
    
    # 업종(Sector) 데이터가 있는 것만 남기면 ETF/ETN이 제거됨
    target_kospi = kospi.dropna(subset=['Sector']).head(500)
    target_kosdaq = kosdaq.dropna(subset=['Sector']).head(1000)
    
    total_targets = pd.concat([target_kospi, target_kosdaq])
    
    found_stocks = []
    
    for _, row in total_targets.iterrows():
        code, name = row['Code'], row['Name']
        
        # 1. 이격도 90 이하 필터링
        disp = get_disparity(code)
        if disp and disp <= 90:
            # 2. DART 영업이익 팩트체크
            is_ok, a_op, q_op = check_profit_fact(name)
            if is_ok:
                found_stocks.append(f"📌 **{name}** ({code})\n- 이격도: {disp:.2f}\n- '24년 영업이익: {a_op}원\n- '25년 3Q 영업이익: {q_op}원")
                print(f"찾음: {name}")
            
            # API 과부하 방지를 위한 짧은 휴식 (DART 요청 시)
            time.sleep(0.1)

    # 결과 전송
    if found_stocks:
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
        header = f"🚀 **[{now_str}] 이격도 90 이하 & 흑자 종목 스캔 결과**\n"
        send_discord_message(header + "\n" + "\n\n".join(found_stocks))
    else:
        send_discord_message("🔍 현재 조건(이격도 90 이하 & 흑자)에 부합하는 종목이 없습니다.")

if __name__ == "__main__":
    main()
