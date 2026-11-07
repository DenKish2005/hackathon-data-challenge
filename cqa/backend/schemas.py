"""Public request models; never accept arbitrary remote URLs."""
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class BaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class DatasetImport(BaseModel):
    source: Literal["local", "api", "payload"] = "local"
    group_id: Literal["DEV", "CONTROL"] = "DEV"
    payload: dict[str, Any] | None = None
    @model_validator(mode="after")
    def check_payload(self):
        if (self.source == "payload") != (self.payload is not None):
            raise ValueError("payload is required only for source=payload")
        return self


class ChecklistCreate(BaseModel):
    checklist_id: str = Field(min_length=1, max_length=100)
    criteria: list[dict[str, Any]] = Field(min_length=1)
    sections: list[dict[str, Any]] = Field(default_factory=list)
    expected_version: int | None = Field(default=None, ge=1)


class EvaluationCreate(BaseModel):
    conversation_id: str
    group_id: str | None = None
    checklist_id: str = "official"
    checklist_version: int | None = Field(default=None, ge=1)
    force: bool = False


class AppealCreate(BaseModel):
    evaluation_id: str
    criterion_id: str
    comment: str = Field(min_length=1, max_length=5000)


class AppealReviewCreate(BaseModel):
    decision: Literal["upheld", "rejected"]
    reason: str = Field(min_length=1, max_length=5000)
    revised_answer: str | int | None = None
    @model_validator(mode="after")
    def check(self):
        if self.decision == "upheld" and self.revised_answer is None:
            raise ValueError("revised_answer required when upheld")
        if self.decision == "rejected" and self.revised_answer is not None:
            raise ValueError("revised_answer must be absent when rejected")
        return self
