"""Local CQA API and production frontend host."""

import json
import os
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from cqa.service import EvaluationRequest, Evaluator

app = FastAPI(title="Freedom CQA", version="1.0.0")
evaluator = Evaluator()


@app.get("/api/health")
async def health():
    try:
        async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
            response = await client.get(evaluator.url + "/api/tags")
            response.raise_for_status()
            names = [m["name"] for m in response.json()["models"]]
        ready = evaluator.model in names
    except (httpx.HTTPError, KeyError, ValueError):
        ready = False
    return {"status": "ready" if ready else "model_unavailable", "model": evaluator.model}


@app.post("/api/evaluate")
async def evaluate(request: EvaluationRequest):
    try:
        return await evaluator.evaluate(request)
    except httpx.HTTPError as exc:
        raise HTTPException(
            503, "Ollama недоступна или модель не загружена. Проверьте /api/health и ollama pull."
        ) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/history/{conversation_id}")
def history(conversation_id: str):
    return evaluator.store.history(conversation_id)


@app.get("/api/organizer")
async def organizer(group_id: str = "DEV"):
    # Fixed server-side URL; never accept arbitrary browser URLs or expose signatures.
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    url = os.getenv("CQA_DATA_URL")
    if not url:
        raise HTTPException(503, "Задайте CQA_DATA_URL на сервере или импортируйте JSON-файл")
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    query["group_id"] = group_id
    target = urlunsplit(parts._replace(query=urlencode(query)))
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(target)
            response.raise_for_status()
            data = response.json()
        if data.get("isSuccess") is not True:
            raise ValueError("Ошибка организаторов")
        return data
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, "API организаторов недоступен; используйте импорт JSON") from exc


class Workspace(BaseModel):
    revision: int = Field(ge=0)
    data: dict


@app.get("/api/workspace")
def get_workspace():
    with evaluator.store.connect() as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS workspace "
            "(id INTEGER PRIMARY KEY, revision INTEGER, body TEXT)"
        )
        row = db.execute("SELECT revision,body FROM workspace WHERE id=1").fetchone()
    return (
        {"revision": row[0], "data": json.loads(row[1])} if row else {"revision": 0, "data": None}
    )


@app.put("/api/workspace")
def put_workspace(workspace: Workspace):
    body = json.dumps(workspace.data, ensure_ascii=False)
    if len(body.encode()) > 10_000_000:
        raise HTTPException(413, "Рабочее пространство превышает 10 МБ")
    get_workspace()
    with evaluator.store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT revision FROM workspace WHERE id=1").fetchone()
        revision = row[0] if row else 0
        if revision != workspace.revision:
            raise HTTPException(
                409,
                "Данные изменены в другой вкладке. "
                "Экспортируйте локальные изменения перед обновлением.",
            )
        db.execute("INSERT OR REPLACE INTO workspace VALUES (1,?,?)", (revision + 1, body))
    return {"revision": revision + 1}


static = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if static.exists():
    app.mount("/", StaticFiles(directory=static, html=True), name="frontend")
