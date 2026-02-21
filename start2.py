import pandas as pd
import FinanceDataReader as fdr
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import time
import warnings

# 경고 메시지 숨기기 (가독성 향상)
warnings.filterwarnings('ignore')

def get_rsi(df, period=14):
    """
    일반적인 HTS/MTS와 동일한 지수이동평균(EMA) 방식의 RSI 계산 함수
    """
    delta = df['Close'].diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    
    # com = period - 1
    ema_up = up.ewm(com=period-1, adjust=False).mean()
    ema_down = down.ewm(com=period-1, adjust=False).mean()
    
    rs = ema_up / ema_down
    rsi = 100 - (100 / (1 + rs))
    return rsi

def is_recent_operating_profit_positive(ticker_code):
    """
    네이버 금융을 스크래핑하여 가장 최근 발표된 공시 기준 영업이익이 흑자인지 확인
    (연간/분기 실적 테이블을 우선적으로 확인)
    """
    try:
        url = f"https://finance.naver.com/item/main.naver?code={ticker_code}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers)
        
        # 네이버 금융 메인 페이지의 재무제표 표 추출
        tables = pd.read_html(res.text, encoding='euc-kr')
        
        # 일반적으로 3번째(인덱스 3) 표가 '기업실적분석' 테이블입니다.
        finance_table = tables[3]
        
        # 다중 컬럼 인덱스를 평탄화
        finance_table.columns = ['_'.join(str(c) for c in col).strip() for col in finance_table.columns]
        
        # '영업이익'이 포함된 행 찾기
        op_row = finance_table[finance_table.iloc[:, 0].str.contains('영업이익', na=False)]
        
        if op_row.empty:
            return False # 데이터를 찾을 수 없으면 보수적으로 제외
            
        # 가장 최근 분기 또는 연간 데이터 값 추출 (보통 오른쪽 끝에서 두 번째 또는 세 번째 열이 최근 실적)
        # NaN이나 텍스트를 제거하고 숫자로 변환
        recent_values = pd.to_numeric(op_row.iloc[0, -4:], errors='coerce').dropna()
        
        if len(recent_values) > 0:
            latest_op = recent_values.iloc[-1]
            return latest_op > 0 # 영업이익이 0보다 크면 True (흑자)
            
        return False
        
    except Exception as e:
        print(f"[{ticker_code}] 재무 데이터 확인 중 오류 발생: {e}")
        return False

def main():
    print("=== 국내 주식 낙폭과대(RSI 40 이하) & 우량 유동성 & 흑자 기업 검색 시작 ===")
    
    # 1. 국내 주식(코스피, 코스닥) 종목 코드 가져오기
    krx_df = fdr.StockListing('KRX')
    
    # 우선주, 스팩주 등 제외 (종목코드가 6자리 숫자로 끝나고, 마지막이 0인 보통주만 필터링)
    krx_df = krx_df[krx_df['Code'].str.match(r'^\d{5}0$')]
    tickers = krx_df['Code'].tolist()
    names = krx_df['Name'].tolist()
    ticker_dict = dict(zip(tickers, names))
    
    # 분석 기준일 설정 (오늘 기준으로 100일 전까지의 데이터만 가져와서 속도 향상)
    end_date = datetime.today()
    start_date = end_date - timedelta(days=100)
    
    # 필터링 조건
    MIN_MEDIAN_TRADING_VALUE = 3000000000  # 20일 중간값 기준 30억 원 이상
    TARGET_RSI = 40                        # RSI 40 이하
    
    candidates = []
    
    print(f"총 {len(tickers)}개 보통주 종목에 대해 1차 기술적 필터링(RSI 및 중간값)을 진행합니다. 잠시만 기다려주세요...\n")
    
    for i, ticker in enumerate(tickers):
        try:
            # 주가 데이터 수집
            df = fdr.DataReader(ticker, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
            
            if len(df) < 30: # 상장한 지 얼마 안 된 종목 제외
                continue
                
            # 1. 거래대금 중간값 조건 (평균의 함정 회피)
            df['Trading_Value'] = df['Close'] * df['Volume']
            # 최근 20일 거래대금의 '중간값' 계산
            recent_median_value = df['Trading_Value'].rolling(window=20).median().iloc[-1]
            
            if recent_median_value < MIN_MEDIAN_TRADING_VALUE:
                continue
                
            # 2. RSI 조건 확인
            df['RSI'] = get_rsi(df)
            current_rsi = df['RSI'].iloc[-1]
            
            if current_rsi <= TARGET_RSI:
                # 1차 조건 통과한 종목만 리스트에 추가
                candidates.append({
                    'Code': ticker,
                    'Name': ticker_dict[ticker],
                    'RSI': round(current_rsi, 2),
                    'Median_Value(억)': round(recent_median_value / 100000000, 1)
                })
                
        except Exception as e:
            continue
            
    print(f"\n1차 조건(유동성 중간값 충족 & RSI {TARGET_RSI} 이하)을 통과한 종목은 총 {len(candidates)}개입니다.")
    print("이제 해당 종목들의 가장 최근 공시 기준 '영업이익 흑자' 여부를 실시간으로 확인합니다...\n")
    
    final_picks = []
    
    for idx, cand in enumerate(candidates):
        ticker = cand['Code']
        name = cand['Name']
        print(f"[{idx+1}/{len(candidates)}] {name}({ticker}) 영업이익 확인 중...", end="")
        
        # 3. 최근 공시 기준 영업이익 흑자 확인 (네이버 금융 실시간 스크래핑)
        if is_recent_operating_profit_positive(ticker):
            print(" 흑자 확인! (편입)")
            final_picks.append(cand)
        else:
            print(" 적자 또는 데이터 없음 (제외)")
            
        time.sleep(0.5) # 서버 부하 방지를 위한 딜레이
        
    print("\n" + "="*50)
    print("🏆 [최종 검색 결과] 🏆")
    print("="*50)
    if not final_picks:
        print("현재 모든 조건을 만족하는 종목이 없습니다.")
    else:
        result_df = pd.DataFrame(final_picks)
        # RSI가 낮은 순으로 정렬하여 출력
        result_df = result_df.sort_values(by='RSI', ascending=True).reset_index(drop=True)
        print(result_df.to_string())

if __name__ == "__main__":
    main()
