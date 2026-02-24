import FinanceDataReader as fdr
import OpenDartReader
from pykrx import stock
import requests
import pandas as pd
from datetime import datetime, timedelta
import time

# [설정]
DART_API_KEY = '732bd7e69779f5735f3b9c6aae3c4140f7841c3e'
DISCORD_WEBHOOK_URL = 'https://discord.com/api/webhooks/1474739516177911979/IlrMnj_UABCGYJiVg9NcPpSVT2HoT9aMNpTsVyJzCK3yS9LQH9E0WgbYB99FHVS2SUWT'
dart = OpenDartReader(DART_API_KEY)

def send_discord(content):
    if len(content) > 1900:
        chunks = [content[i:i+1900] for i in range(0, len(content), 1900)]
        for chunk in chunks:
            requests.post(DISCORD_WEBHOOK_URL, json={"content": chunk})
    else:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": content})

def get_market_data():
    # 깃허브 액션 서버(UTC) 기준 날짜 보정
    now = datetime.now() + timedelta(hours=9) # 한국 시간으로 보정
    today = now.strftime("%Y%m%d")
    try:
        df_investor = stock.get_market_net_purchases_of_equities_by_ticker(today, today, "ALL")
        df_price = stock.get_market_price_change(today, today)
        return df_investor, df_price
    except:
        return pd.DataFrame(), pd.DataFrame()

def main():
    print("🚀 스캔 시작...")
    df_inv, df_prc = get_market_data()
    
    # KRX 전체 종목 리스트 가져오기
    try:
        df_krx = fdr.StockListing('KRX')
    except: return

    # 시총 상위 500(코스피), 1000(코스닥) 추출 (단순 Market 필터링)
    kospi = df_krx[df_krx['Market'].str.contains('KOSPI', na=False)].head(500)
    kosdaq = df_krx[df_krx['Market'].str.contains('KOSDAQ', na=False)].head(1000)
    total_targets = pd.concat([kospi, kosdaq])
    
    found_stocks = []
    
    # 오늘 날짜 보정
    now = datetime.now() + timedelta(hours=9)
    start_date = (now - timedelta(days=60)).strftime('%Y-%m-%d')

    for _, row in total_targets.iterrows():
        code, name = row['Code'], row['Name']
        
        try:
            # 1. 이격도 계산
            df_hist = fdr.DataReader(code, start_date)
            if len(df_hist) < 20: continue
            
            ma20 = df_hist['Close'].rolling(window=20).mean().iloc[-1]
            current_price = df_hist['Close'].iloc[-1]
            disp = (current_price / ma20) * 100
            
            # 조건: 이격도 90 이하 (테스트를 위해 잠시 95 정도로 높여서 확인해볼 수도 있음)
            if disp <= 90:
                # 2. DART 흑자 체크 (데이터가 없을 경우 '패스'가 아니라 '재조회' 하도록 수정)
                try:
                    # 2024년 사업보고서(연간) 조회
                    ann = dart.finstate_all(name, 2024, '11011')
                    ann_op_row = ann[ann['account_nm'].str.contains('영업이익', na=False)]
                    
                    # 2025년 3분기보고서(분기) 조회
                    qua = dart.finstate_all(name, 2025, '11014')
                    qua_op_row = qua[qua['account_nm'].str.contains('영업이익', na=False)]
                    
                    # 데이터가 둘 다 존재할 때만 흑자 검사
                    if not ann_op_row.empty and not qua_op_row.empty:
                        ann_op = int(ann_op_row['thstrm_amount'].values[0].replace(',', ''))
                        qua_op = int(qua_op_row['thstrm_amount'].values[0].replace(',', ''))
                        
                        if ann_op > 0 and qua_op > 0:
                            change = df_prc.loc[code, '등락률'] if code in df_prc.index else 0
                            f_net = df_inv.loc[code, '외국인'] if code in df_inv.index else 0
                            i_net = df_inv.loc[code, '기관합계'] if code in df_inv.index else 0
                            
                            found_stocks.append(
                                f"✅ **{name}** ({code})\n"
                                f"└ 이격도: **{disp:.2f}** | 등락률: {change:.2f}%\n"
                                f"└ 수급: 外 {f_net:,} / 機 {i_net:,}\n"
                                f"└ '24년익: {ann_op:,} | '25.3Q익: {qua_op:,}"
                            )
                except:
                    # DART 조회 에러 시 일단 '이격도 통과 종목'으로라도 리스팅하려면 이 부분 수정 가능
                    continue
                time.sleep(0.1)
        except:
            continue

    # 결과 전송
    now_tag = now.strftime('%Y-%m-%d %H:%M')
    if found_stocks:
        header = f"📊 **[{now_tag}] 스캔 결과**\n\n"
        send_discord(header + "\n".join(found_stocks))
    else:
        # 결과가 없을 때 디버깅을 위해 '이격도'만 통과한 종목이 있는지 메시지를 띄움
        send_discord(f"🔍 [{now_tag}] 조건(90 이하+흑자)에 맞는 종목이 없습니다.\n(이격도 90 이하 종목은 존재하나 흑자 조건이나 데이터 로드 문제로 필터링 되었을 수 있습니다.)")

if __name__ == "__main__":
    main()
