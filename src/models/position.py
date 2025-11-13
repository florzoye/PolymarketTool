from pydantic import BaseModel

class Position(BaseModel):
    slug: str
    title: str
    outcome: str
    price: float
    token_id: str | int 
    conditionId: str
    usdcSize: int | float

    