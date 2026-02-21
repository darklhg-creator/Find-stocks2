import pandas as pd
import FinanceDataReader as fdr
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import time
import warnings

# 불필요한 경고 메시지 끄기
warnings.filterwarnings('ignore')

def get_rsi(df, period=14):
    """지수이동평균(EMA) 방식의 RSI 계산 (HTS/MTS와 동일한 방식)"""
    delta = df['Close'].diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    
    # EMA를 사용하여 변동성 계산
    ema_up = up.ewm(com=period-1, adjust=False).mean()
    ema_down = down.ewm(com=period-1, adjust=False).mean()
    
    rs = ema_up / ema_down
    rsi = 100 - (100 / (1 + rs))
    return rsi

def is_recent_operating_profit_positive(ticker_code):
    """네이버 금융 스크래핑을 통해 가장 최근 공시 기준 영업이익 흑자 여부 확인"""
    try:
        url = f"https://finance.naver.com/item/main.naver?code={ticker_code}"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        res = requests.get(url, headers=headers)
        
        # lxml 엔진을 사용하여 테이블 추출
        tables = pd.read_html(res.text, encoding='euc-kr')
        
        # '기업실적분석' 테이블은 보통 4번째(인덱스 3)에 위치함
        finance_table = tables[3]
        
        # 다중 인덱스 평탄화 및 '영업이익' 행 찾기
        finance_table.columns = ['_'.join(str(c) for c in col).strip() for col in finance_table.columns]
        op_row = finance_table[finance_table.iloc[:, 0].str.contains('영업이익', na=False)]
        
        if op_row.empty:
            return False
            
        # 가장 최근 4개의 실적 데이터 중 마지막 값(최신 공시) 확인
        recent_values = pd.to_numeric(op_row.iloc[0, -4:], errors='coerce').dropna()
        
        if len(recent_values) > 0:
            return recent_values.iloc[-1] > 0 # 흑자면 True
            
        return False
    except:
        return False

def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 국내 주식 주도주 및 낙폭과대 탐색 시작")
    
    # 1. 국내 상장 종목 리스트 (보통주만 필터링)
    try:
        krx_df = fdr.StockListing('KRX')
        # 종목코드가 6자리 숫자로 끝나고 '0'으로 끝나는 보통주만 선택
        krx_df = krx_df[krx_df['Code'].str.match(r'^\d{5}0$')]
        ticker_dict = dict(zip(krx_df['Code'], krx_df['Name']))
    except Exception as e:
        print(f"종목 리스트 확보 실패: {e}")
        return

    # 분석 범위: 최근 120일 데이터
    end_date = datetime.today()
    start_date = end_date - timedelta(days=120)
    
    # 필터링 기준 설정
    MIN_MEDIAN_TRADING_VALUE = 3000000000  # 20일 거래대금 중간값 30억 원 이상
    TARGET_RSI = 40                        # RSI 40 이하 (과매도 구간 진입)
    
    candidates = []
    tickers = list(ticker_dict.keys())
    
    print(f"총 {len(tickers)}개 종목 분석 중... (거래대금 중간값 및 RSI 필터링)")

    for ticker in tickers:
        try:
            df = fdr.DataReader(ticker, start_date, end_date)
            if len(df) < 30: continue
            
            # 거래대금 중간값 계산 (평균의 함정 회피)
            df['Trading_Value'] = df['Close'] * df['Volume']
            recent_median = df['Trading_Value'].rolling(window=20).median().iloc[-1]
            
            if recent_median < MIN_MEDIAN_TRADING_VALUE:
                continue
                
            # RSI 지표 계산
            df['RSI'] = get_rsi(df)
            current_rsi = df['RSI'].iloc[-1]
            
            if current_rsi <= TARGET_RSI:
                candidates.append({
                    'Code': ticker,
                    'Name': ticker_dict[ticker],
                    'RSI': round(current_rsi, 2),
                    '거래대금_중간값(억)': round(recent_median / 100000000, 1)
                })
        except:
            continue

    print(f"\n✅ 기술적 조건 통과: {len(candidates)}종목. 이제 실시간 영업이익 흑자 여부를 검증합니다.")
    
    final_picks = []
    for cand in candidates:
        # 네이버 금융 데이터로 최신 영업이익 확인
        if is_recent_operating_profit_positive(cand['Code']):
            final_picks.append(cand)
        time.sleep(0.1) # 서버 부하 방지용 짧은 휴식

    # 결과 출력
    print("\n" + "="*70)
    print(f"🏆 최종 필터링 결과 (RSI {TARGET_RSI} 이하 & 유동성 우량 & 흑자 기업)")
    print("="*70)
    
    if not final_picks:
        print("현재 조건에 부합하는 종목이 없습니다.")
    else:
        result_df = pd.DataFrame(final_picks)
        # RSI가 낮은 순(더 많이 과매도된 순)으로 정렬
        result_df = result_df.sort_values(by='RSI').reset_index(drop=True)
        print(result_df.to_string(index=False))
    print("="*70)

if __name__ == "__main__":
    main()
