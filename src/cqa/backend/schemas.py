"""Stable public contracts; evaluator reuses the existing criterion vocabulary."""

import re
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cqa.service import Criterion


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, allow_inf_nan=False)


class TranscriptMessage(Schema):
    timestamp: str = Field(max_length=100)
    speaker: Literal["client", "operator", "bot", "system"]
    text: str = Field(max_length=15000)


class Record(Schema):
    model_config = ConfigDict(extra="allow")
    conversation_id: str = Field(min_length=1, max_length=200, pattern=r"^[\w.:-]+$")
    channel: Literal["agent chat", "voice call"]
    language: Literal["RU", "KZ", "EN"]
    transcript: list[TranscriptMessage] = Field(min_length=1, max_length=500)
    audio_url: str | None = Field(default=None, max_length=8000)

    @model_validator(mode="after")
    def valid(self):
        if sum(len(m.text) for m in self.transcript) > 120000:
            raise ValueError("Transcript too long")
        if self.channel == "voice call" and not self.audio_url:
            raise ValueError("Voice calls require audio_url")
        if self.audio_url:
            url = urlsplit(self.audio_url)
            if url.scheme != "https" or not url.hostname or url.username or url.password:
                raise ValueError("Audio requires HTTPS")
        for m in self.transcript:
            if self.channel == "agent chat":
                if not re.fullmatch(r"\d{2,}:[0-5]\d", m.timestamp):
                    raise ValueError("Chat timestamp must be MM:SS")
            else:
                stamp = datetime.fromisoformat(m.timestamp.replace("Z", "+00:00"))
                if stamp.utcoffset() is None:
                    raise ValueError("Call timestamp requires timezone")
        return self


class Dataset(Schema):
    dataset_group_id: str = Field(min_length=1, max_length=100)
    total_records: int = Field(ge=1, le=1000)
    records: list[Record] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def counts(self):
        if self.total_records != len(self.records):
            raise ValueError("total_records does not match records")
        if len({r.conversation_id for r in self.records}) != len(self.records):
            raise ValueError("Duplicate conversation_id")
        return self


class DatasetEnvelope(Schema):
    error: str = ""
    isSuccess: Literal[True]
    data: Dataset


class ImportRequest(Schema):
    source: Literal["local", "organizer"] = "local"
    payload: DatasetEnvelope | None = None
    group_id: str = Field(default="DEV", min_length=1, max_length=100)

    @model_validator(mode="after")
    def source_data(self):
        if (self.source == "local") != (self.payload is not None):
            raise ValueError(
                "Local import requires payload; organizer import accepts group_id only"
            )
        return self


class ImportResult(Schema):
    dataset_group_id: str
    total_records: int
    imported: int
    skipped: int


class MessageView(Schema):
    message_id: str
    message_index: int
    speaker: str
    timestamp_original: str
    text: str


class ConversationView(Schema):
    conversation_id: str
    dataset_group_id: str
    channel: str
    language: str
    audio_url: str | None
    imported_at: str


class ConversationDetail(ConversationView):
    messages: list[MessageView]
    # Raw organizer record stays server-side; it may contain extra private metadata.


class ChecklistCreate(Schema):
    checklist_id: str = Field(min_length=1, max_length=100, pattern=r"^[\w.-]+$")
    base_version: int | None = Field(default=None, ge=1)
    criteria: list[Criterion] = Field(min_length=1, max_length=50)
    sections: list[dict] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def unique(self):
        if len({c.id for c in self.criteria}) != len(self.criteria):
            raise ValueError("Duplicate criterion ID")
        return self


class ChecklistView(Schema):
    checklist_id: str
    version: int
    criteria: list[Criterion]
    sections: list[dict]
    created_at: str
