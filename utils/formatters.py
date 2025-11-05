def format_money(value: float) -> str:
    """Форматирует деньги: 12345.6 → $12 345.60"""
    return f"${value:,.2f}".replace(",", " ")

def format_pnl(pnl: float, percent: float) -> str:
    """Форматирует PnL с эмодзи и знаком процента"""
    sign = "📈" if pnl >= 0 else "📉"
    return f"{sign} {format_money(pnl)} ({percent:+.2f}%)"