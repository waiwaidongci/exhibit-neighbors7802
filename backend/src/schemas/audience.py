from pydantic import BaseModel, Field


class GroupShare(BaseModel):
    key: str = Field(min_length=1, max_length=60)
    label: str = Field(min_length=1, max_length=120)
    share: float


class ForbiddenPair(BaseModel):
    age: str = Field(min_length=1, max_length=60)
    method: str = Field(min_length=1, max_length=60)


class VisitorCell(BaseModel):
    age: str = Field(min_length=1, max_length=60)
    method: str = Field(min_length=1, max_length=60)


class AudienceInput(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    age_groups: list[GroupShare] = Field(min_length=1, max_length=60)
    visit_methods: list[GroupShare] = Field(min_length=1, max_length=60)
    forbidden: list[ForbiddenPair] = Field(default_factory=list, max_length=3600)
    visitor_cells: dict[str, VisitorCell] = Field(default_factory=dict)
