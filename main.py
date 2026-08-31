import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import requests
import io
import copy

# --------------------------------------------------
# 1. 페이지 설정 & 맞춤 스타일
# --------------------------------------------------
st.set_page_config(
    page_title="전국 폭염일수 대시보드",
    page_icon="☀️",
    layout="wide"
)

st.title("☀️ 전국 시군구별 폭염일수 대시보드")
st.caption("기상청 종관관측망 데이터를 바탕으로 한 전국 시군구 폭염일수 단계구분도입니다.")

# --------------------------------------------------
# 2. 데이터 로딩 (기상청 복합 CSV 파싱)
# --------------------------------------------------
GEOJSON_URL = "https://raw.githubusercontent.com/greatsong/modudata/main/data/boundaries/sigungu_kr.geojson"

@st.cache_data
def load_geojson(url):
    response = requests.get(url)
    return response.json()

@st.cache_data
def load_heatwave_data():
    try:
        with open("heatwave.csv", "r", encoding="cp949") as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        with open("heatwave.csv", "r", encoding="utf-8") as f:
            lines = f.readlines()

    # '년도,날짜,지점' 실제 데이터 시작 행 탐색
    start_idx = None
    for idx, line in enumerate(lines):
        if "년도" in line and "지점" in line:
            start_idx = idx
            break
            
    if start_idx is None:
        start_idx = 53

    csv_data = "".join(lines[start_idx:])
    df = pd.read_csv(io.StringIO(csv_data))
    
    df.columns = [c.strip() for c in df.columns]
    df = df.dropna(subset=['년도', '지점'])
    df['년도'] = df['년도'].astype(int)
    return df

try:
    geojson_raw = load_geojson(GEOJSON_URL)
    df_raw = load_heatwave_data()
except Exception as e:
    st.error(f"데이터를 불러오는 중 오류가 발생했습니다: {e}")
    st.stop()

# --------------------------------------------------
# 3. 기상청 관측지점 -> 행정구역 매핑 사전
# --------------------------------------------------
STATION_TO_SIGUNGU = {
    '강릉': '강릉시', '강화': '강화군', '거제': '거제시', '거창': '거창군', 
    '고흥': '고흥군', '광주': '광주', '구미': '구미시', '군산': '군산시', 
    '금산': '금산군', '남원': '남원시', '남해': '남해군', '대관령': '평창군', 
    '대구': '대구', '대전': '대전', '목포': '목포시', '문경': '문경시', 
    '밀양': '밀양시', '보령': '보령시', '보은': '보은군', '봉화': '봉화군', 
    '부산': '부산', '부안': '부안군', '부여': '부여군', '산청': '산청군', 
    '서산': '서산시', '서울': '서울', '속초': '속초시', '수원': '수원시', 
    '안동': '안동시', '양평': '양평군', '여수': '여수시', '영덕': '영덕군', 
    '영주': '영주시', '영천': '영천시', '완도': '완도군', '울산': '울산', 
    '울진': '울진군', '원주': '원주시', '의성': '의성군', '이천': '이천시', 
    '인제': '인제군', '인천': '인천', '임실': '임실군', '장수': '장수군', 
    '장흥': '장흥군', '전주': '전주시', '정읍': '정읍시', '제천': '제천시', 
    '진주': '진주시', '창원': '창원시', '천안': '천안시', '철원': '철원군', 
    '청주': '청주시', '추풍령': '영동군', '춘천': '춘천시', '충주': '충주시', 
    '태백': '태백시', '통영': '통영시', '포항': '포항시', '합천': '합천군', 
    '해남': '해남군', '홍천': '홍천군'
}

# --------------------------------------------------
# 4. 사이드바 필터
# --------------------------------------------------
st.sidebar.header("🔍 조회 옵션")

years = sorted(df_raw['년도'].unique())
selected_year = st.sidebar.select_slider(
    "📅 연도 선택",
    options=years,
    value=years[-1]
)

st.sidebar.markdown("---")
st.sidebar.info(
    f"📍 **{selected_year}년 데이터 분석**\n\n"
    "기상청 전국 62개 종관기상관측소 관측 통계를 기반으로 집계되었습니다."
)

# 데이터 집계
df_year = df_raw[df_raw['년도'] == selected_year]
df_counts = df_year.groupby('지점').size().reset_index(name='폭염일수')
df_counts['시군구'] = df_counts['지점'].map(STATION_TO_SIGUNGU)

# --------------------------------------------------
# 5. 핵심 지표 카드
# --------------------------------------------------
if not df_counts.empty:
    max_row = df_counts.sort_values(by='폭염일수', ascending=False).iloc[0]
    avg_val = df_counts['폭염일수'].mean()

    m1, m2, m3 = st.columns(3)
    m1.metric("전국 평균 폭염일수", f"{avg_val:.1f}일")
    m2.metric("최다 폭염 관측지", f"{max_row['지점']} ({max_row['폭염일수']}일)")
    m3.metric("관측 지점 수", f"{len(df_counts)}개 지역")

st.write("")

# --------------------------------------------------
# 6. GeoJSON 데이터 결합
# --------------------------------------------------
geojson_display = copy.deepcopy(geojson_raw)
heatwave_map = dict(zip(df_counts['시군구'], df_counts['폭염일수']))

for feature in geojson_display['features']:
    sido = feature['properties'].get('시도', '')
    sigungu = feature['properties'].get('시군구', '')
    
    val = None
    if sigungu in heatwave_map:
        val = heatwave_map[sigungu]
    elif sido in heatwave_map:
        val = heatwave_map[sido]
        
    feature['properties']['폭염일수'] = f"{val}일" if val is not None else "관측소 없음"

# --------------------------------------------------
# 7. 예쁜 지도 생성 (Esri Light Gray Canvas: 워터마크 없음, 화사한 미색)
# --------------------------------------------------
st.subheader(f"🗺️ {selected_year}년 전국 폭염일수 지도")

# 무료이며 워터마크가 없는 Esri의 깨끗한 캔버스 타일
m = folium.Map(
    location=[36.0, 127.8],
    zoom_start=7,
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
    attr="Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ"
)

# 5단계 구간 계산
min_val = float(df_counts['폭염일수'].min())
max_val = float(df_counts['폭염일수'].max())

if min_val == max_val:
    bins = [min_val - 1.0, min_val, min_val + 1.0]
else:
    step = (max_val - min_val) / 5.0
    bins = [round(min_val + i * step, 1) for i in range(6)]

# 단계구분도 레이어 추가
folium.Choropleth(
    geo_data=geojson_display,
    data=df_counts,
    columns=['시군구', '폭염일수'],
    key_on="feature.properties.시군구",
    fill_color="YlOrRd",
    fill_opacity=0.78,
    line_color="#ffffff",        # 경계를 깔끔한 흰색 라인으로 분할
    line_weight=1.0,
    line_opacity=0.9,
    legend_name=f"{selected_year}년 폭염일수 (일)",
    bins=bins,
    nan_fill_color="#f8fafc",     # 관측소 없는 지역: 맑은 아이보리 화이트
    nan_fill_opacity=0.5
).add_to(m)

# 마우스 툴팁 레이어 추가 (오류를 유발하는 속성 제거 후 안정화)
folium.GeoJson(
    geojson_display,
    style_function=lambda x: {
        'fillColor': '#00000000',
        'color': '#00000000',
        'weight': 0
    },
    tooltip=folium.GeoJsonTooltip(
        fields=['시도', '시군구', '폭염일수'],
        aliases=['시도:', '시군구:', '폭염일수:'],
        localize=True,
        sticky=True
    )
).add_to(m)

# 지도 출력
st_folium(m, width="100%", height=620, key=f"heatwave_map_{selected_year}", returned_objects=[])

# --------------------------------------------------
# 8. 상위 / 하위 순위 표
# --------------------------------------------------
st.divider()
st.subheader(f"📊 {selected_year}년 폭염일수 순위")

col1, col2 = st.columns(2)

top_10 = df_counts.sort_values(by='폭염일수', ascending=False).head(10)[['지점', '시군구', '폭염일수']].reset_index(drop=True)
top_10.index = top_10.index + 1
top_10.rename(columns={'지점': '관측지점', '폭염일수': '폭염일수 (일)'}, inplace=True)

bottom_10 = df_counts.sort_values(by='폭염일수', ascending=True).head(10)[['지점', '시군구', '폭염일수']].reset_index(drop=True)
bottom_10.index = bottom_10.index + 1
bottom_10.rename(columns={'지점': '관측지점', '폭염일수': '폭염일수 (일)'}, inplace=True)

with col1:
    st.markdown("#### 🔥 **폭염 많은 상위 10곳**")
    st.dataframe(
        top_10.style.background_gradient(subset=['폭염일수 (일)'], cmap='YlOrRd'),
        use_container_width=True
    )

with col2:
    st.markdown("#### 🧊 **폭염 적은 하위 10곳**")
    st.dataframe(
        bottom_10.style.background_gradient(subset=['폭염일수 (일)'], cmap='Blues_r'),
        use_container_width=True
    )
