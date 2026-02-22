import pandas as pd
import FinanceDataReader as fdr
import requests
from datetime import datetime, timedelta
import warnings
import json
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import unquote

warnings.filterwarnings('ignore')

# ✅ 환경 설정
RAW_KEY = "62e0d95b35661ef8e1f9a665ef46cc7cd64a3ace4d179612dda40c847f6bdb7e"
PUBLIC_API_KEY = unquote(RAW_KEY) 
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1474739516177911979/IlrMnj_UABCGYJiVg9NcPpSVT2HoT9aMNpTsVyJzCK3yS9LQH9E0WgbYB99FHVS2SUWT"

def get_investor_data_public(ticker_name):
    """공공데이터 API: 최근 3일 수급 추출 및 양매수 여부 판별"""
    try:
        url = "http://apis.data.go.kr/1160100/service/GetStockSecuritiesInfoService/getInvestorRegistrationStat"
        today = datetime.now()
        start_dt = (today - timedelta(days=10)).strftime('%Y%m%d')
        params = {
            'serviceKey': PUBLIC_API_KEY, 'resultType': 'json',
            'itmsNm': ticker_name, 'beginBasDt': start_dt, 'numOfRows': '10'
        }
        res = requests.get(url, params=params, timeout=15)
        data = res.json()
        items = data['response']['body']['items']['item']
        if isinstance(items, dict): items = [items]
        items = sorted(items, key=lambda x: x['basDt'], reverse=True)
        
        inst_sum, frgn_sum = 0, 0
        for i in range(min(3, len(items))):
            inst_sum += int(items[i]['insttnPurNetQty'])
            frgn_sum += int(items[i]['frgnPurNetQty'])
            
        def format_val(val):
            if abs(val) >= 10000: return f"{'+' if val > 0 else ''}{round(val/10000, 1)}만"
            return f"{'+' if val > 0 else ''}{val}"
            
        is_hot = (frgn_sum > 0 and inst_sum > 0)
        return f"외인{format_val(frgn_sum)} / 기관{format_val(inst_sum)}", is_hot, (inst_sum + frgn_sum)
    except:
        return "조회지연", False, 0

def is_recent_operating_profit_positive(ticker_code):
    """최신 공시 기준 영업이익 흑자 확인 (Naver Finance 크롤링)"""
    try:
        url = f"https://finance.naver.com/item/main.naver?code={ticker_code}"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        tables = pd.read_html(res.text, encoding='euc-kr')
        for df in tables:
            df.columns = [str(c) for c in df.columns]
            if any('영업이익' in str(row) for row in df.iloc[:,0]):
                val = pd.to_numeric(df.iloc[0, 1:11], errors='coerce').dropna()
                if len(val) > 0: return val.iloc[-1] > 0
        return False
    except: return False

def analyze_stock(args):
    """폭풍전야: 일/주/월 추세 통합 및 단일 거래일 급등 배제 엔진"""
    ticker, name, end_date = args
    try:
        # 중장기 추세(주/월봉) 확인을 위해 충분한 데이터 로드
        df = fdr.DataReader(ticker, (end_date - timedelta(days=600)), end_date)
        if len(df) < 100: return None
        
        df['Val'] = df['Close'] * df['Volume']
        df['MA20_Price'] = df['Close'].rolling(window=20).mean()
        df['MA20_Vol'] = df['Volume'].rolling(window=20).mean()
        
        curr = df.iloc[-1]
        prev_close = df['Close'].iloc[-2]
        vol_ratio = (curr['Volume'] / df['MA20_Vol'].iloc[-1]) * 100
        day_return = (curr['Close'] - prev_close) / prev_close
        val_median = df['Val'].tail(20).median()
        val_count_10b = (df['Val'].tail(20) >= 1000000000).sum()

        # 🚀 [업데이트된 필터] 최근 5거래일 중 하루라도 10% 이상 급등 시 배제
        recent_5d_daily_returns = df['Close'].tail(6).pct_change().dropna()
        if (recent_5d_daily_returns >= 0.10).any(): return None

        # 🌪️ [기본 필터]
        if curr['Close'] < df['MA20_Price'].iloc[-1]: return None
        if abs(day_return) > 0.03: return None
        if vol_ratio > 35: return None
        if val_median < 1500000000: return None
        if val_count_10b < 15: return None

        # 🚀 [중장기 추세 필터] 주봉/월봉 MA20 위에서 지지받는지 확인
        df_weekly = df['Close'].resample('W').last()
        w_ma20 = df_weekly.rolling(window=20).mean().iloc[-1]
        df_monthly = df['Close'].resample('M').last()
        m_ma20 = df_monthly.rolling(window=20).mean().iloc[-1]

        if curr['Close'] < w_ma20 or curr['Close'] < m_ma20: return None

        # [Saved Info 1.2] 최신 공시 기준 영업이익 흑자 확인
        if is_recent_operating_profit_positive(ticker):
            supply_info, is_hot, total_qty = get_investor_data_public(name)
            return {
                'Name': name, 'Code': ticker, 'Ratio': round(vol_ratio, 1), 
                'MedianVal': round(val_median / 100000000, 1), 
                'Return': round(day_return * 100, 2),
                'Supply': supply_info, 'IsHot': is_hot, 'TotalQty': total_qty
            }
    except: return None

def main():
    print(f"🚀 [폭풍전야] 단일 급등 배제 및 중장기 추세 엔진 가동...")
    krx_df = fdr.StockListing('KRX') # [Saved Info 1.1] 국내 주식 대상
    krx_df = krx_df[krx_df['Code'].str.match(r'^\d{5}0$')]
    ticker_dict = dict(zip(krx_df['Code'], krx_df['Name']))
    end_date = datetime.today()
    
    tasks = [(t, n, end_date) for t, n in ticker_dict.items()]
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(analyze_stock, tasks))
    
    all_picks = [r for r in results if r is not None]
    final_picks = sorted(all_picks, key=lambda x: x['Ratio'])[:30]
    
    # 양매수 강도 TOP 3 추출
    top3_hot = sorted([p for p in final_picks if p['IsHot']], key=lambda x: x['TotalQty'], reverse=True)[:3]
    
    if not final_picks:
        msg = f"📅 {end_date.strftime('%Y-%m-%d')} | 조건을 만족하는 종목 없음"
    else:
        msg = f"🌪️ **[폭풍전야: 정밀 필터링 TOP {len(final_picks)}]**\n"
        msg += "*(로직: 흑자+20선위+거래급감+단일급등배제+주/월봉 우상향)*\n\n"
        
        if top3_hot:
            msg += "🔥 **양매수 집중 종목 TOP 3**\n"
            for i, p in enumerate(top3_hot):
                msg += f"> {i+1}위: **{p['Name']}** ({p['Supply']})\n"
            msg += "\n"
            
        for p in final_picks:
            star = "⭐" if p['IsHot'] else ""
            msg += f"• {star}**{p['Name']}**({p['Code']}) | `{p['Ratio']}%` | `{p['MedianVal']}억` | `{p['Return']}%` | `[{p['Supply']}]` \n"

    try:
        headers = {'Content-Type': 'application/json'}
        requests.post(DISCORD_WEBHOOK_URL, data=json.dumps({"content": msg}), headers=headers)
        print("✅ 디스코드 전송 완료!")
    except:
        print("❌ 전송 실패")

if __name__ == "__main__":
    main()
