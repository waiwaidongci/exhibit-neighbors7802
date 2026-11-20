from pydantic import BaseModel, Field


class ComparisonInput(BaseModel):
    run_a_id: int
    run_b_id: int
    name: str = Field(min_length=2, max_length=160)
