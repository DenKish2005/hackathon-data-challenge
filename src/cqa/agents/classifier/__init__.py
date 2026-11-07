"""Only configured fact matches become labels; no invented categories."""

from typing import Protocol


class Classifier(Protocol):
    def configuration(self) -> dict: ...

    async def classify(self, extraction: dict, categories: dict) -> dict: ...


class BasicClassifier:
    def configuration(self):
        return {"name": "BasicClassifier", "version": 1}

    async def classify(self, extraction, categories):
        labels = [
            label
            for label, expected in categories.items()
            if expected and all(extraction["facts"].get(k) == v for k, v in expected.items())
        ]
        return {
            "categories": labels,
            "labels": labels,
            "message_references": extraction["message_references"] if labels else [],
        }
