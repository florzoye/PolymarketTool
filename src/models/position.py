from pydantic import BaseModel

class Position(BaseModel):
    slug: str
    outcome: str
    conditionId: str
    usdcSize: int | float

    