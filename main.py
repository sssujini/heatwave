import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import requests
import io
import copy

# --------------------------------------------------
# 1. 페이지 설정 및 디자인 CSS
# --------------------------------------------------
st.set_page_config(
    page_title="전국 폭염일수 대시보드",
    page_icon="🔥",
    layout="wide"
)

st.markdown("""
<style>
    /* 지도 컨테이너 배경을 화사한 미색/소프트 그레이로 설정 */
    iframe {
        background-color: #f8fafc !important;
        border-radius: 12px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.06);
    }
    .stDataFrame {
        border-radius: 8px;
        overflow: hidden;
    }
</style>
""", unsafe_allow_html=True)

st.title("☀️ 전국 시군구별 폭염일수 대시보드")
st.caption("기상청 종관관측망 데이터를 전국 시군구 지리 경계에 매핑한 대화형 지도입니다.")

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
# 3. 기상청 관측지점 -> 행정구역 매핑
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
# 4. 사이드바 필터 & 연도 선택
# --------------------------------------------------
st.sidebar.markdown("### 🎛️ 필터 설정")

years = sorted(df_raw['년도'].unique())
selected_year = st.sidebar.select_slider(
    "조회 연도 선택",
    options=years,
    value=years[-1]
)

st.sidebar.markdown("---")
st.sidebar.info(
    f"📍 **{selected_year}년 데이터 분석 중**\n\n"
    "기상청 62개 대표 종관관측소 자료를 기반으로 산출되었습니다."
)

# 데이터 집계
df_year = df_raw[df_raw['년도'] == selected_year]
df_counts = df_year.groupby('지점').size().reset_index(name='폭염일수')
df_counts['시군구'] = df_counts['지점'].map(STATION_TO_SIGUNGU)

# --------------------------------------------------
# 5. 핵심 요약 메트릭 카드
# --------------------------------------------------
max_row = df_counts.sort_values(by='폭염일수', ascending=False).iloc[0]
avg_heatwave = df_counts['폭염일수'].mean()

m1, m2, m3 = st.columns(3)
with m1:
    st.metric(label="전국 평균 폭염일수", value=f"{avg_heatwave:.1f}일")
with m2:
    st.metric(label="최다 폭염 관측지", value=f"{max_row['지점']} ({max_row['폭염일수']}일)")
with m3:
    st.metric(label="관측 지점 수", value=f"{len(df_counts)}개 지역")

st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

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
# 7. 워터마크 영구 제거 & 순수 인포그래픽 맵 생성
# --------------------------------------------------
# ★ tiles=None 설정으로 외부 유료 타일서버 워터마크 완전 차단
m = folium.Map(
    location=[35.9, 127.8],
    zoom_start=7,
    tiles=None,
    zoom_control=True
)

# 5단계 색상 구간 계산
min_val = float(df_counts['폭염일수'].min())
max_val = float(df_counts['폭염일수'].max())

if min_val == max_val:
    bins = [min_val - 1.0, min_val, min_val + 1.0]
else:
    step = (max_val - min_val) / 5.0
    bins = [round(min_val + i * step, 1) for i in range(6)]

# 단계구분도 레이어 추가 (선명한 YlOrRd 컬러 팔레트 & 깔끔한 경계선)
folium.Choropleth(
    geo_data=geojson_display,
    data=df_counts,
    columns=['시군구', '폭염일수'],
    key_on="feature.properties.시군구",
    fill_color="YlOrRd",
    fill_opacity=0.88,
    line_color="#cbd5e1",        # 연한 슬레이트 그레이 경계선
    line_weight=0.7,
    line_opacity=1.0,
    legend_name=f"{selected_year}년 시군구 폭염일수 (일)",
    bins=bins,
    nan_fill_color="#e2e8f0",     # 관측소 없는 지역: 세련된 밝은 회색
    nan_fill_opacity=0.7
).add_to(m)

# 마우스오버 툴팁 및 인터랙션 레이어
folium.GeoJson(
    geojson_display,
    style_function=lambda x: {'fillColor': 'transparent', 'color': 'transparent'},
    highlight_function=lambda x: {'weight': 2.5, 'color': '#1e293b', 'fillOpacity': 0.95},
    tooltip=folium.GeoJsonTooltip(
        fields=['시도', '시군구', '폭염일수'],
        aliases=['시·도:', '시·군·구:', '폭염일수:'],
        localize=True,
        sticky=True
    )
).add_to(m)

st_folium(m, width="100%", height=620, key=f"clean_heatwave_map_{selected_year}", returned_objects=[])

# --------------------------------------------------
# 8. 상위 / 하위 순위 표
# --------------------------------------------------
st.divider()

col1, col2 = st.columns(2)

top_10 = df_counts.sort_values(by='폭염일수', ascending=False).head(10)[['지점', '시군구', '폭염일수']].reset_index(drop=True)
top_10.index = top_10.index + 1
top_10.rename(columns={'지점': '관측지점', '폭염일수': '폭염일수 (일)'}, inplace=True)

bottom_10 = df_counts.sort_values(by='폭염일수', ascending=True).head(10)[['지점', '시군구', '폭염일수']].reset_index(drop=True)
bottom_10.index = bottom_10.index + 1
bottom_10.rename(columns={'지점': '관측지점', '폭염일수': '폭염일수 (일)'}, inplace=True)

with col1:
    st.markdown(f"#### 🔥 **폭염이 가장 극심했던 10곳**")
    st.dataframe(
        top_10.style.background_gradient(subset=['폭염일수 (일)'], cmap='YlOrRd'),
        use_container_width=True
    )

with col2:
    st.markdown(f"#### 🧊 **상대적으로 시원했던 10곳**")
    st.dataframe(
        bottom_10.style.background_gradient(subset=['폭염일수 (일)'], cmap='Blues_r'),
        use_container_width=True
    )
