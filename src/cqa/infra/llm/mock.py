"""Synthetic provider for infrastructure tests; never claims model accuracy."""


class MockProvider:
    model = "synthetic-mock-v1"
    is_mock = True

    def configuration(self):
        return {"provider": "mock", "model": self.model}

    async def generate(self, messages, schema):
        return {"is_mock": True, "notice": "Synthetic provider; use MockEvaluator for evaluation"}
