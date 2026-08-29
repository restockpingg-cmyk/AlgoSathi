"""Local web dashboard for monitoring AlgoSathi's paper/live trading activity.

Reads the same SQLite trade log the runner writes to — run it alongside (or after) the
runner in a separate terminal:

    .venv\\Scripts\\pip install -e ".[dashboard]"
    .venv\\Scripts\\streamlit run scripts/dashboard.py
"""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import streamlit as st

from algosathi.analytics import equity_curve, summarize_by_symbol
from algosathi.config import get_settings
from algosathi.persistence.db import all_trades, get_session_factory

LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "algosathi.log"

st.set_page_config(page_title="AlgoSathi Dashboard", layout="wide")
st.title("AlgoSathi")

settings = get_settings()
session_factory = get_session_factory()
trades = all_trades(session_factory)

with st.sidebar:
    st.subheader("Session")
    st.write(f"Mode: **{settings.mode.value}**")
    st.write(f"Symbol: **{settings.yaml.symbol}**")
    st.write(f"Strategy: **{settings.yaml.strategy.name}**")
    if st.button("Refresh now"):
        st.rerun()
    auto_refresh = st.checkbox("Auto-refresh every 10s", value=False)

if not trades:
    st.info("No trades recorded yet. Run the bot (paper or live) to see activity here.")
else:
    summary = summarize_by_symbol(trades)
    total_pnl = summary["realized_pnl"].sum()
    open_positions = summary[summary["open_qty"] != 0]

    col1, col2, col3 = st.columns(3)
    col1.metric("Total realized P&L", f"{total_pnl:,.2f}")
    col2.metric("Total trades", len(trades))
    col3.metric("Open positions", len(open_positions))

    st.subheader("Per-symbol summary")
    st.dataframe(summary, use_container_width=True, hide_index=True)

    curve = equity_curve(trades)
    if not curve.empty:
        st.subheader("Realized P&L over time")
        st.line_chart(curve.set_index("timestamp")["cumulative_realized_pnl"])

    st.subheader("Trade history")
    trade_rows = pd.DataFrame(
        [
            {
                "timestamp": t.timestamp,
                "symbol": t.symbol,
                "side": t.side,
                "quantity": t.quantity,
                "price": t.price,
                "mode": t.mode,
            }
            for t in reversed(trades)
        ]
    )
    st.dataframe(trade_rows, use_container_width=True, hide_index=True)

with st.expander("Recent log lines"):
    if LOG_PATH.exists():
        lines = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()[-100:]
        st.code("\n".join(lines) or "(log file is empty)")
    else:
        st.write("No log file yet.")

if trades and auto_refresh:
    time.sleep(10)
    st.rerun()
