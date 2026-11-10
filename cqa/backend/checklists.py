"""The published eight CQA criteria; scoring belongs to the AI teammate."""
from fastapi import HTTPException

OFFICIAL = [
    {"id": "01", "title": "Установление контакта", "type": "binary", "weight": 10, "naAllowed": False},
    {"id": "02", "title": "Выявление потребности", "type": "binary", "weight": 15, "naAllowed": True},
    {"id": "03", "title": "Идентификация", "type": "binary", "weight": 20, "naAllowed": True},
    {"id": "04", "title": "Корректная и полная консультация", "type": "scale", "weight": 20, "scale": [0, 5, 10, 15, 20], "naAllowed": True},
    {"id": "05", "title": "Эмпатия и клиентоориентированность", "type": "binary", "weight": 15, "naAllowed": False},
    {"id": "06", "title": "Управление диалогом, скорость и грамотность", "type": "scale", "weight": 15, "scale": [0, 4, 7, 10], "naAllowed": False},
    {"id": "07", "title": "Завершение", "type": "binary", "weight": 5, "naAllowed": True},
    {"id": "08", "title": "Грубые ошибки", "type": "flag", "weight": 0, "naAllowed": False},
]


def validate_criteria(criteria: list[dict]):
    ids = [str(item.get("id", "")) for item in criteria]
    if len(ids) != len(set(ids)) or any(not item for item in ids):
        raise HTTPException(422, "Criteria require unique nonempty IDs")
    for c in criteria:
        kind = c.get("type")
        weight = c.get("weight")
        if kind not in {"binary", "scale", "flag"} or type(weight) not in {int, float} or not 0 <= weight <= 100:
            raise HTTPException(422, "Invalid criterion type or weight")
        if type(c.get("naAllowed", False)) is not bool:
            raise HTTPException(422, "naAllowed must be boolean")
        if kind == "scale":
            vals = c.get("scale")
            if not isinstance(vals, list) or not vals or any(type(v) not in (int, float) for v in vals) or vals != sorted(set(vals)) or vals[0] != 0 or vals[-1] <= 0:
                raise HTTPException(422, "Invalid numeric scale")
        if kind == "flag" and weight != 0:
            raise HTTPException(422, "Flags have zero weight")


def validate_answer(criterion: dict, answer):
    if answer == "N/A":
        return bool(criterion.get("naAllowed"))
    if criterion["type"] == "scale":
        return type(answer) in (int, float) and answer in criterion["scale"]
    return answer in ("Да", "Нет")
