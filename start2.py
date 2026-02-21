import pandas as pd
import FinanceDataReader as fdr
import requests
from datetime import datetime, timedelta
import warnings
import json
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import unquote # 인코딩 방지용

warnings.filterwarnings('ignore')

# ✅ 반드시 마이페이지의 'Decoding' 키를 복사해서 아래에 넣으세요
# (키에 % 문자가 포함되어 있다면 Encoding 키일 확률이 높습니다)
RAW_KEY = "62e0d95b35661ef8e1f9a665ef46cc7cd64a3ace4d179612dda40c847f6bdb7e"
PUBLIC_API_KEY = unquote(RAW_KEY) # 이미 인코딩된 경우를 대비해 해제 후 재사용

DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1474739516177911979/IlrMnj_UABCGYJiVg9NcPpSVT2HoT9aMNpTsVyJzCK3yS9LQH9E0WgbYB99FHVS2SUWT"

def get_investor_data_public(ticker_name):
    """공공데이터 API 강화 버전"""
    try:
        url = "http://apis.data.go.kr/1160100/service/GetStockSecuritiesInfoService/getInvestorRegistrationStat"
        
        # 주말 고려 10일치 조회
        today = datetime.now()
        start_dt = (today - timedelta(days=10)).strftime('%Y%m%d')
        
        params = {
            'serviceKey': PUBLIC_API_KEY,
            'resultType': 'json',
            'itmsNm': ticker_name,
            'beginBasDt': start_dt,
            'numOfRows': '10'
        }
        
        # verify=False와 timeout 연장으로 안정성 확보
        res = requests.get(url, params=params, timeout=15)
        
        # 만약 API가 XML 에러를 뱉는다면 (인증키 문제)
        if res.text.startswith("<"):
            return "키활성화대기", False
            
        data = res.json()
        items = data['response']['body']['items']['item']
        
        if not items: return "데이터없음", False
        
        items = sorted(items, key=lambda x: x['basDt'], reverse=True)
        
        inst_sum, frgn_sum = 0, 0
        for i in range(min(3, len(items))):
            inst_sum += int(items[i]['insttnPurNetQty'])
            frgn_sum += int(items[i]['frgnPurNetQty'])
            
        def format_val(val):
            if abs(val) >= 10000: return f"{'+' if val > 0 else ''}{round(val/10000, 1)}만"
            return f"{'+' if val > 0 else ''}{val}"
            
        is_hot = (frgn_sum > 0 or inst_sum > 0)
        return f"외인{format_val(frgn_sum)} / 기관{format_val(inst_sum)}", is_hot
    except Exception as e:
        # 에러 종류를 조금 더 구체적으로 표기하여 원인 파악
        return "조회지연", False

# ... (나머지 analyze_stock, is_recent_operating_profit_positive, main 함수는 동일)
