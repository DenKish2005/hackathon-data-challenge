"""Optional structural extraction; does not infer customer intent or evaluate quality."""


class BasicExtractor:
    async def extract(self, conversation: dict) -> dict:
        messages = conversation.get("messages", [])
        return {"structured_facts": {"message_count": len(messages), "operator_message_count": sum(m["speaker"] == "operator" for m in messages)},
                "message_references": [m["message_id"] for m in messages], "detected_issues": [], "uncertainty_markers": ["Semantic extraction not configured"]}
