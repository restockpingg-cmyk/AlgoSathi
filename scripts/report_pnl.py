"""Print a realized P&L and open-position summary from the trades recorded in SQLite.

    python scripts/report_pnl.py
"""

from __future__ import annotations

from algosathi.analytics import summarize_by_symbol
from algosathi.persistence.db import all_trades, get_session_factory


def main() -> None:
    session_factory = get_session_factory()
    trades = all_trades(session_factory)
    if not trades:
        print("No trades recorded yet.")
        return

    summary = summarize_by_symbol(trades)
    print(summary.to_string(index=False, formatters={"realized_pnl": "{:.2f}".format, "avg_price": "{:.2f}".format}))
    print(f"\nTotal realized P&L: {summary['realized_pnl'].sum():.2f}")
    print(f"Total trades: {len(trades)}")


if __name__ == "__main__":
    main()
