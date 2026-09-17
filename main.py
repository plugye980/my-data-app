"""
어제의 박스오피스 순위를 보여주는 스트림릿(Streamlit) 앱입니다.

- 코드에 API 키를 직접 적지 않고, 스트림릿의 "비밀 금고(secrets)"에서 불러옵니다.
  (배포 시 Streamlit Cloud 관리 화면의 Secrets에 KOBIS_KEY = "발급받은키" 형태로 넣어주세요.)
- 조회 날짜는 오늘 날짜에서 하루를 뺀 "어제"를 매번 자동으로 계산합니다.
  이때 서버의 시간대가 아니라 반드시 "한국 시간(KST)" 기준으로 계산합니다.
- 초보자도 흐름을 따라올 수 있도록 각 단계마다 한글 주석을 달아두었습니다.
"""

import html
import math
import random
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
# 2. 무늬 만들기 — 같은 간격으로 반복되는 무늬는 아무리 옅게 깔아도 '자로 잰 듯한'
#    느낌이 납니다. 그래서 대리석 결처럼, 굵기·간격·길이가 제각각인 선을 코드로
#    직접 그려서 씁니다. 난수를 쓰지만 씨앗(seed)을 고정했기 때문에 새로고침해도
#    항상 똑같은 모양이 나옵니다.
# ────────────────────────────────────────────────────────────────


def _smooth_path(points: list[tuple[float, float]]) -> str:
    """점들을 부드럽게 이어주는 곡선(SVG path) 문자열로 바꿉니다."""
    path = f"M{points[0][0]:.1f} {points[0][1]:.1f}"
    for i in range(len(points) - 1):
        prev_pt = points[i - 1] if i > 0 else points[0]
        cur_pt, next_pt = points[i], points[i + 1]
        after_pt = points[i + 2] if i + 2 < len(points) else points[-1]
        c1 = (cur_pt[0] + (next_pt[0] - prev_pt[0]) / 6, cur_pt[1] + (next_pt[1] - prev_pt[1]) / 6)
        c2 = (next_pt[0] - (after_pt[0] - cur_pt[0]) / 6, next_pt[1] - (after_pt[1] - cur_pt[1]) / 6)
        path += f"C{c1[0]:.1f} {c1[1]:.1f} {c2[0]:.1f} {c2[1]:.1f} {next_pt[0]:.1f} {next_pt[1]:.1f}"
    return path


def _wander(rng, start, end, segments, amplitude, drift):
    """시작점에서 끝점까지, 옆으로 조금씩 흔들리며 흘러가는 점들을 만듭니다."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    nx, ny = -dy / length, dx / length  # 진행 방향에 수직인 방향
    points, offset = [], 0.0
    for i in range(segments + 1):
        t = i / segments
        taper = (4 * t * (1 - t)) ** 0.6  # 양 끝으로 갈수록 흔들림이 잦아듭니다.
        offset = max(-amplitude, min(amplitude, offset + rng.uniform(-drift, drift)))
        wobble = offset * taper + rng.uniform(-amplitude * 0.12, amplitude * 0.12)
        points.append((start[0] + dx * t + nx * wobble, start[1] + dy * t + ny * wobble))
    return points


def build_vein_svg() -> str:
    """대리석 결 — 길게 흐르는 주 맥 몇 가닥과, 거기에 붙지 않은 짧은 실금들."""
    rng = random.Random(20260917)
    width, height = 600, 380
    parts = []

    # 서로 나란하지 않도록 각도를 크게 다르게 둔 주 맥 세 가닥.
    for start, end, stroke in (
        ((-40, 300), (660, 60), 1.5),
        ((-30, 120), (640, 330), 1.1),
        ((120, -30), (430, 410), 0.9),
    ):
        parts.append((_smooth_path(_wander(rng, start, end, 9, 58, 26)), stroke, 0.14))
        # 주 맥 옆에 잔 맥을 붙이되, 시작·끝을 어긋내어 평행선이 되지 않게 합니다.
        for _ in range(rng.randint(1, 3)):
            head = rng.uniform(0.05, 0.4)
            tail = rng.uniform(0.55, 0.95)
            branch_start = (
                start[0] + (end[0] - start[0]) * head + rng.uniform(-40, 40),
                start[1] + (end[1] - start[1]) * head + rng.uniform(-40, 40),
            )
            branch_end = (
                start[0] + (end[0] - start[0]) * tail + rng.uniform(-70, 70),
                start[1] + (end[1] - start[1]) * tail + rng.uniform(-70, 70),
            )
            parts.append(
                (
                    _smooth_path(_wander(rng, branch_start, branch_end, 7, 34, 18)),
                    rng.uniform(0.4, 0.8),
                    rng.uniform(0.05, 0.1),
                )
            )

    # 아무 데도 닿지 않는 짧은 실금 — 화면이 고르게 덮이지 않도록 한쪽으로 몰아둡니다.
    for _ in range(5):
        head = (rng.uniform(-20, 420), rng.uniform(-20, 400))
        tail = (head[0] + rng.uniform(80, 260), head[1] + rng.uniform(-150, 150))
        parts.append(
            (_smooth_path(_wander(rng, head, tail, 6, 26, 14)), rng.uniform(0.35, 0.6), rng.uniform(0.04, 0.08))
        )

    body = "".join(
        f"<path d='{d}' fill='none' stroke='%234a86a8' stroke-width='{w:.2f}'"
        f" stroke-opacity='{o:.3f}' stroke-linecap='round'/>"
        for d, w, o in parts
    )
    return f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}'>{body}</svg>"


def _css_url(svg: str) -> str:
    """SVG 문자열을 CSS에서 배경 그림으로 쓸 수 있는 형태로 감쌉니다."""
    return f'url("data:image/svg+xml;utf8,{svg}")'


# 만든 결을 CSS 변수로 한 번만 등록해두고, 아래 스타일에서 가져다 씁니다.
st.markdown(
    f"<style>:root{{--vein:{_css_url(build_vein_svg())};}}</style>",
    unsafe_allow_html=True,
)


# ────────────────────────────────────────────────────────────────
# 3. 디자인(CSS) — 흔한 사각형 카드 대신, 모서리가 잘려 있거나
#    가운데에 미세한 균열(선) 효과가 들어간 비대칭 카드를 사용합니다.
#    배경과 카드가 또렷이 분리되지 않도록 어두운 톤 위에 은은한 색으로만 구분합니다.
# ────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
        /* 배경은 순백을 기본으로 하고, 색이 있는 빛 번짐은 별도의 층(::after)에서
           천천히 움직이게 만들어 화면이 완전히 정지해 보이지 않도록 합니다.
           이 빛 번짐이 있어야 위에 얹은 유리판들이 '무언가를 비치게' 됩니다. */
        html, body, [data-testid="stAppViewContainer"] {
            background: #fdfeff;
            color: #20242b;
        }
        [data-testid="stHeader"] { background: transparent; }
        .block-container { padding-top: 2.6rem; padding-bottom: 3rem; max-width: 1180px; }

        /* 크게 번진 색 덩어리들이 천천히 떠다니는 배경 층 — 유리판 뒤에서 흐릿하게
           비쳐 보이는 것이 이 층입니다. */
        [data-testid="stAppViewContainer"]::after {
            content: "";
            position: fixed;
            inset: -18%;
            pointer-events: none;
            z-index: 0;
            filter: blur(22px);
            background:
                radial-gradient(38% 42% at 10% 8%, rgba(125, 197, 232, 0.72) 0%, transparent 70%),
                radial-gradient(30% 34% at 88% 4%, rgba(245, 217, 168, 0.62) 0%, transparent 72%),
                radial-gradient(36% 42% at 74% 40%, rgba(143, 198, 231, 0.5) 0%, transparent 72%),
                radial-gradient(42% 38% at 18% 70%, rgba(170, 209, 235, 0.52) 0%, transparent 70%),
                radial-gradient(34% 30% at 58% 88%, rgba(226, 214, 236, 0.4) 0%, transparent 72%);
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

        /* 구분선은 하늘색 하나만 씁니다. */
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

        .section-label {
            color: #2f7fae;
            font-size: 0.82rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.14em;
            margin-bottom: 0.8rem;
        }

        /* 1위 영화 지표 카드 — 반투명 유리판처럼 보이도록 배경을 살짝만 채우고,
           뒤에 깔린 색을 흐리게 비쳐 보이게(backdrop-filter) 만들었습니다. 위쪽
           모서리의 밝은 선은 유리 단면에 빛이 걸린 느낌을 냅니다.
           대리석 결은 한 장을 카드마다 다른 위치에서 잘라 쓰되, 배율은 비슷하게
           맞춰 카드별로 결의 밀도가 들쭉날쭉하지 않게 했습니다. */
        .kpi-card {
            position: relative;
            padding: 1.3rem 1.3rem 1.1rem 1.3rem;
            background-image: var(--vein), linear-gradient(155deg, rgba(255, 255, 255, 0.62) 0%, rgba(233, 244, 250, 0.42) 100%);
            background-repeat: no-repeat, no-repeat;
            -webkit-backdrop-filter: blur(14px) saturate(125%);
            backdrop-filter: blur(14px) saturate(125%);
            border: 1px solid rgba(255, 255, 255, 0.85);
            box-shadow:
                0 0 0 1px rgba(122, 172, 202, 0.16),
                0 8px 26px rgba(31, 61, 82, 0.09),
                inset 0 1px 0 rgba(255, 255, 255, 0.9);
            overflow: hidden;
            transition: transform 0.25s ease, box-shadow 0.25s ease;
        }
        .kpi-card:hover {
            transform: translateY(-3px);
            box-shadow:
                0 0 0 1px rgba(122, 172, 202, 0.22),
                0 16px 34px rgba(31, 61, 82, 0.13),
                inset 0 1px 0 rgba(255, 255, 255, 0.95);
        }
        .kpi-card.card-hero {
            min-height: 168px;
            padding: 1.7rem 1.5rem 1.4rem 1.5rem;
            clip-path: polygon(0 0, 100% 0, 100% 100%, 6% 100%, 0 90%);
            background-size: 205% 250%, auto;
            background-position: 12% 88%, 0 0;
        }
        .kpi-card.card-2 {
            min-height: 118px;
            clip-path: polygon(0 9%, 90% 0, 100% 0, 100% 100%, 0 100%);
            background-size: 195% 265%, auto;
            background-position: 68% 6%, 0 0;
        }
        .kpi-card.card-3 {
            min-height: 118px;
            clip-path: polygon(0 0, 100% 0, 100% 82%, 90% 100%, 0 100%);
            background-size: 200% 255%, auto;
            background-position: 34% 46%, 0 0;
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
           배경/글자색이 항상 이 화면의 밝은 톤을 그대로 따르도록 했습니다.
           표도 카드와 같은 반투명 유리판 위에 얹습니다. */
        .rank-table-wrap {
            overflow-x: auto;
            padding: 0.3rem 0.4rem;
            background: linear-gradient(160deg, rgba(255, 255, 255, 0.58) 0%, rgba(233, 244, 250, 0.38) 100%);
            -webkit-backdrop-filter: blur(14px) saturate(125%);
            backdrop-filter: blur(14px) saturate(125%);
            border: 1px solid rgba(255, 255, 255, 0.85);
            box-shadow:
                0 0 0 1px rgba(122, 172, 202, 0.14),
                0 8px 26px rgba(31, 61, 82, 0.07),
                inset 0 1px 0 rgba(255, 255, 255, 0.9);
            clip-path: polygon(0 0, 100% 0, 100% 96%, 97% 100%, 0 100%);
        }
        .rank-table { width: 100%; border-collapse: collapse; font-size: 0.92rem; }
        .rank-table thead th {
            text-align: left;
            color: #545b66;
            font-size: 0.74rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-weight: 700;
            padding: 0.6rem 0.9rem;
            border-bottom: 1px solid rgba(79, 163, 207, 0.28);
            /* 표는 숫자를 읽는 곳이라 무늬를 일부러 넣지 않고 비워 둡니다. */
        }
        .rank-table thead th.num { text-align: right; }
        .rank-table tbody td {
            padding: 0.62rem 0.9rem;
            color: #20242b;
            border-bottom: 1px solid rgba(120, 160, 185, 0.14);
        }
        .rank-table tbody td.num { text-align: right; font-variant-numeric: tabular-nums; }
        .rank-table tbody tr {
            transition: background-color 0.2s ease;
        }
        .rank-table tbody tr:hover { background-color: rgba(255, 255, 255, 0.5); }
        .rank-table tbody tr.rank-first td:first-child { border-left: 3px solid #4fa3cf; }
        .rank-table tbody tr.rank-first td { padding-top: 0.72rem; padding-bottom: 0.72rem; }

        /* 안내(가이드) 메시지 상자 — 카드와 같은 유리판이되, 왼쪽에 하늘색 띠를 둘러
           눈에 먼저 들어오게 합니다. 오른쪽 위 모서리는 비스듬히 잘랐습니다. */
        .guide-box {
            position: relative;
            padding: 1.3rem 1.4rem;
            /* 카드와 같은 대리석 결을, 또 다른 위치에서 잘라 깔았습니다. */
            background-image: var(--vein), linear-gradient(160deg, rgba(255, 255, 255, 0.6) 0%, rgba(226, 240, 248, 0.45) 100%);
            background-repeat: no-repeat, no-repeat;
            background-size: 200% 260%, auto;
            background-position: 82% 62%, 0 0;
            -webkit-backdrop-filter: blur(14px) saturate(125%);
            backdrop-filter: blur(14px) saturate(125%);
            border: 1px solid rgba(255, 255, 255, 0.85);
            border-left: 3px solid rgba(79, 163, 207, 0.85);
            box-shadow:
                0 0 0 1px rgba(122, 172, 202, 0.14),
                0 8px 26px rgba(31, 61, 82, 0.08),
                inset 0 1px 0 rgba(255, 255, 255, 0.9);
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
st.markdown('<div class="crack-divider fade-in"></div>', unsafe_allow_html=True)


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
    f'<div class="fade-in">'
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
        # (문자열을 한 줄로 이어 붙여야 합니다 — 빈 줄이 섞이면 스트림릿의 마크다운
        # 파서가 이어지는 내용을 코드 블록으로 오인해 HTML 태그가 그대로 보입니다.)
        st.markdown(
            f'<div class="kpi-card {card_class} scroll-reveal">'
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
