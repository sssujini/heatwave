import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import requests
import io
import copy

# --------------------------------------------------
# 1. 페이지 설정
# --------------------------------------------------
st.set_page_config(
    page_title="전국 시군구별 폭염일수 지도",
    layout="wide"
)

st.title("☀️ 전국 시군구별 폭염일수 현황 지도")
st.caption("기상청 폭염일수 관측 데이터를 전국 시군구 지리 경계(GeoJSON)에 매핑한 대화형 지도입니다.")

# --------------------------------------------------
# 2. 데이터 로딩 (기상청 복합 CSV 구조 파싱)
# --------------------------------------------------
GEOJSON_URL = "https://raw.githubusercontent.com/greatsong/modudata/main/data/boundaries/sigungu_kr.geojson"

@st.cache_data
def load_geojson(url):
    response = requests.get(url)
    return response.json()

@st.cache_data
def load_heatwave_data():
    """복합 CSV에서 '년도,날짜,지점'이 시작되는 행 이후 데이터를 파싱합니다."""
    # CP949 인코딩 우선 적용 (기상청 기본 인코딩)
    try:
        with open("heatwave.csv", "r", encoding="cp949") as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        with open("heatwave.csv", "r", encoding="utf-8") as f:
            lines = f.readlines()

    # '년도,날짜,지점' 헤더가 위치한 행 찾기
    start_idx = None
    for idx, line in enumerate(lines):
        if "년도" in line and "지점" in line:
            start_idx = idx
            break
            
    if start_idx is None:
        start_idx = 53

    csv_data = "".join(lines[start_idx:])
    df = pd.read_csv(io.StringIO(csv_data))
    
    # 열 이름 공백 제거 및 결측치 정제
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
# 3. 기상청 관측지점 -> 행정구역(시군구) 매핑 사전
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
# 4. 사이드바: 연도 선택 슬라이더
# --------------------------------------------------
st.sidebar.header("🔍 조회 옵션")

years = sorted(df_raw['년도'].unique())
selected_year = st.sidebar.select_slider(
    "📅 연도 선택",
    options=years,
    value=years[-1]  # 기본값: 가장 최근 연도
)

# 선택 연도의 데이터 필터링
df_year = df_raw[df_raw['년도'] == selected_year]

# 지점별 폭염 발생 일수 집계 (Count)
df_counts = df_year.groupby('지점').size().reset_index(name='폭염일수')

# 지점명을 시군구 이름으로 변환
df_counts['시군구'] = df_counts['지점'].map(STATION_TO_SIGUNGU)

# --------------------------------------------------
# 5. GeoJSON 경계 데이터와 결합
# --------------------------------------------------
geojson_display = copy.deepcopy(geojson_raw)

heatwave_map = dict(zip(df_counts['시군구'], df_counts['폭염일수']))

# GeoJSON 피처 속성에 폭염일수 주입
for feature in geojson_display['features']:
    sido = feature['properties'].get('시도', '')
    sigungu = feature['properties'].get('시군구', '')
    
    val = None
    if sigungu in heatwave_map:
        val = heatwave_map[sigungu]
    elif sido in heatwave_map:
        val = heatwave_map[sido]
        
    feature['properties']['폭염일수'] = val if val is not None else "관측소 없음"

# --------------------------------------------------
# 6. 단계구분도 (Folium Choropleth) 지도 생성
# --------------------------------------------------
st.subheader(f"🗺️ {selected_year}년 전국 시군구별 폭염일수 단계구분도")

# ★ 워터마크(API KEY REQUIRED)가 없는 오픈소스 기본 지도(OpenStreetMap) 사용
m = folium.Map(
    location=[36.0, 127.8], 
    zoom_start=7, 
    tiles="OpenStreetMap"
)

# 구간 설정 (최소값 ~ 최대값 균등 5분할)
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
    fill_opacity=0.7,
    line_opacity=0.3,
    legend_name=f"{selected_year}년 폭염일수 (일)",
    bins=bins,
    nan_fill_color="#e0e0e0",
    nan_fill_opacity=0.4
).add_to(m)

# 툴팁 레이어 추가
folium.GeoJson(
    geojson_display,
    style_function=lambda x: {'fillColor': '#00000000', 'color': '#00000000'},
    tooltip=folium.GeoJsonTooltip(
        fields=['시도', '시군구', '폭염일수'],
        aliases=['시도:', '시군구:', '폭염일수(일):'],
        localize=True,
        sticky=True
    )
).add_to(m)

# Streamlit에 지도 렌더링
st_folium(m, width="100%", height=600, key=f"heatwave_map_{selected_year}", returned_objects=[])

# --------------------------------------------------
# 7. 폭염일수 많은 곳 / 적은 곳 10곳 표 출력
# --------------------------------------------------
st.divider()
st.subheader(f"📊 {selected_year}년 폭염일수 순위")

col1, col2 = st.columns(2)

# 상위 10곳
top_10 = df_counts.sort_values(by='폭염일수', ascending=False).head(10)[['지점', '시군구', '폭염일수']].reset_index(drop=True)
top_10.index = top_10.index + 1

# 하위 10곳
bottom_10 = df_counts.sort_values(by='폭염일수', ascending=True).head(10)[['지점', '시군구', '폭염일수']].reset_index(drop=True)
bottom_10.index = bottom_10.index + 1

with col1:
    st.markdown(f"🔥 **폭염일수 많은 상위 10곳 ({selected_year}년)**")
    st.dataframe(top_10, use_container_width=True)

with col2:
    st.markdown(f"❄️ **폭염일수 적은 하위 10곳 ({selected_year}년)**")
    st.dataframe(bottom_10, use_container_width=True)

# --------------------------------------------------
# 8. 데이터 정보 안내
# --------------------------------------------------
with st.expander("ℹ️ 관측소 및 지도 데이터 매핑 안내"):
    st.markdown("""
    - **데이터 출처**: 기상청 종관기상관측(ASOS) 폭염일수 데이터 (총 62개 주요 관측지점)
    - **관측소 없는 지역**: 회색으로 표시되며 마우스 오버 시 `관측소 없음`으로 나타납니다.
    - **광역시·특별시**: 기상청 대표 지점(예: 서울, 대구 등)의 관측값을 관내 자치구에 공통 반영했습니다.
    """)
