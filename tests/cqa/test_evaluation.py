import json

import httpx
import pytest

from cqa.service import Analysis, EvaluationRequest, Evaluator, Store, score, validate_analysis


def request():
    return EvaluationRequest.model_validate(
        {
            "conversation_id": "unseen-1",
            "language": "KZ",
            "version": 1,
            "messages": [
                {
                    "id": "m1",
                    "role": "operator",
                    "text": "Сәлеметсіз бе! Мен Алия.",
                    "time": "00:02",
                }
            ],
            "criteria": [
                {
                    "id": "g",
                    "title": "Контакт",
                    "description": "Представился",
                    "weight": 10,
                    "type": "binary",
                },
                {
                    "id": "s",
                    "title": "Шкала",
                    "description": "Полнота",
                    "weight": 20,
                    "type": "scale",
                    "scale": [0, 5, 10, 15, 20],
                },
                {
                    "id": "i",
                    "title": "Идентификация",
                    "description": "Проверил",
                    "weight": 20,
                    "type": "binary",
                    "naAllowed": True,
                    "naCondition": "Общий вопрос",
                },
                {
                    "id": "f",
                    "title": "Флаг",
                    "description": "Оскорбление",
                    "weight": 0,
                    "type": "flag",
                },
            ],
        }
    )


def analysis():
    return Analysis.model_validate(
        {
            "summary": "Проверена работа оператора",
            "results": [
                {
                    "criterionId": cid,
                    "answer": answer,
                    "reason": "Подтверждается исходной репликой",
                    "evidenceId": "m1",
                    "quote": "Мен Алия",
                    "checkedMessageIds": ["m1"],
                    "confidence": 0.9,
                }
                for cid, answer in [("g", "Да"), ("s", 15), ("i", "N/A"), ("f", "Нет")]
            ],
        }
    )


def test_weight_redistribution():
    r, a = request(), analysis()
    assert score(r.criteria, validate_analysis(r, a).results) == {"score": 83.33, "critical": False}
    a.results[-1].answer = "Да"
    assert score(r.criteria, a.results)["critical"] is True
    assert score(r.criteria, a.results)["score"] == 83.33


@pytest.mark.parametrize("change", ["quote", "scale", "missing", "duplicate", "range", "na"])
def test_reject_invented_evidence_or_invalid_result(change):
    a = analysis()
    if change == "quote":
        a.results[0].quote = "выдуманная цитата"
    if change == "scale":
        a.results[1].answer = 13
    if change == "missing":
        a.results.pop()
    if change == "duplicate":
        a.results[1].criterionId = "g"
    if change == "range":
        a.results[0].checkedMessageIds = ["missing"]
    if change == "na":
        a.results[0].answer = "N/A"
    with pytest.raises(ValueError):
        validate_analysis(request(), a)


async def test_real_pipeline_cache_and_checklist_invalidation(tmp_path):
    calls = []

    def respond(req):
        calls.append(json.loads(req.content))
        return httpx.Response(
            200, json={"message": {"content": analysis().model_dump_json()}, "eval_count": 20}
        )

    evaluator = Evaluator(Store(str(tmp_path / "history.db")), httpx.MockTransport(respond))
    result = await evaluator.evaluate(request())
    assert len(calls) == 2  # evaluator + critic, never a hard-coded result
    assert result["passes"] == 2
    assert result["tokens"] == 40
    assert (await evaluator.evaluate(request()))["cached"]
    assert len(calls) == 2
    changed = request()
    changed.criteria[0].description = "Новое правило"
    await evaluator.evaluate(changed)
    assert len(calls) == 4
    assert len(evaluator.store.history("unseen-1")) == 2
    assert calls[-1]["format"]["type"] == "object"


async def test_no_fake_success_when_model_offline(tmp_path):
    def fail(req):
        raise httpx.ConnectError("offline", request=req)

    evaluator = Evaluator(Store(str(tmp_path / "db")), httpx.MockTransport(fail))
    with pytest.raises(httpx.ConnectError):
        await evaluator.evaluate(request())
    assert evaluator.store.history("unseen-1") == []
