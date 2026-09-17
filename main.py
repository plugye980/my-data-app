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
        /* 배경은 순백을 기본으로 하고, 색이 있는 은은한 빛 번짐은 별도의 층(::after)에서
           천천히 움직이게 만들어 화면이 완전히 정지해 보이지 않도록 합니다. */
        html, body, [data-testid="stAppViewContainer"] {
            background: #ffffff;
            color: #20242b;
        }
        [data-testid="stHeader"] { background: transparent; }
        .block-container { padding-top: 2.6rem; padding-bottom: 3rem; max-width: 1180px; }

        /* 아주 옅은 하늘색 빛 번짐이 천천히 떠다니는 배경 층입니다. */
        [data-testid="stAppViewContainer"]::after {
            content: "";
            position: fixed;
            inset: -12%;
            pointer-events: none;
            z-index: 0;
            background:
                radial-gradient(circle at 14% 8%, #dbf1fb 0%, transparent 40%),
                radial-gradient(circle at 92% 2%, #fbf1de 0%, transparent 26%);
            animation: driftGlow 26s ease-in-out infinite alternate;
        }
        /* 화면 전체에 아주 옅은 종이 질감(노이즈)을 얹어, 색면이 평평해 보이지 않게 합니다. */
        [data-testid="stAppViewContainer"]::before {
            content: "";
            position: fixed;
            inset: 0;
            pointer-events: none;
            z-index: 0;
            opacity: 0.045;
            mix-blend-mode: multiply;
            background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/><feColorMatrix type='saturate' values='0'/></filter><rect width='100%25' height='100%25' filter='url(%23n)'/></svg>");
        }
        [data-testid="stAppViewContainer"] > * { position: relative; z-index: 1; }

        @keyframes driftGlow {
            0%   { transform: translate(0, 0) scale(1); }
            100% { transform: translate(-2.5%, 2%) scale(1.04); }
        }
        @keyframes fadeSlideUp {
            from { opacity: 0; transform: translateY(10px); }
            to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes pulseGlow {
            0%, 100% { box-shadow: 0 0 0 0 rgba(184, 135, 74, 0.45); }
            50%      { box-shadow: 0 0 7px 3px rgba(184, 135, 74, 0.32); }
        }
        .fade-in { animation: fadeSlideUp 0.6s ease both; }

        /* 스크롤에 따른 애니메이션 — 아래로 스크롤해서 요소가 화면에 들어올 때
           서서히 떠오르며 나타납니다. 이 기능(scroll-driven animation)을 지원하지
           않는 브라우저에서는 페이지가 열리자마자 한 번 나타나는 것으로 자연스럽게
           대체됩니다. */
        @keyframes revealUp {
            from { opacity: 0; transform: translateY(26px); }
            to   { opacity: 1; transform: translateY(0); }
        }
        .scroll-reveal {
            opacity: 0;
            transform: translateY(26px);
            animation: revealUp 0.6s ease forwards;
            animation-delay: 0.05s;
        }
        @supports (animation-timeline: view()) {
            .scroll-reveal {
                animation: revealUp linear both;
                animation-timeline: view();
                animation-range: entry 0% cover 40%;
            }
        }

        /* 전체 글꼴에 살짝 자간을 주어 차분하고 모던한 인상을 만듭니다. */
        h1, h2, h3, h4, p, span, div, label { letter-spacing: 0.01em; }

        .app-title {
            font-size: 2.1rem;
            font-weight: 700;
            color: #182330;
            margin-bottom: 0.15rem;
        }
        .app-subtitle {
            color: #545b66;
            font-size: 0.95rem;
            margin-bottom: 1.6rem;
        }

        /* 구분선은 기본적으로 하늘색 하나만 씁니다. 제목 바로 아래의 구분선(.hero)에만
           황동빛 포인트를 아주 살짝 얹어, 화면 전체에서 황동색이 나오는 지점을
           최소한으로 줄였습니다. */
        .crack-divider {
            position: relative;
            height: 1px;
            margin: 1.4rem 0 2.0rem 0;
            background: linear-gradient(90deg, transparent 0%, #4fa3cf70 35%, #4fa3cfb0 50%, #4fa3cf70 65%, transparent 100%);
        }
        .crack-divider::after {
            content: "";
            position: absolute;
            top: -3px;
            left: 50%;
            width: 7px;
            height: 7px;
            background: #ffffff;
            border: 1px solid #4fa3cf;
            transform: translateX(-50%) rotate(45deg);
        }
        .crack-divider.hero {
            background: linear-gradient(90deg, transparent 0%, #4fa3cf70 35%, #b8874ac0 50%, #4fa3cf70 65%, transparent 100%);
        }
        .crack-divider.hero::after {
            border: 1px solid #b8874a;
            animation: pulseGlow 2.6s ease-in-out infinite;
        }
        /* 참고 이미지 속 금색 삼각 처마(페디먼트) 장식을 오마주해, 다이아몬드 아래에
           작은 삼각 표식을 하나 더 두었습니다 — 새 지점이 아니라 기존 황동빛 지점을
           조금 더 구조적으로 표현한 것입니다. */
        .crack-divider.hero::before {
            content: "";
            position: absolute;
            top: 4px;
            left: 50%;
            transform: translateX(-50%);
            width: 0;
            height: 0;
            border-left: 5px solid transparent;
            border-right: 5px solid transparent;
            border-top: 6px solid #b8874a80;
        }

        .section-label {
            color: #2f7fae;
            font-size: 0.82rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.14em;
            margin-bottom: 0.8rem;
        }

        /* 1위 영화 지표 카드 — 세 장의 크기를 일부러 다르게 두어(1:1로 맞춰진 정사각 그리드가
           아니라) 왼쪽 카드가 더 크고 도드라진 '대표 카드'가 되도록 했습니다. 모서리도
           서로 다르게 잘라 비대칭을 만들고, 대각선 균열 하나씩을 겹쳐 질감을 줍니다. */
        .kpi-card {
            position: relative;
            padding: 1.3rem 1.3rem 1.1rem 1.3rem;
            background: linear-gradient(155deg, #ffffff 0%, #eff8fb 100%);
            border: 1px solid #d7e8f0;
            box-shadow: 0 1px 3px rgba(31, 61, 82, 0.06);
            overflow: hidden;
            transition: transform 0.25s ease, box-shadow 0.25s ease;
        }
        .kpi-card:hover {
            transform: translateY(-3px);
            box-shadow: 0 10px 22px rgba(31, 61, 82, 0.12);
        }
        .kpi-card.card-hero {
            min-height: 168px;
            padding: 1.7rem 1.5rem 1.4rem 1.5rem;
            clip-path: polygon(0 0, 100% 0, 100% 100%, 6% 100%, 0 90%);
            box-shadow: 0 6px 18px rgba(79, 163, 207, 0.14);
        }
        /* 참고 이미지 상단의 톱니(사선 삼각) 처마 트림을 오마주한 얇은 띠입니다. */
        .panel-trim {
            position: relative;
            z-index: 1;
            height: 6px;
            margin: -1.7rem -1.5rem 0.85rem -1.5rem;
            background-image:
                linear-gradient(135deg, #4fa3cf 25%, transparent 25.5%),
                linear-gradient(225deg, #4fa3cf 25%, transparent 25.5%);
            background-size: 14px 12px;
            background-position: 0 0, 7px 0;
            opacity: 0.5;
        }
        /* 작은 카드 두 장에는 참고 이미지 속 각진 패널 벽면처럼, 서로 다른 각도로
           교차하는 결을 얹었습니다. 단순히 한 방향으로 반복되는 무늬보다 훨씬
           구조물에 가까운 인상을 줍니다. */
        .kpi-card.card-2, .kpi-card.card-3 {
            min-height: 118px;
            background:
                repeating-linear-gradient(112deg, rgba(79, 163, 207, 0.09) 0px, rgba(79, 163, 207, 0.09) 1px, transparent 1px, transparent 23px),
                repeating-linear-gradient(64deg, rgba(79, 163, 207, 0.06) 0px, rgba(79, 163, 207, 0.06) 1px, transparent 1px, transparent 29px),
                linear-gradient(155deg, #ffffff 0%, #eff8fb 100%);
        }
        .kpi-card.card-2 {
            clip-path: polygon(0 9%, 90% 0, 100% 0, 100% 100%, 0 100%);
        }
        .kpi-card.card-3 {
            clip-path: polygon(0 0, 100% 0, 100% 82%, 90% 100%, 0 100%);
        }

        .kpi-card::before {
            content: "";
            position: absolute;
            z-index: 0;
            width: 160%;
            height: 1px;
            background: linear-gradient(90deg, transparent, #4fa3cf88 45%, #4fa3cf88 55%, transparent);
            top: 55%;
            left: -30%;
            transform: rotate(-9deg);
        }
        /* 대표 카드 모서리에 동심원 메달(포털/홀로그램 명판) 하나를 둡니다. 화면
           전체에 은은히 번지게 했던 이전 방식 대신, 참고 이미지의 '벽에 새겨진
           원형 부조'처럼 테두리가 뚜렷한 작은 명판으로 만들어 더 구조물답게
           보이도록 했습니다. */
        .kpi-card.card-hero::after {
            content: "";
            position: absolute;
            top: 14px;
            right: 14px;
            z-index: 0;
            width: 44px;
            height: 44px;
            border-radius: 50%;
            pointer-events: none;
            border: 1px solid rgba(79, 163, 207, 0.45);
            background-image: repeating-radial-gradient(circle, rgba(79, 163, 207, 0.4) 0px, rgba(79, 163, 207, 0.4) 1px, transparent 1px, transparent 5px);
            box-shadow: inset 0 0 0 4px #eff8fb, inset 0 0 0 5px rgba(79, 163, 207, 0.3);
        }
        .kpi-label, .kpi-value, .kpi-unit {
            position: relative;
            z-index: 1;
        }
        .kpi-label {
            color: #545b66;
            font-size: 0.78rem;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            margin-bottom: 0.55rem;
        }
        .kpi-value {
            color: #182330;
            font-size: 1.9rem;
            font-weight: 700;
        }
        .kpi-card.card-hero .kpi-value { font-size: 2.35rem; }
        .kpi-unit {
            font-size: 0.95rem;
            color: #545b66;
            font-weight: 400;
            margin-left: 0.2rem;
        }

        /* 참고 이미지의 원형 포털/홀로그램 명판을 오마주했습니다. 화면 전체에
           번지는 대신 테두리가 있는 하나의 메달로 뚜렷하게 그려서, 배경 무늬가
           아니라 '걸려 있는 구조물'처럼 보이게 했습니다. 별도의 장식 레이어
           (::before)에만 그려서 실제 글자는 절대 가리지 않습니다. */
        .portal-ring {
            position: relative;
        }
        .portal-ring::before {
            content: "";
            position: absolute;
            z-index: 0;
            top: -18px;
            right: 6px;
            width: 84px;
            height: 84px;
            border-radius: 50%;
            pointer-events: none;
            border: 1px solid rgba(79, 163, 207, 0.35);
            background-image: repeating-radial-gradient(circle, rgba(79, 163, 207, 0.28) 0px, rgba(79, 163, 207, 0.28) 1px, transparent 1px, transparent 6px);
            box-shadow: inset 0 0 0 6px #ffffff, inset 0 0 0 7px rgba(79, 163, 207, 0.22);
        }
        .movie-headline, .rank-badge {
            position: relative;
            z-index: 1;
        }
        .movie-headline {
            display: inline-block;
            color: #182330;
            font-size: 1.35rem;
            font-weight: 700;
            margin-bottom: 0.2rem;
            margin-right: 0.55rem;
        }
        /* 화면에서 황동색이 등장하는 두 지점 중 하나 — 1위 영화 이름 옆의 작은 표식입니다. */
        .rank-badge {
            display: inline-block;
            padding: 0.12rem 0.55rem;
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.06em;
            color: #8a6423;
            background: #fbf0dc;
            border: 1px solid #d9b877;
            border-radius: 999px;
            vertical-align: middle;
        }
        .movie-meta {
            color: #545b66;
            font-size: 0.88rem;
            margin-bottom: 1.1rem;
        }

        /* 전체 순위표 — 캔버스로 그려지는 기본 표 대신 직접 만든 표를 써서,
           배경/글자색이 항상 이 화면의 밝은 톤을 그대로 따르도록 했습니다. */
        .rank-table-wrap { overflow-x: auto; }
        .rank-table { width: 100%; border-collapse: collapse; font-size: 0.92rem; }
        .rank-table thead th {
            text-align: left;
            color: #545b66;
            font-size: 0.74rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-weight: 700;
            padding: 0.6rem 0.9rem;
            border-bottom: 1px solid #bfe0ee;
            /* 표 머리글에도 같은 교차 결을 아주 옅게. */
            background-image:
                repeating-linear-gradient(112deg, rgba(47, 127, 174, 0.06) 0px, rgba(47, 127, 174, 0.06) 1px, transparent 1px, transparent 23px),
                repeating-linear-gradient(64deg, rgba(47, 127, 174, 0.04) 0px, rgba(47, 127, 174, 0.04) 1px, transparent 1px, transparent 29px);
        }
        .rank-table thead th.num { text-align: right; }
        .rank-table tbody td {
            padding: 0.62rem 0.9rem;
            color: #20242b;
            border-bottom: 1px solid #eef3f6;
        }
        .rank-table tbody td.num { text-align: right; font-variant-numeric: tabular-nums; }
        .rank-table tbody tr {
            transition: background-color 0.2s ease;
        }
        .rank-table tbody tr:hover { background-color: #f2f9fc; }
        .rank-table tbody tr.rank-first td:first-child { border-left: 3px solid #4fa3cf; }
        .rank-table tbody tr.rank-first td { padding-top: 0.72rem; padding-bottom: 0.72rem; }

        /* 안내(가이드) 메시지 상자 — 완전한 사각형이 되지 않도록 오른쪽 위 모서리를 비스듬히 잘랐습니다. */
        .guide-box {
            position: relative;
            padding: 1.3rem 1.4rem;
            /* 카드와 같은 교차 결을 얹어 화면 전체의 질감을 통일했습니다. */
            background:
                repeating-linear-gradient(112deg, rgba(79, 163, 207, 0.09) 0px, rgba(79, 163, 207, 0.09) 1px, transparent 1px, transparent 23px),
                repeating-linear-gradient(64deg, rgba(79, 163, 207, 0.06) 0px, rgba(79, 163, 207, 0.06) 1px, transparent 1px, transparent 29px),
                linear-gradient(160deg, #f3f9fc 0%, #e9f3f8 100%);
            border: 1px solid #cfe3ee;
            border-left: 3px solid #4fa3cf;
            clip-path: polygon(0 0, 96% 0, 100% 14%, 100% 100%, 0 100%);
            color: #24303a;
            line-height: 1.65;
        }
        .guide-title {
            color: #2f7fae;
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

st.markdown('<div class="app-title fade-in">어제의 박스오피스</div>', unsafe_allow_html=True)
st.markdown(
    f'<div class="app-subtitle fade-in" style="animation-delay:0.06s">'
    f'기준일 · {format_date_korean(target_dt)} (한국 시간 기준 어제)</div>',
    unsafe_allow_html=True,
)
st.markdown('<div class="crack-divider hero"></div>', unsafe_allow_html=True)


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

st.markdown('<div class="section-label fade-in">오늘의 1위</div>', unsafe_allow_html=True)
st.markdown(
    f'<div class="fade-in portal-ring">'
    f'<span class="movie-headline">{html.escape(top1["영화명"])}</span>'
    f'<span class="rank-badge">1위</span>'
    f"</div>",
    unsafe_allow_html=True,
)
st.markdown(f'<div class="movie-meta fade-in">개봉일 · {html.escape(top1["개봉일"])}</div>', unsafe_allow_html=True)

# 카드 3장의 너비를 일부러 다르게 두어(1.3 : 1 : 1) 똑같은 정사각형이 반복되는
# 느낌을 없애고, 왼쪽 카드가 도드라진 '대표 카드'가 되도록 했습니다.
card_col1, card_col2, card_col3 = st.columns([1.3, 1, 1])
card_specs = [
    (card_col1, "card-hero", "일일 관객수", top1["관객수"], "명"),
    (card_col2, "card-2", "누적 관객수", top1["누적관객"], "명"),
    (card_col3, "card-3", "상영 스크린수", top1["스크린수"], "개"),
]
for col, card_class, label, value, unit in card_specs:
    with col:
        # 대표 카드 위쪽에만 톱니 모양 처마 트림을 하나 얹습니다.
        # (문자열을 한 줄로 이어 붙여야 합니다 — 빈 줄이 섞이면 스트림릿의 마크다운
        # 파서가 이어지는 내용을 코드 블록으로 오인해 HTML 태그가 그대로 보입니다.)
        trim_html = '<div class="panel-trim"></div>' if card_class == "card-hero" else ""
        st.markdown(
            f'<div class="kpi-card {card_class} scroll-reveal">{trim_html}'
            f'<div class="kpi-label">{html.escape(label)}</div>'
            f'<div class="kpi-value">{value:,}<span class="kpi-unit">{html.escape(unit)}</span></div>'
            f"</div>",
            unsafe_allow_html=True,
        )

st.markdown('<div class="crack-divider scroll-reveal"></div>', unsafe_allow_html=True)


# ────────────────────────────────────────────────────────────────
# 10. 관객수 상위 5편 — 막대그래프
#     화려한 배경이나 테두리 없이, 눈금선만으로 값을 읽을 수 있도록 최소한으로 그립니다.
# ────────────────────────────────────────────────────────────────
st.markdown('<div class="section-label scroll-reveal">관객수 상위 5편</div>', unsafe_allow_html=True)

top5 = df.sort_values("관객수", ascending=False).head(5).sort_values("관객수", ascending=True)

fig = go.Figure(
    go.Bar(
        x=top5["관객수"],
        y=top5["영화명"],
        orientation="h",
        marker=dict(color="#4fa3cf", line=dict(width=0)),
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

st.markdown('<div class="crack-divider scroll-reveal"></div>', unsafe_allow_html=True)


# ────────────────────────────────────────────────────────────────
# 11. 전체 순위표
#     st.dataframe은 내부적으로 캔버스에 직접 그려지기 때문에, 브라우저나 OS가
#     어두운 모드를 선호하면 이 화면의 밝은 톤과 상관없이 검게 나올 수 있습니다.
#     그래서 직접 HTML 표를 만들어, 색이 항상 이 페이지 디자인을 따르게 했습니다.
# ────────────────────────────────────────────────────────────────
st.markdown('<div class="section-label scroll-reveal">전체 순위</div>', unsafe_allow_html=True)


def build_rank_table_html(table_df: pd.DataFrame) -> str:
    """순위표 DataFrame을 직접 스타일을 입힌 HTML 표 문자열로 바꿉니다."""
    numeric_columns = {"순위", "관객수", "누적관객", "스크린수"}
    header_cells = "".join(
        f'<th class="{"num" if col in numeric_columns else ""}">{html.escape(col)}</th>'
        for col in table_df.columns
    )

    body_rows = []
    for row in table_df.itertuples(index=False):
        row_class = "rank-first" if row.순위 == 1 else ""
        cells = (
            f'<td class="num">{row.순위}</td>'
            f'<td>{html.escape(row.영화명)}</td>'
            f'<td>{html.escape(row.개봉일)}</td>'
            f'<td class="num">{row.관객수:,}</td>'
            f'<td class="num">{row.누적관객:,}</td>'
            f'<td class="num">{row.스크린수:,}</td>'
        )
        body_rows.append(f'<tr class="{row_class}">{cells}</tr>')

    return (
        '<div class="rank-table-wrap scroll-reveal"><table class="rank-table">'
        f"<thead><tr>{header_cells}</tr></thead>"
        f'<tbody>{"".join(body_rows)}</tbody>'
        "</table></div>"
    )


st.markdown(build_rank_table_html(df), unsafe_allow_html=True)
