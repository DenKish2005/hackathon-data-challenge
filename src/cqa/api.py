"""Local CQA API and production frontend host."""

import os
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from cqa.service import EvaluationRequest, Evaluator
from cqa.workspace import WorkspaceConflict, read_workspace, write_workspace

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
    return {
        "status": "ready" if ready else "model_unavailable",
        "model": evaluator.model,
        "strategy": evaluator.strategy,
        "agentConcurrency": evaluator.agent_concurrency,
    }


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


@app.get("/api/history/{conversation_id:path}")
def history(conversation_id: str):
    return evaluator.store.history(conversation_id)


@app.get("/api/organizer")
async def organizer(group_id: str = Query(default="DEV", pattern=r"^[A-Za-z0-9_-]{1,64}$")):
    # Fixed server-side URL; never accept arbitrary browser URLs or expose signatures.
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    url = os.getenv("CQA_DATA_URL")
    if not url:
        raise HTTPException(503, "Задайте CQA_DATA_URL на сервере или импортируйте JSON-файл")
    try:
        parts = urlsplit(url)
        if (
            parts.scheme != "https"
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
        ):
            raise ValueError("Invalid organizer URL")
        # Accessing port also validates its syntax. Never include this URL in client errors.
        _ = parts.port
        query = [(key, value) for key, value in parse_qsl(parts.query) if key != "group_id"]
        query.append(("group_id", group_id))
        target = urlunsplit(parts._replace(query=urlencode(query)))
    except ValueError as exc:
        raise HTTPException(503, "Проверьте настройку CQA_DATA_URL на сервере") from exc
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10)) as client:
            response = await client.get(target)
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, (dict, list)):
            raise ValueError("Некорректный ответ организаторов")
        if isinstance(data, dict) and data.get("isSuccess") is False:
            raise ValueError("Ошибка организаторов")
        container = data.get("data", data) if isinstance(data, dict) else None
        records = (
            data
            if isinstance(data, list)
            else (container.get("records") if isinstance(container, dict) else None)
        )
        if not isinstance(records, list) or not records or len(records) > 1000:
            raise ValueError("Нужен массив из 1–1000 записей records")
        return data
    except httpx.TimeoutException as exc:
        raise HTTPException(
            504, "Источник диалогов не ответил вовремя. Повторите загрузку."
        ) from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, "API организаторов недоступен; используйте импорт JSON") from exc


class Workspace(BaseModel):
    revision: int = Field(ge=0)
    data: dict


@app.get("/api/workspace")
def get_workspace():
    return read_workspace(evaluator.store)


@app.put("/api/workspace")
def put_workspace(workspace: Workspace):
    try:
        return write_workspace(evaluator.store, workspace.revision, workspace.data)
    except WorkspaceConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(413, str(exc)) from exc


static = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if static.exists():
    app.mount("/", StaticFiles(directory=static, html=True), name="frontend")
