import React, { useEffect, useRef, useState } from "react";

async function readResponse(response, fallback) {
  let data;
  try {
    data = await response.json();
  } catch {
    throw Error(fallback);
  }
  if (!response.ok)
    throw Error(typeof data.detail === "string" ? data.detail : fallback);
  return data;
}

export default function EvaluationPanel({
  dialogs,
  criteria,
  version,
  onResult,
}) {
  const [health, setHealth] = useState(null);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState("");
  const [error, setError] = useState("");
  const [history, setHistory] = useState(null);
  const [force, setForce] = useState(false);
  const [runningVersion, setRunningVersion] = useState(null);
  const mounted = useRef(false);
  const running = useRef(false);
  const onResultRef = useRef(onResult);
  const healthRequest = useRef(null);
  const historyRequest = useRef(null);
  const singleId = dialogs.length === 1 ? dialogs[0].id : null;
  onResultRef.current = onResult;

  async function refreshHealth() {
    healthRequest.current?.abort();
    const controller = new AbortController();
    healthRequest.current = controller;
    const timeout = setTimeout(() => controller.abort(), 10000);
    if (mounted.current) setHealth(null);
    try {
      const response = await fetch("/api/health", {
        signal: controller.signal,
      });
      const result = await readResponse(response, "Сервис оценки недоступен");
      if (mounted.current && healthRequest.current === controller)
        setHealth(result);
    } catch {
      if (mounted.current && healthRequest.current === controller)
        setHealth({ status: "offline" });
    } finally {
      clearTimeout(timeout);
    }
  }
  useEffect(() => {
    mounted.current = true;
    refreshHealth();
    return () => {
      mounted.current = false;
      healthRequest.current?.abort();
      historyRequest.current?.abort();
    };
  }, []);
  useEffect(() => {
    historyRequest.current?.abort();
    historyRequest.current = null;
    setHistory(null);
  }, [singleId]);

  async function run() {
    // Lock synchronously: two clicks in the same render must not duplicate requests.
    if (running.current || !dialogs.length) return;
    running.current = true;
    const batch = structuredClone({ dialogs, criteria, version, force });
    setBusy(true);
    setRunningVersion(batch.version);
    setError("");
    setHistory(null);
    const failures = [];
    let completed = 0;
    try {
      for (let i = 0; i < batch.dialogs.length; i++) {
        if (!mounted.current) break;
        const d = batch.dialogs[i];
        setProgress(
          `${i + 1}/${batch.dialogs.length} · ${d.id} — анализ и проверка…`,
        );
        try {
          const response = await fetch("/api/evaluate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              conversation_id: d.id,
              language: d.language,
              messages: d.messages.map(({ id, role, text, time }) => ({
                id,
                role,
                text,
                time,
              })),
              criteria: batch.criteria,
              version: batch.version,
              force: batch.force,
            }),
          });
          const result = await readResponse(
            response,
            "Сервис не вернул корректную оценку",
          );
          // Preserve the original ID if the user switches to another dialogue while waiting.
          onResultRef.current(d.id, result);
          completed++;
        } catch (e) {
          failures.push(`${d.id}: ${e.message}`);
        }
      }
    } finally {
      running.current = false;
      if (mounted.current) {
        setProgress(
          `Обработка завершена: ${completed}/${batch.dialogs.length} успешно`,
        );
        setError(failures.join("; "));
        setBusy(false);
        setRunningVersion(null);
        refreshHealth();
      }
    }
  }
  async function showHistory() {
    if (!singleId) return;
    historyRequest.current?.abort();
    const controller = new AbortController();
    historyRequest.current = controller;
    const timeout = setTimeout(() => controller.abort(), 15000);
    setError("");
    setHistory(null);
    try {
      const r = await fetch(`/api/history/${encodeURIComponent(singleId)}`, {
        signal: controller.signal,
      });
      const entries = await readResponse(r, "История недоступна");
      if (!Array.isArray(entries)) throw Error("Некорректный ответ истории");
      if (mounted.current && historyRequest.current === controller)
        setHistory(entries);
    } catch (e) {
      if (mounted.current && historyRequest.current === controller)
        setError(
          e.name === "AbortError"
            ? "Превышено время ожидания истории. Попробуйте снова."
            : e.message,
        );
    } finally {
      clearTimeout(timeout);
    }
  }
  return (
    <section className="ai-evaluation" aria-label="AI-оценка">
      <div>
        <strong>Оценка новых диалогов · Ollama</strong>
        <p>
          {health === null
            ? "Проверяется доступность модели…"
            : health.status === "ready"
              ? `Модель ${health.model} загружена; готовность генерации проверяется при оценке`
              : health.status === "offline"
                ? "Сервис оценки недоступен. Проверьте запуск Python API."
                : "Модель не загружена: запустите Ollama и загрузите модель по инструкции README"}
        </p>
        <p>
          {busy
            ? `Выполняется оценка по снимку чек-листа v${runningVersion}.`
            : `Применяется текущий чек-лист v${version}.`}{" "}
          {health?.strategy === "multi_agent"
            ? "Специалист по каждому критерию и финальный критик."
            : "Оценивание и независимая проверка критиком."}{" "}
          Цитаты проверяются по исходному тексту, итог рассчитывается на
          сервере.
        </p>
      </div>
      <button className="button" onClick={refreshHealth}>
        Проверить модель
      </button>
      <label>
        <input
          type="checkbox"
          checked={force}
          disabled={busy}
          onChange={(e) => setForce(e.target.checked)}
        />{" "}
        Пересчитать без кэша
      </label>
      <button
        className="button primary"
        disabled={busy || !dialogs.length}
        onClick={run}
      >
        {busy
          ? "Анализируется…"
          : `Оценить ${dialogs.length === 1 ? "диалог" : `диалоги (${dialogs.length})`}`}
      </button>
      {singleId && (
        <button className="button" onClick={showHistory}>
          История AI-оценок
        </button>
      )}
      <p role="status">{progress}</p>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {history?.length === 0 && (
        <p>Сохранённых AI-оценок этого диалога пока нет.</p>
      )}
      {history?.map((h) => (
        <details key={h.evaluationId}>
          <summary>
            {h.createdAt} · {h.model} · v{h.checklistVersion} · {h.score ?? "—"}
            /100
          </summary>
          <p>{h.summary}</p>
          {h.results.map((r) => (
            <p key={r.criterionId}>
              #{r.criterionId} · {r.answer} — {r.reason} «{r.quote}»
            </p>
          ))}
        </details>
      ))}
    </section>
  );
}
