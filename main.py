"""
어제의 박스오피스 순위를 보여주는 스트림릿(Streamlit) 앱입니다.

- 코드에 API 키를 직접 적지 않고, 스트림릿의 "비밀 금고(secrets)"에서 불러옵니다.
  (배포 시 Streamlit Cloud 관리 화면의 Secrets에 KOBIS_KEY = "발급받은키" 형태로 넣어주세요.)
- 조회 날짜는 오늘 날짜에서 하루를 뺀 "어제"를 매번 자동으로 계산합니다.
  이때 서버의 시간대가 아니라 반드시 "한국 시간(KST)" 기준으로 계산합니다.
- 초보자도 흐름을 따라올 수 있도록 각 단계마다 한글 주석을 달아두었습니다.
"""

import html
from datetime import datetime, timedelta, timezone

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

# ────────────────────────────────────────────────────────────────
# 1. 기본 설정값
# ────────────────────────────────────────────────────────────────

# KOBIS(영화진흥위원회) 일별 박스오피스 공식 API 주소입니다.
KOBIS_URL = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"

# 한국 표준시(UTC+9)를 나타내는 시간대 객체입니다.
# Streamlit Cloud 서버는 한국 시간이 아닐 수 있으므로, 항상 이 시간대를 기준으로 계산합니다.
KST = timezone(timedelta(hours=9))

# 브라우저 탭 제목, 레이아웃 등 페이지의 기본 모양을 설정합니다.
st.set_page_config(page_title="어제의 박스오피스", layout="wide")


# ────────────────────────────────────────────────────────────────
# 2. 디자인(CSS) — 흔한 사각형 카드 대신, 모서리가 잘려 있거나
#    가운데에 미세한 균열(선) 효과가 들어간 비대칭 카드를 사용합니다.
#    배경과 카드가 또렷이 분리되지 않도록 어두운 톤 위에 은은한 색으로만 구분합니다.
# ────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
        /* 흰 배경 위에 하늘색과 황동빛을 아주 옅게 흘려 넣어, 밋밋한 흰 여백이 아니라
           은은하게 색이 스며든 배경을 만듭니다. */
        html, body, [data-testid="stAppViewContainer"] {
            background:
                radial-gradient(circle at 10% -8%, #e3f4fb 0%, transparent 42%),
                radial-gradient(circle at 100% 4%, #faf1de 0%, transparent 38%),
                #ffffff;
            color: #262a30;
        }
        [data-testid="stHeader"] { background: transparent; }
        .block-container { padding-top: 2.6rem; padding-bottom: 3rem; max-width: 1180px; }

        /* 화면 전체에 아주 옅은 종이 질감(노이즈)을 얹어, 색면이 평평해 보이지 않게 합니다. */
        [data-testid="stAppViewContainer"]::before {
            content: "";
            position: fixed;
            inset: 0;
            pointer-events: none;
            z-index: 0;
            opacity: 0.05;
            mix-blend-mode: multiply;
            background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/><feColorMatrix type='saturate' values='0'/></filter><rect width='100%25' height='100%25' filter='url(%23n)'/></svg>");
        }
        [data-testid="stAppViewContainer"] > * { position: relative; z-index: 1; }

        /* 전체 글꼴에 살짝 자간을 주어 차분하고 모던한 인상을 만듭니다. */
        h1, h2, h3, h4, p, span, div, label { letter-spacing: 0.01em; }

        .app-title {
            font-size: 2.1rem;
            font-weight: 700;
            color: #1c2733;
            margin-bottom: 0.15rem;
        }
        .app-subtitle {
            color: #6b7280;
            font-size: 0.95rem;
            margin-bottom: 1.6rem;
        }

        /* 제목 아래, 가운데가 살짝 어긋난(비대칭) 균열형 구분선.
           하늘색 선 가운데에 황동빛 포인트를 하나 박아 두 색을 섞습니다. */
        .crack-divider {
            position: relative;
            height: 1px;
            margin: 1.4rem 0 2.0rem 0;
            background: linear-gradient(90deg, transparent 0%, #4fa3cf66 35%, #b8874ad9 50%, #4fa3cf66 65%, transparent 100%);
        }
        .crack-divider::after {
            content: "";
            position: absolute;
            top: -3px;
            left: 50%;
            width: 7px;
            height: 7px;
            background: #ffffff;
            border: 1px solid #b8874a;
            transform: translateX(-50%) rotate(45deg);
        }

        .section-label {
            color: #2f7fae;
            font-size: 0.82rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.14em;
            margin-bottom: 0.8rem;
        }

        /* 1위 영화 지표 카드 3장 — 모서리를 서로 다르게 잘라 비대칭을 만들고,
           대각선 균열 하나씩을 겹쳐 특별한 질감을 줍니다. 가운데 카드만 균열을
           황동빛으로 두어 하늘색 톤 사이에 포인트를 섞었습니다. */
        .kpi-card {
            position: relative;
            padding: 1.4rem 1.3rem 1.2rem 1.3rem;
            background: linear-gradient(155deg, #ffffff 0%, #eff8fb 100%);
            border: 1px solid #d7e8f0;
            box-shadow: 0 1px 3px rgba(31, 61, 82, 0.06);
            min-height: 132px;
            overflow: hidden;
        }
        .kpi-card.card-1 { clip-path: polygon(0 0, 100% 0, 100% 100%, 8% 100%, 0 86%); }
        .kpi-card.card-2 { clip-path: polygon(0 10%, 93% 0, 100% 0, 100% 100%, 0 100%); }
        .kpi-card.card-3 { clip-path: polygon(0 0, 100% 0, 100% 88%, 94% 100%, 0 100%); }

        .kpi-card::before {
            content: "";
            position: absolute;
            width: 160%;
            height: 1px;
            background: linear-gradient(90deg, transparent, #4fa3cf88 45%, #4fa3cf88 55%, transparent);
            top: 55%;
            left: -30%;
            transform: rotate(-9deg);
        }
        .kpi-card.card-2::before {
            background: linear-gradient(90deg, transparent, #b8874a99 45%, #b8874a99 55%, transparent);
        }
        .kpi-label {
            position: relative;
            color: #6b7280;
            font-size: 0.78rem;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            margin-bottom: 0.55rem;
        }
        .kpi-value {
            position: relative;
            color: #1c2733;
            font-size: 1.9rem;
            font-weight: 700;
        }
        .kpi-unit {
            font-size: 0.95rem;
            color: #6b7280;
            font-weight: 400;
            margin-left: 0.2rem;
        }

        .movie-headline {
            color: #1c2733;
            font-size: 1.35rem;
            font-weight: 700;
            margin-bottom: 0.2rem;
        }
        .movie-meta {
            color: #6b7280;
            font-size: 0.88rem;
            margin-bottom: 1.1rem;
        }

        /* 데이터 표가 도드라진 박스로 튀지 않도록, 배경 톤에 스며들게 만듭니다. */
        [data-testid="stDataFrame"] { background: transparent; }

        /* 안내(가이드) 메시지 상자 — 완전한 사각형이 되지 않도록 오른쪽 위 모서리를 비스듬히 잘랐고,
           황동빛 톤으로 다른 섹션과 구분되는 신호를 줍니다. */
        .guide-box {
            position: relative;
            padding: 1.3rem 1.4rem;
            background: linear-gradient(160deg, #fff8ec 0%, #fdf2df 100%);
            border: 1px solid #e7cf9e;
            border-left: 3px solid #b8874a;
            clip-path: polygon(0 0, 96% 0, 100% 14%, 100% 100%, 0 100%);
            color: #4a3c22;
            line-height: 1.65;
        }
        .guide-title {
            color: #8a6423;
            font-weight: 700;
            margin-bottom: 0.5rem;
            font-size: 1.0rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# ────────────────────────────────────────────────────────────────
# 3. 날짜 계산 — 항상 "한국 시간 기준 어제"를 자동으로 구합니다.
# ────────────────────────────────────────────────────────────────
def get_yesterday_kst() -> str:
    """지금 이 순간의 한국 시간을 구한 뒤, 하루 전 날짜를 'yyyymmdd' 형식 문자열로 반환합니다."""
    now_kst = datetime.now(KST)
    yesterday_kst = now_kst - timedelta(days=1)
    return yesterday_kst.strftime("%Y%m%d")


def format_date_korean(yyyymmdd: str) -> str:
    """'20260916' 같은 문자열을 '2026년 09월 16일'처럼 사람이 읽기 좋은 한국어 형식으로 바꿉니다."""
    dt = datetime.strptime(yyyymmdd, "%Y%m%d")
    return dt.strftime("%Y년 %m월 %d일")


# ────────────────────────────────────────────────────────────────
# 4. API 호출 — 같은 날짜로 다시 조회하면 1시간 동안은 실제 요청을 보내지 않고
#    직전에 받아둔 결과를 그대로 재사용합니다. (st.cache_data의 ttl=3600)
# ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_box_office(target_dt: str, api_key: str) -> dict:
    """KOBIS 일별 박스오피스 API를 호출하고, 응답을 딕셔너리(JSON)로 반환합니다."""
    params = {"key": api_key, "targetDt": target_dt}
    response = requests.get(KOBIS_URL, params=params, timeout=10)
    response.raise_for_status()
    return response.json()


def render_guide(title: str, lines: list[str]) -> None:
    """API 호출이 실패했거나 데이터가 비어 있을 때, 화면을 비워두는 대신
    무엇을 확인해야 하는지 안내하는 상자를 보여줍니다."""
    items_html = "".join(f"<li>{html.escape(line)}</li>" for line in lines)
    st.markdown(
        f"""
        <div class="guide-box">
            <div class="guide-title">{html.escape(title)}</div>
            <ul style="margin:0; padding-left:1.2rem;">{items_html}</ul>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ────────────────────────────────────────────────────────────────
# 5. 화면 상단 — 제목과 날짜
# ────────────────────────────────────────────────────────────────
target_dt = get_yesterday_kst()

st.markdown('<div class="app-title">어제의 박스오피스</div>', unsafe_allow_html=True)
st.markdown(
    f'<div class="app-subtitle">기준일 · {format_date_korean(target_dt)} (한국 시간 기준 어제)</div>',
    unsafe_allow_html=True,
)
st.markdown('<div class="crack-divider"></div>', unsafe_allow_html=True)


# ────────────────────────────────────────────────────────────────
# 6. secrets에서 API 키 읽기
# ────────────────────────────────────────────────────────────────
api_key = st.secrets.get("KOBIS_KEY")

if not api_key:
    render_guide(
        "API 키를 찾을 수 없습니다",
        [
            "Streamlit Cloud의 앱 설정 → Secrets 화면에 KOBIS_KEY 값이 등록되어 있는지 확인해주세요.",
            '예시 형식: KOBIS_KEY = "발급받은 인증키"',
            "키를 새로 등록했다면 앱을 다시 시작(Reboot)해야 반영됩니다.",
        ],
    )
    st.stop()


# ────────────────────────────────────────────────────────────────
# 7. API 호출 및 오류 처리
#    - 네트워크 자체가 실패한 경우
#    - 응답은 왔지만 오류 상자(faultInfo)가 담겨 온 경우
#    - 정상 응답이지만 영화 목록이 비어 있는 경우
#    세 가지 상황을 모두 구분해서, 사용자가 무엇을 확인해야 하는지 안내합니다.
# ────────────────────────────────────────────────────────────────
try:
    with st.spinner("박스오피스 정보를 불러오는 중입니다..."):
        raw_data = fetch_box_office(target_dt, api_key)
except requests.exceptions.RequestException:
    render_guide(
        "박스오피스 정보를 불러오지 못했습니다",
        [
            "인터넷 연결 상태를 확인해주세요.",
            "KOBIS 오픈API 서버가 일시적으로 응답하지 않을 수 있으니, 잠시 후 다시 시도해주세요.",
            "문제가 계속되면 새로고침으로 다시 요청해보세요.",
        ],
    )
    st.stop()

# KOBIS API는 키가 틀려도 HTTP 상태코드는 200(정상)으로 오고,
# 대신 boxOfficeResult 자리에 faultInfo(오류 정보) 상자가 담겨서 옵니다.
fault_info = raw_data.get("faultInfo")
if fault_info:
    fault_message = fault_info.get("message", "알 수 없는 오류")
    render_guide(
        "KOBIS API가 오류를 반환했습니다",
        [
            f"API 응답 메시지: {fault_message}",
            "Secrets에 등록한 KOBIS_KEY 값이 정확한지 다시 확인해주세요.",
            "조회 날짜(targetDt) 형식이 8자리 숫자(yyyymmdd)인지 확인해주세요.",
        ],
    )
    st.stop()

daily_list = raw_data.get("boxOfficeResult", {}).get("dailyBoxOfficeList", [])
if not daily_list:
    render_guide(
        "표시할 박스오피스 데이터가 없습니다",
        [
            "해당 날짜의 박스오피스 집계가 아직 발표되지 않았을 수 있습니다. 잠시 후 다시 시도해주세요.",
            "KOBIS 서버 점검 등으로 데이터 제공이 일시 중단되었을 수 있습니다.",
        ],
    )
    st.stop()


# ────────────────────────────────────────────────────────────────
# 8. 데이터 가공 — API가 모든 숫자를 문자("15","1234") 형태로 주기 때문에,
#    정렬과 그래프에 쓸 수 있도록 정수(int)로 바꿔줍니다.
# ────────────────────────────────────────────────────────────────
rows = []
for item in daily_list:
    rows.append(
        {
            "순위": int(item["rank"]),
            "영화명": item["movieNm"],
            "개봉일": item["openDt"],
            "관객수": int(item["audiCnt"]),
            "누적관객": int(item["audiAcc"]),
            "스크린수": int(item["scrnCnt"]),
        }
    )

df = pd.DataFrame(rows).sort_values("순위").reset_index(drop=True)


# ────────────────────────────────────────────────────────────────
# 9. 1위 영화 — 지표 카드 3장으로 크게 보여줍니다.
# ────────────────────────────────────────────────────────────────
top1 = df.iloc[0]

st.markdown('<div class="section-label">오늘의 1위</div>', unsafe_allow_html=True)
st.markdown(f'<div class="movie-headline">{html.escape(top1["영화명"])}</div>', unsafe_allow_html=True)
st.markdown(f'<div class="movie-meta">개봉일 · {html.escape(top1["개봉일"])}</div>', unsafe_allow_html=True)

card_col1, card_col2, card_col3 = st.columns(3)
card_specs = [
    (card_col1, "card-1", "일일 관객수", top1["관객수"], "명"),
    (card_col2, "card-2", "누적 관객수", top1["누적관객"], "명"),
    (card_col3, "card-3", "상영 스크린수", top1["스크린수"], "개"),
]
for col, card_class, label, value, unit in card_specs:
    with col:
        st.markdown(
            f"""
            <div class="kpi-card {card_class}">
                <div class="kpi-label">{html.escape(label)}</div>
                <div class="kpi-value">{value:,}<span class="kpi-unit">{html.escape(unit)}</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

st.markdown('<div class="crack-divider"></div>', unsafe_allow_html=True)


# ────────────────────────────────────────────────────────────────
# 10. 관객수 상위 5편 — 막대그래프
#     화려한 배경이나 테두리 없이, 눈금선만으로 값을 읽을 수 있도록 최소한으로 그립니다.
# ────────────────────────────────────────────────────────────────
st.markdown('<div class="section-label">관객수 상위 5편</div>', unsafe_allow_html=True)

top5 = df.sort_values("관객수", ascending=False).head(5).sort_values("관객수", ascending=True)

# 막대는 대부분 하늘색으로 통일하되, 관객수 1위 막대 하나만 황동빛으로 두어
# 색을 섞은 포인트를 줍니다.
bar_colors = ["#4fa3cf"] * (len(top5) - 1) + ["#b8874a"]

fig = go.Figure(
    go.Bar(
        x=top5["관객수"],
        y=top5["영화명"],
        orientation="h",
        marker=dict(color=bar_colors, line=dict(width=0)),
        width=0.45,
        hovertemplate="%{y}<br>관객수 %{x:,}명<extra></extra>",
    )
)
fig.update_layout(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#262a30", size=13),
    margin=dict(l=0, r=20, t=10, b=10),
    height=280,
    xaxis=dict(
        showgrid=True,
        gridcolor="rgba(38,42,48,0.12)",
        gridwidth=1,
        zeroline=False,
        showline=False,
        tickformat=",",
    ),
    yaxis=dict(showgrid=False, showline=False, zeroline=False),
    showlegend=False,
)
st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

st.markdown('<div class="crack-divider"></div>', unsafe_allow_html=True)


# ────────────────────────────────────────────────────────────────
# 11. 전체 순위표
# ────────────────────────────────────────────────────────────────
st.markdown('<div class="section-label">전체 순위</div>', unsafe_allow_html=True)

st.dataframe(
    df,
    hide_index=True,
    use_container_width=True,
    column_config={
        "순위": st.column_config.NumberColumn("순위"),
        "영화명": st.column_config.TextColumn("영화명"),
        "개봉일": st.column_config.TextColumn("개봉일"),
        "관객수": st.column_config.NumberColumn("관객수", format="%,d"),
        "누적관객": st.column_config.NumberColumn("누적관객", format="%,d"),
        "스크린수": st.column_config.NumberColumn("스크린수", format="%,d"),
    },
)
