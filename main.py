#!/usr/bin/env python3
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import re
import sys
import time
from typing import Iterable, List, Optional, Tuple

import feedparser
import requests


RSS_SOURCES = [
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
    "https://cryptopanic.com/news/rss/bitcoin/",
]

USER_AGENT = "bitcoin-news-sentiment/0.1"
YAHOO_SYMBOL = "BTC-USD"

POSITIVE_WORDS = {
    "beat",
    "breakout",
    "bull",
    "bullish",
    "buy",
    "demand",
    "gain",
    "green",
    "growth",
    "higher",
    "inflow",
    "jump",
    "optimism",
    "outperform",
    "rally",
    "recover",
    "resilient",
    "rise",
    "risk-on",
    "strong",
    "surge",
    "up",
}

NEGATIVE_WORDS = {
    "bear",
    "bearish",
    "crash",
    "decline",
    "drop",
    "fear",
    "headwind",
    "lower",
    "loss",
    "liquidation",
    "outflow",
    "plunge",
    "pressure",
    "risk-off",
    "sell",
    "selloff",
    "slump",
    "weak",
    "worse",
}


@dataclass(frozen=True)
class NewsItem:
    title: str
    link: str
    published: datetime
    summary: str
    score: float


@dataclass(frozen=True)
class FuturesSnapshot:
    last_price: float
    last_close_time: datetime
    yesterday_close: float
    yesterday_close_time: datetime
    pct_change_since_close: float
    avg_abs_daily_return: float


def _to_datetime(parsed: Optional[Tuple]) -> Optional[datetime]:
    if not parsed:
        return None
    return datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc)


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _score_text(text: str) -> float:
    tokens = re.findall(r"[a-zA-Z']+", text.lower())
    if not tokens:
        return 0.0
    positives = sum(1 for t in tokens if t in POSITIVE_WORDS)
    negatives = sum(1 for t in tokens if t in NEGATIVE_WORDS)
    if positives == 0 and negatives == 0:
        return 0.0
    return (positives - negatives) / max(1, positives + negatives)


def fetch_news(sources: Iterable[str]) -> List[NewsItem]:
    headers = {"User-Agent": USER_AGENT}
    items: List[NewsItem] = []
    seen = set()

    for url in sources:
        feed = feedparser.parse(url, request_headers=headers)
        for entry in feed.entries:
            published = _to_datetime(
                entry.get("published_parsed") or entry.get("updated_parsed")
            )
            if not published:
                continue
            title = _clean_text(entry.get("title", ""))
            link = entry.get("link", "")
            summary = _clean_text(entry.get("summary", ""))
            dedupe_key = (title.lower(), link)
            if not title or dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            score = _score_text(f"{title} {summary}")
            items.append(
                NewsItem(
                    title=title,
                    link=link,
                    published=published,
                    summary=summary,
                    score=score,
                )
            )

    items.sort(key=lambda item: item.published, reverse=True)
    return items


def filter_recent(
    items: Iterable[NewsItem],
    now: datetime,
    today_only: bool,
) -> Tuple[List[NewsItem], str]:
    today_items = [item for item in items if item.published.date() == now.date()]
    if today_items:
        return today_items, "today"
    if today_only:
        return [], "none"
    cutoff = now - timedelta(hours=24)
    recent_items = [item for item in items if item.published >= cutoff]
    return recent_items, "last_24h"


def fetch_price_snapshot(
    symbol: str, timeout: int, retries: int
) -> FuturesSnapshot:
    chart_url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{symbol}?range=7d&interval=1d&includePrePost=false"
    )
    headers = {"User-Agent": USER_AGENT}

    def fetch_json(url: str) -> dict | list:
        last_exc: Optional[Exception] = None
        for attempt in range(1, retries + 1):
            try:
                response = requests.get(url, headers=headers, timeout=timeout)
                response.raise_for_status()
                return response.json()
            except requests.RequestException as exc:
                last_exc = exc
                if attempt < retries:
                    time.sleep(1.5 * attempt)
        raise RuntimeError(f"Failed to fetch {url}") from last_exc

    chart = fetch_json(chart_url)
    result = chart.get("chart", {}).get("result", [])
    if not result:
        raise RuntimeError("No chart data returned from Yahoo Finance.")
    series = result[0]
    timestamps = series.get("timestamp", [])
    indicators = series.get("indicators", {}).get("quote", [])
    if not timestamps or not indicators:
        raise RuntimeError("Yahoo Finance response missing timestamps or prices.")
    closes = indicators[0].get("close", [])
    if not closes or len(closes) < 2:
        raise RuntimeError("Not enough close data from Yahoo Finance.")

    cleaned: List[Tuple[int, float]] = []
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        cleaned.append((ts, float(close)))
    if len(cleaned) < 2:
        raise RuntimeError("Not enough valid close data from Yahoo Finance.")

    cleaned.sort(key=lambda item: item[0])
    last_close_ts, last_close = cleaned[-1]
    yesterday_close_ts, yesterday_close = cleaned[-2]
    last_close_time = datetime.fromtimestamp(last_close_ts, tz=timezone.utc)
    yesterday_close_time = datetime.fromtimestamp(yesterday_close_ts, tz=timezone.utc)
    pct_change_since_close = (last_close - yesterday_close) / yesterday_close * 100.0
    returns: List[float] = []
    for i in range(1, len(cleaned)):
        prev_close = cleaned[i - 1][1]
        close = cleaned[i][1]
        if prev_close > 0:
            returns.append(abs((close - prev_close) / prev_close))
    avg_abs_daily_return = sum(returns) / len(returns) if returns else 0.0

    return FuturesSnapshot(
        last_price=last_close,
        last_close_time=last_close_time,
        yesterday_close=yesterday_close,
        yesterday_close_time=yesterday_close_time,
        pct_change_since_close=pct_change_since_close,
        avg_abs_daily_return=avg_abs_daily_return,
    )


def combine_signal(news_items: List[NewsItem], futures: FuturesSnapshot) -> float:
    if news_items:
        news_score = sum(item.score for item in news_items) / len(news_items)
    else:
        news_score = 0.0

    price_score = max(-1.0, min(1.0, futures.pct_change_since_close / 5.0))
    combined = (0.7 * news_score) + (0.3 * price_score)
    return combined


def expected_move_pct(combined_score: float, futures: FuturesSnapshot) -> float:
    scaled = max(-1.0, min(1.0, combined_score))
    return scaled * futures.avg_abs_daily_return * 100.0


def format_report(
    news_items: List[NewsItem],
    source_label: str,
    futures: FuturesSnapshot,
    combined_score: float,
    now: datetime,
    limit: int,
) -> str:
    if combined_score >= 0.15:
        sentiment = "bullish"
        long_bias = "favored"
        short_bias = "disfavored"
        direction = "increase"
    elif combined_score <= -0.15:
        sentiment = "bearish"
        long_bias = "disfavored"
        short_bias = "favored"
        direction = "decrease"
    else:
        sentiment = "neutral"
        long_bias = "balanced"
        short_bias = "balanced"
        direction = "flat to mixed"
    move_pct = expected_move_pct(combined_score, futures)
    expected_price = futures.yesterday_close * (1 + move_pct / 100.0)
    lines = [
        "Bitcoin Sentiment Report",
        f"Generated (UTC): {now.strftime('%Y-%m-%d %H:%M')}",
        f"News window used: {source_label}",
        (
            "BTC-USD last close: "
            f"{futures.last_price:,.2f} "
            f"at {futures.last_close_time.strftime('%Y-%m-%d %H:%M')} UTC"
        ),
        (
            "Previous close: "
            f"{futures.yesterday_close:,.2f} "
            f"at {futures.yesterday_close_time.strftime('%Y-%m-%d %H:%M')} UTC"
        ),
        f"Change between those closes: {futures.pct_change_since_close:+.2f}%",
        f"Avg abs daily move (7d): {futures.avg_abs_daily_return * 100.0:.2f}%",
        f"Combined signal: {combined_score:+.3f}",
        f"Overall sentiment: {sentiment}",
        f"Long bias: {long_bias}",
        f"Short bias: {short_bias}",
        f"Prediction: BTC is expected to be {direction} by end of today (UTC).",
        f"Expected move vs yesterday close: {move_pct:+.2f}%",
        f"Expected price target: {expected_price:,.2f}",
        "",
        f"Top {min(limit, len(news_items))} recent headlines:",
    ]
    for item in news_items[:limit]:
        lines.append(
            f"- {item.published.strftime('%H:%M')} {item.title} "
            f"(score {item.score:+.2f})"
        )
        if item.link:
            lines.append(f"  {item.link}")
    if not news_items:
        lines.append("- No recent items matched the filter.")
    return "\n".join(lines)


def main() -> int:
    now = datetime.now(timezone.utc)
    max_articles = 40
    timeout = 25
    retries = 3

    news = fetch_news(RSS_SOURCES)
    filtered, window_label = filter_recent(news, now, today_only=True)
    filtered = filtered[:max_articles]

    try:
        futures = fetch_price_snapshot(YAHOO_SYMBOL, timeout, retries)
    except Exception as exc:
        print(
            "Failed to fetch Yahoo Finance data. "
            "Check network access and try again.\n"
            f"Error: {exc}",
            file=sys.stderr,
        )
        return 1

    combined_score = combine_signal(filtered, futures)
    report = format_report(
        news_items=filtered,
        source_label=window_label,
        futures=futures,
        combined_score=combined_score,
        now=now,
        limit=min(10, max_articles),
    )
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
