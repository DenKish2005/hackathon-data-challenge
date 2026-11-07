"""Shared appeal write contracts for REST and the workspace adapter."""

from typing import Literal

from pydantic import Field, model_validator

from cqa.backend.schemas import Schema
from cqa.infra.orchestrator.pipeline import Finding


class AppealCreate(Schema):
    evaluation_id: str = Field(min_length=1, max_length=100)
    criterion_id: str = Field(min_length=1, max_length=100)
    comment: str = Field(min_length=1, max_length=5000)


class ReviewRequest(Schema):
    decision: Literal["accepted", "rejected"]
    reason: str = Field(min_length=1, max_length=5000)
    base_revision: int = Field(ge=0)
    replacement: Finding | None = None

    @model_validator(mode="after")
    def valid(self):
        if (self.decision == "accepted") != (self.replacement is not None):
            raise ValueError("Accepted review requires replacement; rejected review forbids it")
        return self
