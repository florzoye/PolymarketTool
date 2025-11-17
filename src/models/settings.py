from pydantic import BaseModel

class Settings(BaseModel):
    exp_at: int             # начало мониторинга
    started_at: int         # конец мониторинга

    first_bet: bool         # первая ли сделка на этот рынок (по дефолту: в районе 30 сделок)
    min_amount: int | float # минимальное количество вложенных средств 

    min_quote: float          # минимальная цена котировки рынка
    max_quote: float          # максимальная цена котировки рынка

    sl_percent: float = None   # Stop_loss: например -25%
    tp_percent: float = None   # Take_profit: например +40%