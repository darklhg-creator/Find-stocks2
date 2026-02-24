import FinanceDataReader as fdr
import OpenDartReader
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
import sys
import time

# ==========================================
# 0. 사용자 설정
# ==========================================
DART_API_KEY = '732bd7e69779f5735f3b9c6aae3c4140f7841c3e'
DISCORD_WEBHOOK_URL = 'https://discord.com/api/webhooks/1474739516177911979/IlrMnj_UABCGYJiVg9NcPpSVT2HoT9aMNpTsVyJzCK3yS9LQH9E0WgbYB99FHVS2SUWT'

dart = OpenDartReader(DART_API_KEY)

# [한국 시간 설정]
KST_TIMEZONE = timezone(timedelta(hours=9))
CURRENT_KST = datetime.now(KST_TIMEZONE)
TARGET_DATE = CURRENT_KST.strftime("%Y-%m-%d")

# ==========================================
# 1. 공통 함수
# ==========================================
def send_discord_message(content):
    try:
        # 디스코드 글자수 제한(2000자) 대응
        if len(content) > 1900:
            chunks = [content[i:i+1900] for i in range(0, len(content), 1900)]
            for chunk in chunks:
                requests.post(DISCORD_WEBHOOK_URL, json={'content': chunk})
        else:
            requests.post(DISCORD_WEBHOOK_URL, json={'content': content})
    except Exception as e:
        print(f"디스코드 전송 실패: {e}")

def get_op_data(corp_name):
    """DART에서 영업이익 수치 가져오기 (단위: 억)"""
    try:
        # 24년 연간 영업이익
        res_a = dart.finstate(corp_name, 2024, '11011')
        op_a_row = res_a[res_a['account_nm'].str.contains('영업이익', na=False)]
        val_a = int(int(op_a_row.iloc[0]['thstrm_amount'].replace(',', '')) / 100000000) if not op_a_row.empty else 0
        
        # 25년 3분기 영업이익
        res_q = dart.finstate(corp_name, 2025, '11014')
        op_q_row = res_q[res_q['account_nm'].str.contains('영업이익', na=False)]
        val_q = int(int(op_q_row.iloc[0]['thstrm_amount'].replace(',', '')) / 100000000) if not op_q_row.empty else 0
        
        return val_a, val_q
    except:
        return "N/A", "N/A"

# ==========================================
# 2. 메인 로직
# ==========================================
def main():
    print(f"[{TARGET_DATE}] 이격도 90이하 종목 전수 조사 시작")

    try:
        # 1. 대상 종목 리스트 확보
        df_kospi = fdr.StockListing('KOSPI').head(500)
        df_kosdaq = fdr.StockListing('KOSDAQ').head(1000)
        df_total = pd.concat([df_kospi, df_kosdaq])
        
        results = []
        print(f"📡 총 {len(df_total)}개 종목 분석 중...")

        for idx, row in df_total.iterrows():
            code = row['Code']
            name = row['Name']
            try:
                # 이격도 계산
                df = fdr.DataReader(code).tail(30)
                if len(df) < 20: continue
                
                current_price = df['Close'].iloc[-1]
                ma20 = df['Close'].rolling(window=20).mean().iloc[-1]
                
                if ma20 == 0 or pd.isna(ma20): continue
                disparity = round((current_price / ma20) * 100, 1)

                # [조건] 이격도 90 이하인 종목은 무조건 포함
                if disparity <= 90.0:
                    ann_op, qua_op = get_op_data(name)
                    # 형식: 종목명 이격도 24년익(억) 25.3Q익(억)
                    # 예: 삼성전자 88.5 +1000 +200
                    ann_str = f"+{ann_op}" if isinstance(ann_op, int) and ann_op > 0 else f"{ann_op}"
                    qua_str = f"+{qua_op}" if isinstance(qua_op, int) and qua_op > 0 else f"{qua_op}"
                    
                    line = f"{name} {disparity} {ann_str} {qua_str}"
                    results.append(line)
                    print(f"📍 추출: {line}")
                    
                    time.sleep(0.1) # DART API 호출 간격
            except:
                continue

        # 3. 결과 전송
        if results:
            report = f"### 📉 이격도 90% 이하 종목 리스트 ({TARGET_DATE})\n"
            report += "📂 [종목명 이격도 24년영익 25.3Q영익(단위:억)]\n"
            report += "```\n" + "\n".join(results) + "\n```"
            send_discord_message(report)
            print(f"✅ {len(results)}개 종목 전송 완료.")
        else:
            send_discord_message(f"🔍 [{TARGET_DATE}] 이격도 90% 이하 종목이 없습니다.")

    except Exception as e:
        send_discord_message(f"❌ 에러 발생: {e}")

if __name__ == "__main__":
    main()
