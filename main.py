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
    page_icon="☀️",
    layout="wide"
)

# 첨부 이미지와 유사한 깔끔하고 모던한 표 및 제목 스타일
st.markdown("""
<style>
    .section-title {
        font-size: 1.35rem;
        font-weight: 700;
        color: #1e293b;
        margin-top: 30px;
        margin-bottom: 12px;
        display: flex;
        align-items: center;
    }
    .section-title::before {
        content: "■";
        color: #0f172a;
        font-size: 0.95rem;
        margin-right: 8px;
    }
    .stDataFrame {
        border-radius: 8px;
        overflow: hidden;
    }
</style>
""", unsafe_allow_html=True)

st.title("☀️ 대한민국 폭염 종합 분석 대시보드")
st.caption("기상청 관측망 데이터를 바탕으로 한 전국 폭염일수 지도 및 연도별 주요 폭염 기록 통계입니다.")

# --------------------------------------------------
# 2. 데이터 로딩 (CSV 내 3개 테이블 분리 파싱)
# --------------------------------------------------
GEOJSON_URL = "https://raw.githubusercontent.com/greatsong/modudata/main/data/boundaries/sigungu_kr.geojson"

@st.cache_data
def load_geojson(url):
    response = requests.get(url)
    return response.json()

@st.cache_data
def load_all_heatwave_data():
    """하나의 heatwave.csv에서 3개 섹션의 데이터를 각각 읽어옵니다."""
    try:
        with open("heatwave.csv", "r", encoding="cp949") as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        with open("heatwave.csv", "r", encoding="utf-8") as f:
            lines = f.readlines()

    # 각 섹션의 시작 위치 파악
    longest_idx = None
    extreme_idx = None
    points_idx = None

    for idx, line in enumerate(lines):
        clean_l = line.strip()
        if clean_l == "가장 긴 폭염":
            longest_idx = idx + 1
        elif clean_l == "가장 빠른/가장 늦은 폭염":
            extreme_idx = idx + 1
        elif clean_l == "전국 폭염일수":
            points_idx = idx + 2  # '년도,날짜,지점' 헤더 위치

    # 1. 가장 긴 폭염 파싱
    longest_lines = []
    for l in lines[longest_idx:]:
        if not l.strip() or "가장 빠른" in l:
            break
        longest_lines.append(l)
    df_longest = pd.read_csv(io.StringIO("".join(longest_lines)))
    df_longest.columns = [c.strip() for c in df_longest.columns]

    # 2. 가장 빠른/늦은 폭염 파싱
    extreme_lines = []
    for l in lines[extreme_idx:]:
        if not l.strip() or "전국 폭염일수" in l:
            break
        extreme_lines.append(l)
    df_extreme = pd.read_csv(io.StringIO("".join(extreme_lines)))
    df_extreme.columns = [c.strip() for c in df_extreme.columns]

    # 3. 지도용 지점별 폭염일자 데이터 파싱
    df_points = pd.read_csv(io.StringIO("".join(lines[points_idx:])))
    df_points.columns = [c.strip() for c in df_points.columns]
    df_points = df_points.dropna(subset=['년도', '지점'])
    df_points['년도'] = df_points['년도'].astype(int)

    return df_longest, df_extreme, df_points

try:
    geojson_raw = load_geojson(GEOJSON_URL)
    df_longest, df_extreme, df_raw = load_all_heatwave_data()
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
    "📅 지도 조회 연도 선택",
    options=years,
    value=years[-1]
)

st.sidebar.markdown("---")
st.sidebar.info(
    f"📍 **{selected_year}년 폭염 관측 데이터**\n\n"
    "기상청 전국 62개 종관기상관측소 관측 통계를 기반으로 단계구분도를 표시합니다."
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
# 7. 단계구분도 지도 생성 (Esri 캔버스 베이스)
# --------------------------------------------------
st.subheader(f"🗺️ {selected_year}년 전국 폭염일수 지도")

m = folium.Map(
    location=[36.0, 127.8],
    zoom_start=7,
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
    attr="Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ"
)

min_val = float(df_counts['폭염일수'].min())
max_val = float(df_counts['폭염일수'].max())

if min_val == max_val:
    bins = [min_val - 1.0, min_val, min_val + 1.0]
else:
    step = (max_val - min_val) / 5.0
    bins = [round(min_val + i * step, 1) for i in range(6)]

folium.Choropleth(
    geo_data=geojson_display,
    data=df_counts,
    columns=['시군구', '폭염일수'],
    key_on="feature.properties.시군구",
    fill_color="YlOrRd",
    fill_opacity=0.78,
    line_color="#ffffff",
    line_weight=1.0,
    line_opacity=0.9,
    legend_name=f"{selected_year}년 폭염일수 (일)",
    bins=bins,
    nan_fill_color="#f8fafc",
    nan_fill_opacity=0.5
).add_to(m)

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

st_folium(m, width="100%", height=600, key=f"heatwave_map_{selected_year}", returned_objects=[])

# --------------------------------------------------
# 8. 상위 / 하위 순위 표
# --------------------------------------------------
st.divider()
st.subheader(f"📊 {selected_year}년 폭염일수 순위")

col1, col2 = st.columns(2)

top_10 = df_counts.sort_values(by='폭염일수', ascending=False).head(10)[['지점', '시군구', '폭염일수']].reset_index(drop=True)
top_10.index = top_10.index + 1
top_10.rename(columns={'지점': '관측지점'}, inplace=True)

bottom_10 = df_counts.sort_values(by='폭염일수', ascending=True).head(10)[['지점', '시군구', '폭염일수']].reset_index(drop=True)
bottom_10.index = bottom_10.index + 1
bottom_10.rename(columns={'지점': '관측지점'}, inplace=True)

column_config = {
    "폭염일수": st.column_config.ProgressColumn(
        "폭염일수 (일)",
        format="%d일",
        min_value=0,
        max_value=int(df_counts['폭염일수'].max()),
    )
}

with col1:
    st.markdown("#### 🔥 **폭염 많은 상위 10곳**")
    st.dataframe(top_10, column_config=column_config, use_container_width=True)

with col2:
    st.markdown("#### 🧊 **폭염 적은 하위 10곳**")
    st.dataframe(bottom_10, column_config=column_config, use_container_width=True)

# --------------------------------------------------
# 9. 요청하신 테이블: 가장 긴 폭염 & 가장 빠른/늦은 폭염
# --------------------------------------------------
st.divider()

# 9-1. 가장 긴 폭염
st.markdown('<div class="section-title">가장 긴 폭염</div>', unsafe_allow_html=True)

# 이미지처럼 컬럼명 변경 (지속일수 -> 최장 지속일수)
df_longest_display = df_longest.copy()
if "지속일수" in df_longest_display.columns:
    df_longest_display.rename(columns={"지속일수": "최장 지속일수"}, inplace=True)

st.dataframe(
    df_longest_display,
    use_container_width=True,
    hide_index=True,
    column_config={
        "연도": st.column_config.TextColumn("연도"),
        "지점": st.column_config.TextColumn("지점"),
        "시작일": st.column_config.TextColumn("시작일"),
        "종료일": st.column_config.TextColumn("종료일"),
        "최장 지속일수": st.column_config.NumberColumn("최장 지속일수", format="%d"),
    }
)

# 9-2. 가장 빠른 / 가장 늦은 폭염 (사진처럼 2단 헤더 구조 재현)
st.markdown('<div class="section-title">가장 빠른/늦은 폭염</div>', unsafe_allow_html=True)

df_extreme_display = df_extreme.copy()
# 다중 컬럼(MultiIndex)으로 변환하여 사진처럼 상단에 '가장 빠른', '가장 늦은' 그룹 헤더 생성
multi_cols = pd.MultiIndex.from_tuples([
    ("연도", ""),
    ("가장 빠른", "지점"),
    ("가장 빠른", "날짜"),
    ("가장 늦은", "지점"),
    ("가장 늦은", "날짜")
])
df_extreme_display.columns = multi_cols

st.dataframe(
    df_extreme_display,
    use_container_width=True,
    hide_index=True
)
