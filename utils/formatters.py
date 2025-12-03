def format_money(value: float) -> str:
    return f"${value:,.2f}".replace(",", " ")

def format_pnl(pnl: float, percent: float) -> str:
    sign = "📈" if pnl >= 0 else "📉"
    return f"{sign} {format_money(pnl)} ({percent:+.2f}%)"