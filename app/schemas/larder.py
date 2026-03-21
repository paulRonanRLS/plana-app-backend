from datetime import datetime

from pydantic import BaseModel, field_validator


class LarderItemResponse(BaseModel):
    id: str
    name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class LarderAddRequest(BaseModel):
    names: list[str]

    @field_validator("names")
    @classmethod
    def validate_names(cls, v: list[str]) -> list[str]:
        if len(v) < 1:
            raise ValueError("At least one name is required")
        if len(v) > 50:
            raise ValueError("Maximum 50 items per request")
        cleaned: list[str] = []
        seen: set[str] = set()
        for name in v:
            name = name.strip().lower()
            if not name:
                continue
            if name not in seen:
                seen.add(name)
                cleaned.append(name)
        if not cleaned:
            raise ValueError("At least one non-empty name is required")
        return cleaned


class LarderListResponse(BaseModel):
    items: list[LarderItemResponse]
    total: int
