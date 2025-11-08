from pydantic import BaseModel

class Position(BaseModel):
    conditionId: str
    usdcSize: int | float
    slug: str
    outcome: str
    