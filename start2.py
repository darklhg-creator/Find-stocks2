import pandas as pd
import FinanceDataReader as fdr
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import time
import warnings
import json

# 경고 메시지 무시
warnings.filterwarnings('ignore')

# ==========================================
# 설정 구간: 여기에 디스코드 웹후크 URL을 입력하세요
# ==========================================
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1474739516177911979/IlrMnj_UABCGYJiVg9NcPpSVT2HoT9aMNpTsVyJzCK3yS9LQH9E0WgbYB99FHVS2SUWT" 

def get_rsi(df, period=14):
    """지수이동평균(EMA) 방식의 RSI 계산"""
    delta = df['Close'].diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ema_up = up.ewm(com=period-1, adjust=False).mean()
    ema_down = down.ewm(com=period-1, adjust=False).mean()
    rs = ema_up / ema_down
    return 100 - (100 / (1 + rs))

def is_recent_operating_profit_positive(ticker_code):
    """네이버 금융을 통해 최신 공시 기준 영업이익 흑자 여부 확인"""
    try:
        url = f"https://finance.naver.com/item/main.naver?code={ticker_code}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers)
        tables = pd.read_html(res.text, encoding='euc-kr')
        finance_table = tables[3]
        finance_table.columns = ['_'.join(str(c) for c in col).strip() for col in finance_table.columns]
        op_row = finance_table[finance_table.iloc[:, 0].str.contains('영업이익', na=False)]
        
        if op_row.empty: return False
        recent_values = pd.to_numeric(op_row.iloc[0, -4:], errors='coerce').dropna()
        return recent_values.iloc[-1] > 0 if len(recent_values) > 0 else False
    except:
        return False

def send_discord_message(payload):
    """디스코드로 분석 결과 전송"""
    if DISCORD_WEBHOOK_URL == "YOUR_DISCORD_WEBHOOK_URL_HERE":
        print("⚠️ 디스코드 웹후크 URL이 설정되지 않았습니다. 결과만 출력합니다.")
        return
    
    response = requests.post(
        DISCORD_WEBHOOK_URL, 
        data=json.dumps(payload),
        headers={'Content-Type': 'application/json'}
    )
    if response.status_code == 204:
        print("✅ 디스코드 메시지 전송 성공!")
    else:
        print(f"❌ 전송 실패: {response.status_code}")

def main():
    print("🚀 주식 분석 및 디스코드 알림 프로세스 시작...")
    
    try:
        krx_df = fdr.StockListing('KRX')
        krx_df = krx_df[krx_df['Code'].str.match(r'^\d{5}0$')]
        ticker_dict = dict(zip(krx_df['Code'], krx_df['Name']))
    except Exception as e:
        print(f"데이터 로드 실패: {e}")
        return

    end_date = datetime.today()
    start_date = end_date - timedelta(days=120)
    
    # 필터 조건: 중간값 30억 이상, RSI 40 이하
    MIN_MEDIAN_VALUE = 3000000000 
    TARGET_RSI = 40
    
    candidates = []
    tickers = list(ticker_dict.keys())
    
    for ticker in tickers:
        try:
            df = fdr.DataReader(ticker, start_date, end_date)
            if len(df) < 30: continue
            
            # 거래대금 중간값 (평균의 함정 방지)
            df['Value'] = df['Close'] * df['Volume']
            recent_median = df['Value'].rolling(window=20).median().iloc[-1]
            
            if recent_median < MIN_MEDIAN_VALUE: continue
                
            df['RSI'] = get_rsi(df)
            current_rsi = df['RSI'].iloc[-1]
            
            if current_rsi <= TARGET_RSI:
                candidates.append({
                    'Code': ticker,
                    'Name': ticker_dict[ticker],
                    'RSI': round(current_rsi, 2),
                    'Value': round(recent_median / 100000000, 1)
                })
        except:
            continue

    # 흑자 기업 검증
    final_picks = [c for c in candidates if is_recent_operating_profit_positive(c['Code'])]
    
    # 디스코드 메시지 구성
    if not final_picks:
        message = f"📅 {end_date.strftime('%Y-%m-%d')} 분석 결과\n조건에 맞는 종목이 없습니다."
    else:
        message = f"🏆 **{end_date.strftime('%Y-%m-%d')} 우량 낙폭과대 종목** 🏆\n"
        message += "*(조건: RSI 40이하, 거래대금 중간값 30억↑, 영업이익 흑자)*\n\n"
        for p in final_picks:
            message += f"• **{p['Name']}**({p['Code']}) | RSI: `{p['RSI']}` | 거래대금(중간): `{p['Value']}억` \n"

    # 전송
    send_discord_message({"content": message})
    print(message)

if __name__ == "__main__":
    main()
