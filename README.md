# Bitcoin Futures News Sentiment

This project scrapes the most recent Bitcoin news, filters to today (UTC), and combines
news sentiment with Yahoo Finance BTC-USD pricing to infer whether BTC is likely to end
the day higher or lower, plus an expected price target vs yesterday's UTC close.

## What it does
- Pulls BTC-focused headlines from multiple RSS sources.
- Filters to items published today (UTC); falls back to last 24h if none.
- Scores each headline with a lightweight keyword sentiment model.
- Blends news sentiment with recent BTC-USD price moves from Yahoo Finance.
- Estimates an expected move based on the last 7 days of absolute daily returns.

## Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run
```bash
python main.py
```

## Dashboard
```bash
streamlit run app.py
```

## Notes
- This is a heuristic signal, not financial advice.
- The model is deliberately simple so you can extend it with better NLP or
  structured indicators.
