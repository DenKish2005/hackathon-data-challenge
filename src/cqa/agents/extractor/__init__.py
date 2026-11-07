"""Conservative deterministic facts; no unverified semantic claims."""

from typing import Protocol

from cqa.backend.schemas import ConversationDetail


class Extractor(Protocol):
    def configuration(self) -> dict: ...

    async def extract(self, conversation: ConversationDetail) -> dict: ...


class BasicExtractor:
    def configuration(self):
        return {"name": "BasicExtractor", "version": 1}

    async def extract(self, conversation):
        operators = [m.message_id for m in conversation.messages if m.speaker == "operator"]
        return {
            "facts": {
                "language": conversation.language,
                "channel": conversation.channel,
                "message_count": len(conversation.messages),
            },
            "message_references": operators,
            "detected_issues": [] if operators else ["no_operator_messages"],
            "uncertainty_markers": ["Semantic facts have not been inferred"],
        }
