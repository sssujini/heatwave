import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import requests

# --------------------------------------------------
# 1. 페이지 기본 설정
# --------------------------------------------------
st.set_page_config(
    page_title="전국 시군구별 폭염일수 단계구분도",
    layout="wide"
)

st.title("☀️ 전국 시군구별 폭염일수 현황 지도")
st.caption("시계열 필터와 행정구역 자동 보정 알고리즘을 적용한 대화형 지도입니다.")

# --------------------------------------------------
# 2. 데이터 불러오기 함수
# --------------------------------------------------
GEOJSON_URL = "https://raw.githubusercontent.com/greatsong/modudata/main/data/boundaries/sigungu_kr.geojson"

@st.cache_data
def load_geojson(url):
    """지리 경계 GeoJSON 데이터를 웹에서 가져옵니다."""
    response = requests.get(url)
    return response.json()

@st.cache_data
def load_heatwave_data():
    """폭염일수 CSV 파일을 불러옵니다."""
    try:
        return pd.read_csv("heatwave.csv", encoding="utf-8")
    except UnicodeDecodeError:
        return pd.read_csv("heatwave.csv", encoding="cp949")

try:
    geojson_raw = load_geojson(GEOJSON_URL)
    df_raw = load_heatwave_data()
except Exception as e:
    st.error(f"데이터를 불러오는 중 오류가 발생했습니다: {e}")
    st.stop()

# --------------------------------------------------
# 3. 사용자 설정: CSV 열 이름 지정
# --------------------------------------------------
# [주의] 실제 CSV 파일의 열 이름에 맞게 수정해 주세요.
REGION_COL = "시군구명"   # 지역명/시군구 열
HEATWAVE_COL = "폭염일수" # 폭염일수 수치 열
TIME_COL = "연도"         # 시계열 열 (예: "연도", "월", "일자" 등 / 없으면 None 처리)

# 필수 열 존재 여부 확인
if REGION_COL not in df_raw.columns or HEATWAVE_COL not in df_raw.columns:
    st.error(
        f"CSV 파일에 '{REGION_COL}' 또는 '{HEATWAVE_COL}' 열이 없습니다. "
        f"코드 상단의 변수명을 실제 CSV 헤더에 맞춰주세요."
    )
    st.write("현재 CSV 헤더 목록:", list(df_raw.columns))
    st.stop()

# 데이터 기본 전처리
df_clean = df_raw.copy()
df_clean[HEATWAVE_COL] = pd.to_numeric(df_clean[HEATWAVE_COL], errors='coerce')
df_clean = df_clean.dropna(subset=[REGION_COL, HEATWAVE_COL])

# --------------------------------------------------
# 4. 시계열 슬라이더 필터 UI (사이드바)
# --------------------------------------------------
st.sidebar.header("🔍 데이터 필터")

selected_time_label = "전체 기간"
if TIME_COL and TIME_COL in df_clean.columns:
    # 결측치 제외 후 정렬
    unique_times = sorted(df_clean[TIME_COL].dropna().unique())
    
    if len(unique_times) > 1:
        # 슬라이더 생성 (정수, 문자열 등 다양한 타입 대응을 위해 select_slider 사용)
        selected_time = st.sidebar.select_slider(
            f"📅 {TIME_COL} 선택",
            options=unique_times,
            value=unique_times[-1]  # 기본값: 가장 최근 시점
        )
        selected_time_label = f"{selected_time}년" if "연" in TIME_COL or str(selected_time).isdigit() and len(str(selected_time)) == 4 else str(selected_time)
        
        # 선택한 시점의 데이터만 필터링
        df_filtered = df_clean[df_clean[TIME_COL] == selected_time].copy()
        st.sidebar.info(f"현재 선택된 시점: **{selected_time_label}**")
    else:
        df_filtered = df_clean.copy()
        st.sidebar.text(f"단일 시점 데이터 ({unique_times[0]})")
else:
    df_filtered = df_clean.copy()
    st.sidebar.info("시계열(연도/월) 열이 지정되지 않아 전체 데이터를 사용합니다.")

# --------------------------------------------------
# 5. 시군구 명칭 보정 및 GeoJSON 매핑
# --------------------------------------------------
geojson_sigungu_set = {f['properties']['시군구'] for f in geojson_raw['features']}

# 특수 행정구역 매핑용 사용자 사전 (필요시 추가)
CUSTOM_MAPPING = {
    # "CSV_명칭": "GeoJSON_시군구명"
    # 예: "인천광역시 미추홀구": "남구",
}

def resolve_sigungu_name(raw_name, valid_set):
    if not isinstance(raw_name, str):
        return None
    clean_name = raw_name.strip()
    
    if clean_name in CUSTOM_MAPPING:
        return CUSTOM_MAPPING[clean_name]
    if clean_name in valid_set:
        return clean_name
    
    tokens = clean_name.split()
    if len(tokens) >= 2:
        if tokens[-1] in valid_set:   # 뒷단어 확인 (예: "수원시 팔달구" -> "팔달구")
            return tokens[-1]
        if tokens[0] in valid_set:    # 앞단어 확인 (예: 시 단위)
            return tokens[0]
    return None

df_filtered['매핑_시군구'] = df_filtered[REGION_COL].apply(lambda x: resolve_sigungu_name(x, geojson_sigungu_set))

# 매핑 성공/실패 분리
matched_df = df_filtered.dropna(subset=['매핑_시군구']).copy()
unmatched_df = df_filtered[df_filtered['매핑_시군구'].isna()].copy()

# 시군구 단위로 묶인 경우 평균값 계산
matched_df_grouped = matched_df.groupby('매핑_시군구', as_index=False)[HEATWAVE_COL].mean()

# GeoJSON 데이터 복사본 생성 후 속성 업데이트 (캐시 오염 방지)
import copy
geojson_display = copy.deepcopy(geojson_raw)
heatwave_dict = dict(zip(matched_df_grouped['매핑_시군구'], matched_df_grouped[HEATWAVE_COL]))

for feature in geojson_display['features']:
    sigungu_name = feature['properties'].get('시군구')
    val = heatwave_dict.get(sigungu_name, None)
    if val is not None:
        feature['properties']['폭염일수'] = round(val, 1)
    else:
        feature['properties']['폭염일수'] = "데이터 없음"

# --------------------------------------------------
# 6. 단계구분도(Choropleth) 지도 시각화
# --------------------------------------------------
st.subheader(f"🗺️ {selected_time_label} 전국 폭염일수 단계구분도")

m = folium.Map(location=[36.0, 127.8], zoom_start=7, tiles="CartoDB positron")

if not matched_df_grouped.empty:
    min_val = float(matched_df_grouped[HEATWAVE_COL].min())
    max_val = float(matched_df_grouped[HEATWAVE_COL].max())
    
    # 5단계 구간 계산 (최소-최대값이 동일할 경우 예외 처리)
    if min_val == max_val:
        folium_bins = [min_val - 1.0, min_val, min_val + 1.0]
    else:
        step = (max_val - min_val) / 5.0
        folium_bins = [round(min_val + i * step, 2) for i in range(6)]

    # 단계구분도 레이어 추가
    folium.Choropleth(
        geo_data=geojson_display,
        data=matched_df_grouped,
        columns=['매핑_시군구', HEATWAVE_COL],
        key_on="feature.properties.시군구",
        fill_color="YlOrRd",
        fill_opacity=0.7,
        line_opacity=0.2,
        legend_name=f"폭염일수 (일) - {selected_time_label}",
        bins=folium_bins,
        nan_fill_color="#f2f2f2",
        nan_fill_opacity=0.3
    ).add_to(m)

# 마우스 툴팁 레이어 추가
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

# Streamlit에 지도 렌더링 (슬라이더 조작 시 갱신을 위해 key 지정)
st_folium(m, width="100%", height=580, key=f"map_{selected_time_label}", returned_objects=[])

# --------------------------------------------------
# 7. 상위 / 하위 10곳 순위 표
# --------------------------------------------------
st.divider()
st.subheader(f"📊 {selected_time_label} 폭염일수 순위")

col1, col2 = st.columns(2)

top_10 = df_filtered.sort_values(by=HEATWAVE_COL, ascending=False).head(10)[[REGION_COL, HEATWAVE_COL]].reset_index(drop=True)
top_10.index = top_10.index + 1

bottom_10 = df_filtered.sort_values(by=HEATWAVE_COL, ascending=True).head(10)[[REGION_COL, HEATWAVE_COL]].reset_index(drop=True)
bottom_10.index = bottom_10.index + 1

with col1:
    st.markdown(f"🔥 **가장 더웠던 상위 10곳 ({selected_time_label})**")
    st.dataframe(top_10, use_container_width=True)

with col2:
    st.markdown(f"❄️ **상대적으로 시원했던 하위 10곳 ({selected_time_label})**")
    st.dataframe(bottom_10, use_container_width=True)

# --------------------------------------------------
# 8. 매핑 현황 및 미매칭 지역 안내
# --------------------------------------------------
st.divider()
with st.expander("ℹ️ 행정구역 매핑 상태 확인"):
    total_cnt = len(df_filtered)
    matched_cnt = len(matched_df)
    success_rate = (matched_cnt / total_cnt * 100) if total_cnt > 0 else 0
    
    m_col1, m_col2 = st.columns(2)
    m_col1.metric("선택 시점 데이터 수", f"{total_cnt}건")
    m_col2.metric("지도 매핑 성공률", f"{success_rate:.1f}% ({matched_cnt}/{total_cnt})")
    
    if not unmatched_df.empty:
        st.warning(f"이름 불일치로 지도에 미반영된 지역: {len(unmatched_df)}곳")
        unmatched_items = sorted(unmatched_df[REGION_COL].unique())
        cols = st.columns(4)
        for idx, name in enumerate(unmatched_items):
            cols[idx % 4].write(f"- {name}")
    else:
        st.success("모든 지역이 지도 경계와 정상적으로 연결되었습니다.")
