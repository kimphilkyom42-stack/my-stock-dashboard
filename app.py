import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials
import json
import requests
import re
from bs4 import BeautifulSoup

# ==========================================
# 1. 페이지 기본 설정
# ==========================================
st.set_page_config(page_title="나의 주식 포트폴리오", layout="wide")

# ==========================================
# 2. 구글 스프레드시트 연결 설정
# ==========================================
@st.cache_resource
def init_connection():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(st.secrets["gcp_service_account_json"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    sheet_url = st.secrets["google_sheet_url"]
    return client.open_by_url(sheet_url)

# ==========================================
# 3. 구글 시트 안전 저장 함수
# ==========================================
def update_google_sheet(sheet, dataframe):
    sheet.clear()
    # 1. 데이터를 복사한 뒤, 숫자가 들어가야 할 곳을 명확히 지정 (문자열 방지)
    clean_df = dataframe.copy()
    clean_df['매수단가'] = pd.to_numeric(clean_df['매수단가'], errors='coerce').fillna(0.0)
    clean_df['보유수량'] = pd.to_numeric(clean_df['보유수량'], errors='coerce').fillna(0.0)
    
    # 2. 파이썬 기본 리스트 형태로 완벽히 변환
    save_data = [clean_df.columns.tolist()] + clean_df.values.tolist()
    
    # 3. gspread 버전 오류를 막기 위해 시작점(A1)을 명시하여 덮어쓰기
    sheet.update(values=save_data, range_name="A1")

# ==========================================
# 4. 실시간 환율 불러오기 (★오류 수정 반영됨★)
# ==========================================
@st.cache_data(ttl=60)
def get_exchange_rate():
    try:
        ticker = yf.Ticker("KRW=X")
        # 빈 데이터 방지를 위해 최근 5일치 호출
        hist = ticker.history(period="5d")
        
        if not hist.empty:
            rate = hist['Close'].iloc[-1]
            return float(rate)
        else:
            return 1350.0 
    except Exception as e:
        print(f"환율 API 에러 발생: {e}")
        return 1350.0

exchange_rate = get_exchange_rate()

# ==========================================
# 5. 야후 파이낸스 검색 API
# ==========================================
def search_ticker(keyword):
    if re.match(r'^\d{6}$', keyword):
        for suffix in ['.KS', '.KQ']:
            test_ticker = f"{keyword}{suffix}"
            try:
                stock = yf.Ticker(test_ticker)
                if not stock.history(period="1d").empty:
                    name = stock.info.get('shortName', test_ticker)
                    return test_ticker, name
            except:
                continue
            
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={keyword}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        quotes = data.get('quotes', [])
        if quotes:
            symbol = quotes[0]['symbol']
            name = quotes[0].get('shortname', keyword)
            return symbol, name
    except Exception as e:
        pass
    return None, None

# ==========================================
# 6. 사이드바: 사용자 관리
# ==========================================
doc = init_connection()

st.sidebar.header("👥 사용자 관리")
worksheets = doc.worksheets()
user_list = [ws.title for ws in worksheets]

# 6-1. 사용자 선택
selected_user = st.sidebar.selectbox("조회할 사람을 선택하세요", user_list)

# 6-2. 선택된 사용자 설정 (순서 변경 및 삭제)
with st.sidebar.expander(f"⚙️ '{selected_user}'님 설정 (순서/삭제)"):
    current_idx = user_list.index(selected_user)
    
    st.markdown("##### ↕️ 순서 변경")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("⬆️ 위로", disabled=(current_idx == 0), use_container_width=True):
            user_list[current_idx], user_list[current_idx-1] = user_list[current_idx-1], user_list[current_idx]
            ordered_worksheets = [doc.worksheet(name) for name in user_list]
            doc.reorder_worksheets(ordered_worksheets)
            st.rerun()
            
    with col2:
        if st.button("⬇️ 아래로", disabled=(current_idx == len(user_list) - 1), use_container_width=True):
            user_list[current_idx], user_list[current_idx+1] = user_list[current_idx+1], user_list[current_idx]
            ordered_worksheets = [doc.worksheet(name) for name in user_list]
            doc.reorder_worksheets(ordered_worksheets)
            st.rerun()

    st.divider()
    
    st.markdown("##### 🗑️ 사용자 삭제")
    st.warning("⚠️ 삭제 시 데이터는 복구할 수 없습니다.")
    if st.button("❌ 현재 사용자 삭제", type="primary", use_container_width=True):
        if len(user_list) <= 1:
            st.error("최소 1명의 사용자는 남아있어야 합니다.")
        else:
            ws_to_delete = doc.worksheet(selected_user)
            doc.del_worksheet(ws_to_delete)
            st.success(f"'{selected_user}'님이 삭제되었습니다.")
            st.rerun()

st.sidebar.divider()

# 6-3. 새로운 사용자 추가
new_user = st.sidebar.text_input("새로운 사람 추가 (이름 입력 후 Enter)")
if new_user:
    if new_user not in user_list:
        doc.add_worksheet(title=new_user, rows="100", cols="20")
        st.sidebar.success(f"'{new_user}'님이 추가되었습니다! 새로고침 해주세요.")
        st.rerun()
    else:
        st.sidebar.warning("이미 존재하는 이름입니다.")

st.sidebar.info(f"💵 현재 적용 환율\n**1달러 = {exchange_rate:,.2f}원**")
st.sidebar.success(f"현재 접속 중: **{selected_user}**")

st.title(f"📈 {selected_user}님의 주식 대시보드")

# ==========================================
# 7. 데이터 불러오기 및 타입 보정
# ==========================================
worksheet = doc.worksheet(selected_user)
data = worksheet.get_all_records()

if data:
    df = pd.DataFrame(data)
else:
    df = pd.DataFrame(columns=["종목명", "티커", "매수단가", "보유수량"])

# 빈칸 등으로 꼬인 데이터를 숫자형으로 강제 초기화
df['매수단가'] = pd.to_numeric(df.get('매수단가', []), errors='coerce').fillna(0.0)
df['보유수량'] = pd.to_numeric(df.get('보유수량', []), errors='coerce').fillna(0.0)

# ==========================================
# 8. 종목 검색 및 자동 추가 폼
# ==========================================
st.subheader("🔍 새 종목 검색 및 자동 추가")
with st.form("add_stock_form", clear_on_submit=True):
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        search_keyword = st.text_input("종목명 (한국주식은 6자리 코드, 미국은 이름/티커)")
    with col2:
        buy_price = st.number_input("매수단가 (미국주식은 달러 기준 입력)", min_value=0.0, step=1.0)
    with col3:
        quantity = st.number_input("보유수량", min_value=0.0, step=1.0)
    
    submitted = st.form_submit_button("검색하여 포트폴리오에 추가")
    
    if submitted and search_keyword:
        with st.spinner(f"종목코드를 찾는 중..."):
            found_ticker, official_name = search_ticker(search_keyword)
            if found_ticker:
                st.success(f"✅ 추가 완료! '{official_name}' ({found_ticker})")
                new_row = pd.DataFrame([{
                    "종목명": official_name, "티커": found_ticker, 
                    "매수단가": float(buy_price), "보유수량": float(quantity)
                }])
                df = pd.concat([df, new_row], ignore_index=True)
                
                # 안전 저장 함수 사용
                update_google_sheet(worksheet, df)
                st.rerun()
            else:
                st.error("❌ 검색 결과를 찾을 수 없습니다.")

st.divider()

# ==========================================
# 9. 포트폴리오 수정
# ==========================================
st.subheader("📝 내 포트폴리오 수정 및 삭제")
st.warning("🚨 **중요:** 표의 빈칸을 수정한 뒤에는 반드시 키보드의 **Enter 키를 쳐서 입력을 완료한 상태**에서 저장 버튼을 누르셔야 데이터가 날아가지 않습니다!")

edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)

if st.button("💾 수정한 내용을 구글 시트에 저장하기"):
    update_google_sheet(worksheet, edited_df)
    st.success("✨ 구글 시트에 안전하게 저장되었습니다!")
    st.rerun()

# ==========================================
# 10. 현재 주가 및 환율 계산 로직 (💡 실시간 네이버 금융 반영)
# ==========================================
@st.cache_data(ttl=60)
def get_current_prices_with_currency(tickers, rate):
    prices_krw = []
    prices_usd = []
    is_us_stock = []
    
    for ticker in tickers:
        if not ticker or pd.isna(ticker):
            prices_krw.append(0)
            prices_usd.append(0)
            is_us_stock.append(False)
            continue
            
        ticker_str = str(ticker).upper()
        try:
            # 💡 [한국 주식] 네이버 금융에서 100% 실시간 주가 크롤링
            if ticker_str.endswith('.KS') or ticker_str.endswith('.KQ'):
                # '.KS', '.KQ'를 떼고 6자리 숫자 코드만 추출 (예: 000660.KS -> 000660)
                code = ticker_str.replace('.KS', '').replace('.KQ', '')
                url = f"https://finance.naver.com/item/main.naver?code={code}"
                
                # 네이버 서버가 봇을 차단하지 않도록 User-Agent 추가
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                res = requests.get(url, headers=headers)
                soup = BeautifulSoup(res.text, 'html.parser')
                
                # 네이버 금융 현재가 태그 추출
                today_price_tag = soup.select_one('.no_today .blind')
                if today_price_tag:
                    price = float(today_price_tag.text.replace(',', ''))
                else:
                    # 만약 크롤링에 실패하면 예비용으로 야후 파이낸스 사용
                    stock = yf.Ticker(ticker_str)
                    price = stock.history(period="1d")['Close'].iloc[-1]
                
                prices_krw.append(price)
                prices_usd.append(0)
                is_us_stock.append(False)

            # 💡 [미국 주식] 기존대로 야후 파이낸스 사용
            else:
                stock = yf.Ticker(ticker_str)
                # 장중 실시간 가격을 더 잘 가져오기 위해 info['currentPrice'] 우선 시도
                try:
                    price = stock.info.get('currentPrice', stock.history(period="1d")['Close'].iloc[-1])
                except:
                    price = stock.history(period="1d")['Close'].iloc[-1]
                
                prices_krw.append(price * rate) 
                prices_usd.append(price)        
                is_us_stock.append(True)
                
        except Exception as e:
            print(f"{ticker_str} 주가 불러오기 실패: {e}")
            prices_krw.append(0)
            prices_usd.append(0)
            is_us_stock.append(False)
            
    return prices_krw, prices_usd, is_us_stock

# ==========================================
# 11. 수익률 및 평가금액 계산 & 화면 출력
# ==========================================
if not edited_df.empty:
    st.write("🔄 실시간 주가와 환율을 적용하여 계산하는 중입니다...")
    calc_df = edited_df.copy()
    calc_df['매수단가'] = pd.to_numeric(calc_df['매수단가'], errors='coerce').fillna(0)
    calc_df['보유수량'] = pd.to_numeric(calc_df['보유수량'], errors='coerce').fillna(0)
    
    krw_prices, usd_prices, is_us = get_current_prices_with_currency(calc_df['티커'], exchange_rate)
    calc_df['현재가(KRW)'] = krw_prices
    calc_df['현재가(USD)'] = usd_prices
    calc_df['미국주식'] = is_us
    
    calc_df['평가금액'] = calc_df['현재가(KRW)'] * calc_df['보유수량']
    calc_df['매수금액'] = calc_df.apply(
        lambda x: (x['매수단가'] * x['보유수량'] * exchange_rate) if x['미국주식'] else (x['매수단가'] * x['보유수량']), 
        axis=1
    )
    
    calc_df['수익금'] = calc_df['평가금액'] - calc_df['매수금액']
    calc_df['수익률(%)'] = calc_df.apply(
        lambda x: (x['수익금'] / x['매수금액'] * 100) if x['매수금액'] > 0 else 0, axis=1
    )

    st.subheader("📊 포트폴리오 요약 (원화 기준)")
    total_invest = calc_df['매수금액'].sum()
    total_value = calc_df['평가금액'].sum()
    total_profit = calc_df['수익금'].sum()
    total_return = (total_profit / total_invest * 100) if total_invest > 0 else 0

    col1, col2, col3 = st.columns(3)
    col1.metric("총 매수 금액", f"{total_invest:,.0f} 원")
    col2.metric("총 평가 금액", f"{total_value:,.0f} 원")
    col3.metric("총 수익률", f"{total_return:.2f}%", f"{total_profit:,.0f} 원")

    st.divider()

    st.subheader("📋 실시간 계산 결과")
    
    display_df = calc_df.copy()
    
    def format_current_price(row):
        if row['미국주식']:
            return f"{row['현재가(KRW)']:,.0f}원 (${row['현재가(USD)']:,.2f})"
        else:
            return f"{row['현재가(KRW)']:,.0f}원"
            
    def format_buy_price(row):
        if row['미국주식']:
            return f"${row['매수단가']:,.2f}"
        else:
            return f"{row['매수단가']:,.0f}원"

    display_df['현재가'] = display_df.apply(format_current_price, axis=1)
    display_df['매수단가'] = display_df.apply(format_buy_price, axis=1)
    display_df['수익률(%)'] = display_df['수익률(%)'].round(2).astype(str) + '%'
    display_df['매수금액'] = display_df['매수금액'].apply(lambda x: f"{x:,.0f}원")
    display_df['평가금액'] = display_df['평가금액'].apply(lambda x: f"{x:,.0f}원")
    display_df['수익금'] = display_df['수익금'].apply(lambda x: f"{x:,.0f}원")
    
    final_cols = ['종목명', '티커', '매수단가', '보유수량', '현재가', '매수금액', '평가금액', '수익금', '수익률(%)']
    st.dataframe(display_df[final_cols], use_container_width=True)

    if total_value > 0:
        st.divider()
        st.subheader("🥧 포트폴리오 비중 분석")
        
        chart_col1, chart_col2 = st.columns(2)
        
        with chart_col1:
            st.markdown("##### 📌 종목별 비중")
            fig1 = px.pie(calc_df, values='평가금액', names='종목명', hole=0.4)
            st.plotly_chart(fig1, use_container_width=True)
            
        with chart_col2:
            st.markdown("##### 🌍 국가별 비중 (한국 vs 미국)")
            calc_df['국가'] = calc_df['미국주식'].apply(lambda x: '미국 주식' if x else '한국 주식')
            fig2 = px.pie(
                calc_df, 
                values='평가금액', 
                names='국가', 
                hole=0.4,
                color='국가',
                color_discrete_map={'한국 주식': '#1f77b4', '미국 주식': '#ff7f0e'} 
            )
            st.plotly_chart(fig2, use_container_width=True)
else:
    st.info("위에 있는 검색창을 통해 첫 번째 주식을 추가해 보세요!")
