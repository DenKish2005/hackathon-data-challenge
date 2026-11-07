"""Optional deterministic classifier placeholder; no invented categories."""


class BasicClassifier:
    async def classify(self, extracted: dict, categories: list[str]) -> dict:
        return {"categories": [], "labels": [], "supporting_message_references": [], "available_categories": categories, "is_mock": True}
