"""Generate a synthetic OHLC candle CSV with a few clear trend reversals, for demoing the
runner in paper mode without needing real Upstox credentials.

    python scripts/generate_sample_data.py
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "sample" / "infy_sample.csv"


def build_close_series() -> list[float]:
    random.seed(42)
    price = 1500.0
    closes = []
    # Alternate multi-day up/down trends so the SMA crossover strategy has several
    # unambiguous entries and exits, plus small daily noise for realism.
    trend_lengths = [40, 35, 45, 30, 50, 35]
    directions = [1, -1, 1, -1, 1, -1]
    for length, direction in zip(trend_lengths, directions):
        for _ in range(length):
            price += direction * random.uniform(1.5, 4.0) + random.uniform(-1.0, 1.0)
            closes.append(round(price, 2))
    return closes


def main() -> None:
    closes = build_close_series()
    start = datetime(2026, 6, 1, 9, 15)
    rows = []
    for i, close in enumerate(closes):
        open_ = closes[i - 1] if i > 0 else close
        high = max(open_, close) + random.uniform(0, 1.5)
        low = min(open_, close) - random.uniform(0, 1.5)
        rows.append(
            {
                "timestamp": start + timedelta(minutes=5 * i),
                "open": open_,
                "high": round(high, 2),
                "low": round(low, 2),
                "close": close,
                "volume": random.randint(1000, 5000),
            }
        )

    df = pd.DataFrame(rows)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_PATH, index=False)
    print(f"Wrote {len(df)} candles to {OUT_PATH}")


if __name__ == "__main__":
    main()
