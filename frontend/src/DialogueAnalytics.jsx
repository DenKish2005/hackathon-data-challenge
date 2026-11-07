import React from "react";
import {
  ArrowUpRight,
  AudioLines,
  CheckCircle2,
  CircleHelp,
  Clock3,
  FileText,
  Globe2,
  MessageCircle,
  ShieldAlert,
  ShieldCheck,
  UserRound,
} from "lucide-react";
import { initialCriteria, scoreEvaluation } from "./data";
import "./dialogue-analytics.css";

const shortTitles = {
  1: "Установление контакта",
  2: "Выявление потребности",
  3: "Идентификация",
  4: "Корректность консультации",
  5: "Эмпатия",
  6: "Ведение диалога",
  7: "Завершение",
};

function criterionValue(criterion, result) {
  if (!result) return null;
  if (result.answer === "N/A") return null;
  if (criterion.type === "scale") {
    const max = Math.max(...criterion.scale.map(Number));
    return max > 0 && typeof result.answer === "number"
      ? (result.answer / max) * 100
      : null;
  }
  if (criterion.type === "binary") {
    return result.answer === "Да" ? 100 : result.answer === "Нет" ? 0 : null;
  }
  return null;
}

/** A read-only view of one evaluation. New rules never rewrite its snapshot. */
export default function DialogueAnalytics({
  dialog,
  criteria: _currentCriteria,
  onEvidence,
  onOpenAppeal,
}) {
  const rules = dialog.criteriaSnapshot || initialCriteria;
  const results = dialog.results || [];
  const ready = dialog.status !== "pending" && results.length > 0;
  const computed = ready ? scoreEvaluation(rules, results) : { score: null };
  const score = ready && !computed.incomplete ? computed.score : null;
  const hasScore = typeof score === "number" && Number.isFinite(score);
  const rows = rules.map((criterion) => {
    const result = results.find(
      (item) => String(item.criterionId) === String(criterion.id),
    );
    return { criterion, result, value: criterionValue(criterion, result) };
  });
  const flags = rows.filter(
    ({ criterion, result }) =>
      criterion.type === "flag" && result?.answer === "Да",
  );
  const scoredRows = rows.filter(({ criterion }) => criterion.type !== "flag");
  const naCount = scoredRows.filter(
    ({ result }) => result?.answer === "N/A",
  ).length;
  const applicable = scoredRows.filter(
    ({ result, criterion }) =>
      result && result.answer !== "N/A" && criterion.weight > 0,
  ).length;
  const attention = ready
    ? rows
        .filter(
          ({ criterion, result, value }) =>
            (criterion.type === "flag" && result?.answer === "Да") ||
            (criterion.type !== "flag" && value !== null && value < 100),
        )
        .sort(
          (a, b) =>
            Number(b.criterion.type === "flag") -
            Number(a.criterion.type === "flag"),
        )
    : [];
  const scoreLabel = !hasScore
    ? "Ожидает оценки"
    : score >= 85
      ? "Высокое качество"
      : score >= 70
        ? "Есть точки роста"
        : "Требует внимания";
  const ChannelIcon = dialog.channel === "call" ? AudioLines : MessageCircle;
  const scoreText = hasScore
    ? score.toLocaleString("ru-RU", { maximumFractionDigits: 2 })
    : "—";

  return (
    <section
      className="single-analytics"
      aria-label="Аналитика выбранного диалога"
    >
      <div className="sa-overview">
        <article className="sa-score-card">
          <div className="sa-score-copy">
            <span className="sa-eyebrow">РЕЗУЛЬТАТ ДИАЛОГА</span>
            <h2>{scoreLabel}</h2>
            <p>
              {hasScore
                ? "Итог по применимым критериям чек-листа"
                : "Результат появится после оценки сервисом ИИ"}
            </p>
            <span className="sa-checklist">
              <ShieldCheck size={13} />
              Чек-лист v{dialog.checklistVersion || 1}
            </span>
          </div>
          <div
            className="sa-score-ring"
            role="img"
            aria-label={
              hasScore
                ? `Итог ${scoreText} из 100 баллов`
                : "Итоговый балл ещё не рассчитан"
            }
          >
            <svg viewBox="0 0 120 120" aria-hidden="true">
              <circle cx="60" cy="60" r="51" className="sa-ring-track" />
              <circle
                cx="60"
                cy="60"
                r="51"
                className="sa-ring-value"
                strokeDasharray={`${hasScore ? Math.max(0, Math.min(score, 100)) * 3.204 : 0} 320.4`}
              />
            </svg>
            <div>
              <strong className={scoreText.length > 4 ? "sa-small-score" : ""}>
                {scoreText}
              </strong>
              <span>из 100 баллов</span>
            </div>
          </div>
        </article>
        <article className="sa-meta-card">
          <span className="sa-meta-icon">
            <UserRound size={18} />
          </span>
          <span className="sa-meta-label">Оператор</span>
          <strong>{dialog.agent || "Не указан"}</strong>
          <small>Клиент: {dialog.customer || "Не указан"}</small>
        </article>
        <article className="sa-meta-card">
          <span className="sa-meta-icon">
            <ChannelIcon size={18} />
          </span>
          <span className="sa-meta-label">Канал и язык</span>
          <strong>
            {dialog.channel === "call" ? "Звонок" : "Чат"}
            <span className="sa-language">{dialog.language}</span>
          </strong>
          <small>
            {dialog.messages?.length || 0} реплик <span>·</span>{" "}
            {dialog.duration || "Время не указано"}
          </small>
        </article>
        <article
          className={`sa-meta-card ${flags.length ? "sa-critical-card" : ""}`}
        >
          <span className="sa-meta-icon">
            {flags.length ? (
              <ShieldAlert size={18} />
            ) : (
              <ShieldCheck size={18} />
            )}
          </span>
          <span className="sa-meta-label">Грубые ошибки</span>
          <strong>
            {ready
              ? flags.length
                ? "Выявлены"
                : "Не выявлены"
              : "Ожидает оценки"}
          </strong>
          <small>
            {ready
              ? `${applicable} применимых критериев${naCount ? ` · ${naCount} N/A` : ""}`
              : "Без вымышленных результатов"}
          </small>
        </article>
      </div>

      <div className="sa-detail-grid">
        <article className="sa-criteria-panel">
          <header className="sa-panel-heading">
            <div>
              <h2>Профиль качества</h2>
              <p>Критерии только выбранного разговора</p>
            </div>
            <span className="sa-count">{scoredRows.length}</span>
          </header>
          <div className="sa-bars">
            {scoredRows.map(({ criterion, result, value }) => {
              const na = result?.answer === "N/A";
              const answer =
                !ready || !result
                  ? "—"
                  : na
                    ? "N/A"
                    : criterion.type === "scale"
                      ? `${result.answer}/${Math.max(...criterion.scale)}`
                      : result.answer;
              return (
                <div
                  className={`sa-bar-item ${na ? "is-na" : value !== null && value < 100 ? "is-partial" : ""}`}
                  key={criterion.id}
                >
                  <div>
                    <span title={criterion.title}>
                      {criterion.title ===
                      initialCriteria.find((item) => item.id === criterion.id)
                        ?.title
                        ? shortTitles[criterion.id] || criterion.title
                        : criterion.title}
                    </span>
                    <strong>{answer}</strong>
                  </div>
                  <div
                    className="sa-bar-track"
                    role="img"
                    aria-label={`${criterion.title}: ${answer}`}
                  >
                    <span
                      style={{
                        width: `${ready && value !== null ? Math.max(0, Math.min(value, 100)) : 0}%`,
                      }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
          <div className="sa-panel-note">
            <CircleHelp size={13} />
            <span>
              N/A исключается из расчёта. Грубые ошибки отмечаются отдельно.
            </span>
          </div>
        </article>
        <article className="sa-findings-panel">
          <header className="sa-panel-heading">
            <div>
              <h2>Что требует внимания</h2>
              <p>Выводы с опорой на реплики</p>
            </div>
            <span
              className={`sa-count ${attention.length ? "sa-attention-count" : ""}`}
            >
              {ready ? attention.length : "—"}
            </span>
          </header>
          {!ready ? (
            <div className="sa-findings-empty">
              <Clock3 size={29} />
              <h3>Сначала оцените диалог</h3>
              <p>
                Транскрипт доступен ниже. Аналитика появится после подключения
                сервиса оценивания.
              </p>
            </div>
          ) : !attention.length ? (
            <div className="sa-findings-empty">
              <CheckCircle2 size={29} />
              <h3>Отклонений не выявлено</h3>
              <p>
                Применимые критерии выполнены. Подробные обоснования доступны
                рядом с транскриптом.
              </p>
            </div>
          ) : (
            <div className="sa-findings">
              {attention.slice(0, 2).map(({ criterion, result }) => {
                const hasEvidence = dialog.messages?.some(
                  (m) => m.id === result.evidenceId,
                );
                return (
                  <div
                    className={`sa-finding ${criterion.type === "flag" ? "is-critical" : ""}`}
                    key={criterion.id}
                  >
                    <div className="sa-finding-title">
                      <span />
                      {criterion.title}
                    </div>
                    <p>{result.reason}</p>
                    <div className="sa-finding-actions">
                      <button
                        onClick={() => onEvidence?.(result.evidenceId)}
                        disabled={!hasEvidence}
                      >
                        <FileText size={13} />
                        {hasEvidence
                          ? `Реплика #${result.evidenceId}`
                          : "Источник не указан"}
                      </button>
                      {onOpenAppeal && (
                        <button onClick={() => onOpenAppeal(result)}>
                          Оспорить <ArrowUpRight size={13} />
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
              {attention.length > 2 && (
                <p className="sa-more-findings">
                  Ещё {attention.length - 2}{" "}
                  {attention.length - 2 === 1 ? "замечание" : "замечания"} — в
                  подробной оценке ниже.
                </p>
              )}
            </div>
          )}
          <div className="sa-origin">
            <span />
            Демонстрационный набор · оценка одного диалога
          </div>
        </article>
      </div>
    </section>
  );
}
