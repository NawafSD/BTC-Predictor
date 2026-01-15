#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st

from main import (
    RSS_SOURCES,
    YAHOO_SYMBOL,
    combine_signal,
    expected_move_pct,
    fetch_news,
    fetch_price_snapshot,
    filter_recent,
)


def classify_signal(score: float) -> tuple[str, str]:
    if score >= 0.15:
        return "Bullish", "increase"
    if score <= -0.15:
        return "Bearish", "decrease"
    return "Neutral", "move sideways"


def load_data() -> tuple:
    now = datetime.now(timezone.utc)
    news = fetch_news(RSS_SOURCES)
    filtered, window_label = filter_recent(news, now, today_only=True)
    futures = fetch_price_snapshot(YAHOO_SYMBOL, timeout=25, retries=3)
    combined_score = combine_signal(filtered, futures)
    move_pct = expected_move_pct(combined_score, futures)
    expected_price = futures.yesterday_close * (1 + move_pct / 100.0)
    return now, filtered, window_label, futures, combined_score, move_pct, expected_price


def main() -> None:
    st.set_page_config(
        page_title="Quant Hunder's BTC Quantitative Predictor",
        page_icon="📈",
        layout="wide",
    )
    riyadh_tz = ZoneInfo("Asia/Riyadh")

    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700&family=DM+Mono:wght@400;500&display=swap');
        :root {
            --bg: #0b0f12;
            --panel: #121820;
            --panel-2: #161e28;
            --text: #e9eef4;
            --muted: #9aa7b5;
            --accent: #f6c453;
            --accent-2: #65d6a9;
            --danger: #f26b6b;
        }
        html, body, [class*="css"]  {
            font-family: 'Space Grotesk', sans-serif;
            color: var(--text);
        }
        .stApp {
            background: radial-gradient(1200px 800px at 15% 0%, #16202b 0%, var(--bg) 55%);
        }
        .title {
            font-size: 2.2rem;
            font-weight: 700;
            letter-spacing: -0.02em;
            margin-bottom: 0.2rem;
        }
        .subtitle {
            color: var(--muted);
            margin-bottom: 1.2rem;
        }
        .card {
            background: linear-gradient(135deg, var(--panel) 0%, var(--panel-2) 100%);
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 16px;
            padding: 18px;
            box-shadow: 0 12px 30px rgba(0,0,0,0.35);
        }
        .badge {
            display: inline-block;
            padding: 6px 12px;
            border-radius: 999px;
            font-weight: 600;
            font-size: 0.9rem;
            background: rgba(246,196,83,0.18);
            color: var(--accent);
        }
        .metric-label {
            color: var(--muted);
            font-size: 0.85rem;
        }
        .metric-value {
            font-size: 1.35rem;
            font-weight: 600;
        }
        .headline {
            padding: 12px 0 4px 0;
        }
        .metric-block {
            margin-bottom: 14px;
        }
        .headline time {
            font-family: 'DM Mono', monospace;
            color: var(--muted);
            margin-right: 8px;
        }
        .score {
            font-family: 'DM Mono', monospace;
            color: var(--accent-2);
            margin-left: 6px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    header = st.container()
    with header:
        left, center, right = st.columns([1, 2, 1])
        with center:
            st.markdown(
                "<div class='title' style='text-align:center;'>"
                "Quant Hunder's BTC Quantitative Predictor"
                "</div>",
                unsafe_allow_html=True,
            )
        with right:
            image_path = Path("hunder.png")
            if not image_path.exists():
                image_path = Path("hunder.PNG")
            if image_path.exists():
                st.image(str(image_path), width=160)
            st.markdown(
                "<div class='subtitle' style='text-align:right; color:#f26b6b; font-weight:700;'>"
                "Credits: Quant Hunder"
                "</div>",
                unsafe_allow_html=True,
            )

    try:
        now, filtered, window_label, futures, combined_score, move_pct, expected_price = (
            load_data()
        )
    except Exception as exc:
        st.error(f"Failed to load data: {exc}")
        return

    sentiment, direction = classify_signal(combined_score)
    callout = (
        f"BTC is expected to {direction} by end of today (KSA), "
        f"targeting {expected_price:,.2f}."
    )

    left, right = st.columns([1.2, 1])
    with left:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown(f"<div class='badge'>{sentiment}</div>", unsafe_allow_html=True)
        st.markdown(f"<h3>{callout}</h3>", unsafe_allow_html=True)
        generated_local = now.astimezone(riyadh_tz)
        st.markdown(
            "<div class='metric-block'>"
            "<div class='metric-label'>Generated (KSA)</div>"
            f"<div class='metric-value'>{generated_local.strftime('%Y-%m-%d %I:%M %p')}</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<div class='metric-block'>"
            f"<div class='metric-label'>News window</div>"
            f"<div class='metric-value'>{window_label}</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<div class='metric-block'>"
            f"<div class='metric-label'>Combined signal</div>"
            f"<div class='metric-value'>{combined_score:+.3f}</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown(
            "<div class='metric-block'>"
            "<div class='metric-label'>BTC-USD last close (KSA)</div>"
            f"<div class='metric-value'>{futures.last_price:,.2f}</div>"
            f"<div class='metric-label'>"
            f"{futures.last_close_time.astimezone(riyadh_tz).strftime('%Y-%m-%d %I:%M %p')}"
            f"</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<div class='metric-block'>"
            "<div class='metric-label'>Previous close (KSA)</div>"
            f"<div class='metric-value'>{futures.yesterday_close:,.2f}</div>"
            f"<div class='metric-label'>"
            f"{futures.yesterday_close_time.astimezone(riyadh_tz).strftime('%Y-%m-%d %I:%M %p')}"
            f"</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        delta_color = "var(--accent-2)" if futures.pct_change_since_close >= 0 else "var(--danger)"
        st.markdown(
            "<div class='metric-block'>"
            "<div class='metric-label'>"
            "Change between those closes</div>"
            f"<div class='metric-value' style='color:{delta_color};'>"
            f"{futures.pct_change_since_close:+.2f}%</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<div class='metric-block'>"
            "<div class='metric-label'>Expected move vs previous close</div>"
            f"<div class='metric-value'>{move_pct:+.2f}%</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("")
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<h3>Recent BTC headlines (KSA)</h3>", unsafe_allow_html=True)
    if not filtered:
        st.markdown("<div class='subtitle'>No recent headlines found.</div>", unsafe_allow_html=True)
    else:
        for item in filtered[:10]:
            st.markdown(
                "<div class='headline'>"
                f"<time>{item.published.astimezone(riyadh_tz).strftime('%Y-%m-%d %I:%M %p')}</time>"
                f"{item.title}"
                f"<span class='score'>{item.score:+.2f}</span>"
                "</div>",
                unsafe_allow_html=True,
            )
            if item.link:
                st.markdown(
                    f"<a href='{item.link}' target='_blank'>{item.link}</a>",
                    unsafe_allow_html=True,
                )
    st.markdown("</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
