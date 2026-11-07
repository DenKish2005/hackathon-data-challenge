import React, { useEffect, useState } from "react";

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
  const [history, setHistory] = useState([]);
  const [force, setForce] = useState(false);
  useEffect(() => {
    fetch("/api/health")
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => setHealth({ status: "offline" }));
  }, []);
  async function run() {
    setBusy(true);
    setError("");
    const failures = [];
    for (let i = 0; i < dialogs.length; i++) {
      const d = dialogs[i];
      setProgress(`${i + 1}/${dialogs.length} · ${d.id} — анализ и проверка…`);
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
            criteria,
            version,
            force,
          }),
        });
        const result = await response.json();
        if (!response.ok)
          throw Error(
            typeof result.detail === "string"
              ? result.detail
              : "Ошибка валидации запроса",
          );
        onResult(d.id, result);
      } catch (e) {
        failures.push(`${d.id}: ${e.message}`);
      }
    }
    setProgress("Обработка завершена");
    setError(failures.join("; "));
    setBusy(false);
  }
  async function showHistory() {
    try {
      const r = await fetch(
        `/api/history/${encodeURIComponent(dialogs[0].id)}`,
      );
      if (!r.ok) throw Error("История недоступна");
      setHistory(await r.json());
    } catch (e) {
      setError(e.message);
    }
  }
  return (
    <section className="ai-evaluation" aria-label="AI-оценка">
      <div>
        <strong>Оценка новых диалогов · Ollama</strong>
        <p>
          {health?.status === "ready"
            ? `Модель ${health.model} готова`
            : "Модель не готова: запустите Ollama и загрузите модель по инструкции README"}
        </p>
        <p>
          Применяется текущий чек-лист v{version}. Два прохода, проверяемые
          цитаты, расчёт на сервере. Синтетические примеры помечены отдельно.
        </p>
      </div>
      <label>
        <input
          type="checkbox"
          checked={force}
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
      {dialogs.length === 1 && (
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
      {history.map((h) => (
        <details key={h.evaluationId}>
          <summary>
            {h.createdAt} · {h.model} · v{h.checklistVersion} · {h.score}/100
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
