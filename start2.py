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
        # 24년 연간 (사업보고서)
        res_a = dart.finstate(corp_name, 2024, '11011')
        op_a_row = res_a[res_a['account_nm'].str.contains('영업이익', na=False)]
        val_a = int(int(op_a_row.iloc[0]['thstrm_amount'].replace(',', '')) / 100000000) if not op_a_row.empty else 0
        
        # 25년 3분기 (3분기보고서)
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
    print(f"[{TARGET_DATE}] 고속 분석 시작 (KOSPI 50 / KOSDAQ 100)")

    try:
        # 상위 종목 필터링 (시총 순서로 가져옴)
        df_kospi = fdr.StockListing('KOSPI').head(50)
        df_kosdaq = fdr.StockListing('KOSDAQ').head(100)
        df_total = pd.concat([df_kospi, df_kosdaq])
        
        results_list = []
        print(f"📡 총 {len(df_total)}개 핵심 종목 분석 중...")

        for idx, row in df_total.iterrows():
            code, name = row['Code'], row['Name']
            try:
                # 이격도 계산 (최근 30일 데이터 활용)
                df = fdr.DataReader(code).tail(30)
                if len(df) < 20: continue
                
                ma20 = df['Close'].rolling(window=20).mean().iloc[-1]
                disparity = round((df['Close'].iloc[-1] / ma20) * 100, 1)

                # [필터] 이격도 90 이하
                if disparity <= 90.0:
                    ann_op, qua_op = get_op_data(name)
                    
                    # 수치 문자열 처리 (+ 부호 추가)
                    a_str = f"+{ann_op}" if isinstance(ann_op, int) and ann_op > 0 else f"{ann_op}"
                    q_str = f"+{qua_op}" if isinstance(qua_op, int) and qua_op > 0 else f"{qua_op}"
                    
                    results_list.append({
                        'name': name[:8],
                        'disp': disparity,
                        'ann': a_str,
                        'qua': q_str
                    })
                    print(f"📍 발견: {name} ({disparity})")
                    time.sleep(0.1)
            except:
                continue

        # 3. 디스코드 표 형식 구성
        if results_list:
            # 이격도 낮은 순으로 정렬
            results_list = sorted(results_list, key=lambda x: x['disp'])
            
            table_header = f"{'종목명':<10} | {'이격':<5} | {'24년익':>7} | {'25.3Q':>7}\n"
            table_header += "-" * 45 + "\n"
            
            table_body = ""
            for r in results_list:
                table_body += f"{r['name']:<10} | {r['disp']:<5} | {r['ann']:>8} | {r['qua']:>8}\n"
            
            report = f"### 📊 핵심 종목 이격도 분석 ({TARGET_DATE})\n"
            report += "```\n" + table_header + table_body + "```"
            send_discord_message(report)
            print(f"✅ {len(results_list)}개 종목 전송 완료.")
        else:
            send_discord_message(f"🔍 [{TARGET_DATE}] 상위 150개 중 이격도 90% 이하 종목이 없습니다.")

    except Exception as e:
        send_discord_message(f"❌ 실행 중 에러 발생: {e}")

if __name__ == "__main__":
    main()
