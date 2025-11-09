from pydantic import BaseModel

class Position(BaseModel):
    slug: str
    title: str
    outcome: str
    price: float
    conditionId: str
    usdcSize: int | float

    