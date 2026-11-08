import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  ArrowUpRight,
  Check,
  ChevronRight,
  ChevronUp,
  ChevronDown,
  X,
  Clock3,
  FileText,
  Headphones,
  History,
  MessageCircle,
  Search,
  ShieldCheck,
} from "lucide-react";
import { initialCriteria, scoreEvaluation } from "./data";
import CallRecording from "./CallRecording";
import { evaluationLabel, needsReview } from "./evaluation-state";

const format = (value) =>
  typeof value === "number"
    ? value.toLocaleString("ru-RU", { maximumFractionDigits: 2 })
    : "—";

function ratio(rule, result) {
  if (!result || result.answer === "N/A" || rule.type === "flag") return null;
  if (rule.type === "scale") {
    const maximum = Math.max(...rule.scale);
    return typeof result.answer === "number" && maximum > 0
      ? result.answer / maximum
      : null;
  }
  return result.answer === "Да" ? 1 : result.answer === "Нет" ? 0 : null;
}

function validResult(rule, result) {
  if (!result) return false;
  if (rule.type === "flag") return ["Да", "Нет"].includes(result.answer);
  if (result.answer === "N/A") return Boolean(rule.naAllowed);
  return rule.type === "scale"
    ? typeof result.answer === "number" && rule.scale.includes(result.answer)
    : ["Да", "Нет"].includes(result.answer);
}

function hasIssue(rule, result) {
  if (!validResult(rule, result)) return false;
  return rule.type === "flag"
    ? result.answer === "Да"
    : ratio(rule, result) !== null && ratio(rule, result) < 1;
}

function displayTime(value) {
  const iso =
    /^\d{4}-\d{2}-\d{2}T(\d{2}:\d{2}:\d{2})(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.exec(
      value || "",
    );
  return iso ? iso[1] : value;
}

function roleName(role, dialog) {
  if (role === "operator") return dialog.agent || "Оператор";
  if (role === "client") return dialog.customer || "Клиент";
  return role === "bot" ? "Бот" : "Система";
}

function MarkedText({ text, query }) {
  const term = query.trim();
  if (!term) return text;
  const lower = text.toLocaleLowerCase();
  const search = term.toLocaleLowerCase();
  const pieces = [];
  let cursor = 0;
  let at = lower.indexOf(search);
  while (at !== -1) {
    pieces.push(text.slice(cursor, at));
    pieces.push(<mark key={at}>{text.slice(at, at + term.length)}</mark>);
    cursor = at + term.length;
    at = lower.indexOf(search, cursor);
  }
  pieces.push(text.slice(cursor));
  return pieces;
}

/** Light desktop analysis grounded in the supplied Freedom presentation. */
export default function ConversationAnalysis({
  dialog,
  dialogs = [],
  onSwitch,
  onAppeal,
  appeals = [],
}) {
  const rules = dialog.criteriaSnapshot || initialCriteria;
  const results = dialog.results || [];
  const messages = dialog.messages || [];
  const reviewed =
    dialog.reviewRevision > 0 ||
    dialog.originalResults?.some((before) => {
      const after = results.find(
        (r) => String(r.criterionId) === String(before.criterionId),
      );
      return (
        after &&
        (after.answer !== before.answer || after.reason !== before.reason)
      );
    }) ||
    (dialog.reviewRevision === undefined &&
      typeof dialog.originalScore === "number");
  const ready = dialog.status !== "pending" && results.length > 0;
  const calculation = ready
    ? scoreEvaluation(rules, results)
    : { score: null, critical: false };
  const scored = typeof calculation.score === "number";
  const rows = rules.map((rule) => ({
    rule,
    result: results.find(
      (result) => String(result.criterionId) === String(rule.id),
    ),
  }));
  const initialRule = () =>
    rows.find(({ rule, result }) => hasIssue(rule, result))?.rule.id ||
    rules[0]?.id;
  const [activeRule, setActiveRule] = useState(initialRule);
  const [highlighted, setHighlighted] = useState(null);
  const [query, setQuery] = useState("");
  const [matchIndex, setMatchIndex] = useState(0);
  const transcript = useRef(null);
  const active =
    rows.find(({ rule }) => String(rule.id) === String(activeRule)) ||
    rows.find(({ rule, result }) => hasIssue(rule, result)) ||
    rows[0];
  const activeRuleId = active?.rule.id;
  const evidence = messages.find(
    (message) => message.id === active?.result?.evidenceId,
  );
  const naCount = rows.filter(({ result }) => result?.answer === "N/A").length;
  const applicable = rows.filter(
    ({ rule, result }) =>
      rule.type !== "flag" &&
      Number(rule.weight) > 0 &&
      result &&
      result.answer !== "N/A",
  );
  const applicableWeight = applicable.reduce(
    (sum, { rule }) => sum + Number(rule.weight),
    0,
  );
  const issueCount = rows.filter(({ rule, result }) =>
    hasIssue(rule, result),
  ).length;
  const missingCount = rows.filter(
    ({ rule, result }) => !validResult(rule, result),
  ).length;
  const flagRows = rows.filter(({ rule }) => rule.type === "flag");
  const criticalFound = flagRows.some(({ result }) => result?.answer === "Да");
  const criticalKnown =
    flagRows.length > 0 &&
    flagRows.every(({ rule, result }) => validResult(rule, result));
  const history = appeals.filter((appeal) => appeal.dialogId === dialog.id);
  const matches = useMemo(
    () =>
      query.trim()
        ? messages.filter((message) =>
            message.text
              .toLocaleLowerCase()
              .includes(query.trim().toLocaleLowerCase()),
          )
        : [],
    [messages, query],
  );

  useEffect(() => {
    setActiveRule(initialRule());
    setHighlighted(null);
    setQuery("");
    if (transcript.current) transcript.current.scrollTop = 0;
  }, [dialog.id]);

  useEffect(() => {
    if (
      activeRuleId !== undefined &&
      String(activeRuleId) !== String(activeRule)
    ) {
      setActiveRule(activeRuleId);
    }
  }, [activeRule, activeRuleId]);

  function showMessage(id, focus = true) {
    if (!messages.some((message) => message.id === id)) return;
    setHighlighted(id);
    requestAnimationFrame(() => {
      const target = document.getElementById(`ca-message-${id}`);
      const container = transcript.current;
      if (target && container) {
        container.scrollTo({
          top:
            container.scrollTop +
            target.getBoundingClientRect().top -
            container.getBoundingClientRect().top -
            (container.clientHeight - target.offsetHeight) / 2,
          behavior: "smooth",
        });
      }
      if (focus) target?.focus({ preventScroll: true });
    });
  }

  useEffect(() => {
    setMatchIndex(0);
    if (matches.length) showMessage(matches[0].id, false);
  }, [matches]);

  function moveMatch(direction) {
    if (!matches.length) return;
    const next = (matchIndex + direction + matches.length) % matches.length;
    setMatchIndex(next);
    showMessage(matches[next].id, false);
  }

  const contribution =
    active && applicableWeight
      ? (ratio(active.rule, active.result) * Number(active.rule.weight) * 100) /
        applicableWeight
      : null;

  const qualitySummary = (
    <div className="ca-quality-summary">
      <div
        className="ca-score-ring"
        role="img"
        aria-label={
          scored
            ? `${needsReview(dialog) ? "Предварительная оценка" : "Итог"} ${format(calculation.score)} из 100 баллов`
            : ready && !calculation.incomplete
              ? "Нет применимых критериев с баллом"
              : "Итоговый балл ещё не рассчитан"
        }
        style={{
          "--score": `${scored ? Math.max(0, Math.min(calculation.score, 100)) : 0}%`,
        }}
      >
        <div>
          <strong>{format(calculation.score)}</strong>
          <span>/100</span>
        </div>
      </div>
      <div className="ca-quality-meta">
        <strong>
          {scored
            ? needsReview(dialog)
              ? "Предварительная оценка диалога"
              : "Итоговая оценка диалога"
            : ready
              ? calculation.incomplete
                ? "Оценка неполная"
                : "Нет применимых критериев с баллом"
              : "Ожидает оценки"}
        </strong>
        <p>
          {ready
            ? `${applicable.length} применимых критериев · ${naCount} N/A`
            : "Баллы появятся после обработки сервисом"}
        </p>
        <span
          className={
            criticalFound
              ? "ca-critical-flag"
              : criticalKnown
                ? "ca-safe-flag"
                : "ca-unknown-flag"
          }
        >
          {ready ? (
            criticalFound ? (
              <>
                <AlertTriangle size={14} />
                Грубая ошибка
              </>
            ) : criticalKnown ? (
              <>
                <ShieldCheck size={14} />
                Грубых ошибок нет
              </>
            ) : (
              <>
                <Clock3 size={14} />
                {flagRows.length
                  ? "Грубая ошибка: нет данных"
                  : "Грубая ошибка: критерий не задан"}
              </>
            )
          ) : (
            <>
              <Clock3 size={14} />
              Диалог не оценён
            </>
          )}
        </span>
        {reviewed && (
          <small>До пересмотра: {format(dialog.originalScore)} / 100</small>
        )}
      </div>
    </div>
  );

  return (
    <section className="ca-analysis" aria-label="Анализ выбранного разговора">
      <header className="ca-heading">
        <div>
          <span className="ca-eyebrow">РАБОЧЕЕ МЕСТО КОНТРОЛЯ КАЧЕСТВА</span>
          <h1>Анализ разговора</h1>
          <p>
            <span>{dialog.id}</span>
            <span>{dialog.topic}</span>
            <span>{dialog.language}</span>
            <span>{dialog.channel === "call" ? "Звонок" : "Чат"}</span>
            <span>{dialog.duration || "Длительность не указана"}</span>
          </p>
        </div>
        {onSwitch && dialogs.length > 0 && (
          <label className="ca-dialog-picker">
            <span>Выбранный диалог</span>
            <select
              aria-label="Выбрать другой диалог"
              value={dialog.id}
              onChange={(event) => onSwitch(event.target.value)}
            >
              {dialogs.map((item) => (
                <option value={item.id} key={item.id}>
                  {item.id} · {item.topic}
                </option>
              ))}
            </select>
          </label>
        )}
      </header>

      {dialog.channel === "call" && (
        <CallRecording
          key={dialog.id}
          audioUrl={dialog.audio_url}
          dialogId={dialog.id}
          imported={["organizer", "import", "ollama", "ai", "mock"].includes(
            dialog.source,
          )}
        />
      )}
      <details className="ca-conversation-track" aria-label="Ход диалога">
        <summary className="ca-track-heading">
          <div>
            <MessageCircle size={16} />
            <strong>Ход диалога</strong>
            <span>{messages.length} реплик</span>
          </div>
          <span className="ca-track-legend">
            <i />
            Клиент
            <i />
            Оператор
          </span>
        </summary>
        <div
          className="ca-message-timeline"
          role="group"
          aria-label="Перейти к реплике"
        >
          {messages.map((message, index) => (
            <button
              key={message.id}
              className={`ca-timeline-message ca-timeline-${message.role} ${highlighted === message.id ? "is-active" : ""}`}
              onClick={() => showMessage(message.id)}
              aria-label={`Реплика ${index + 1}: ${roleName(message.role, dialog)}, ${displayTime(message.time)}`}
              title={`${roleName(message.role, dialog)} · ${displayTime(message.time)}`}
            >
              <span>{String(index + 1).padStart(2, "0")}</span>
              <small title={message.time}>{displayTime(message.time)}</small>
            </button>
          ))}
        </div>
        <div className="ca-track-note">
          Последовательность реальных реплик · нажмите на фрагмент, чтобы
          перейти к тексту
          {dialog.channel === "call" && !dialog.audio_url && (
            <span>Запись не приложена к демо</span>
          )}
        </div>
      </details>

      <div className="ca-workspace">
        <section
          className="ca-transcript-panel"
          aria-label="Расшифровка разговора"
        >
          <header className="ca-panel-heading">
            <h2>Расшифровка</h2>
            <span>{messages.length} реплик</span>
          </header>
          <div className="ca-transcript-search">
            <Search size={15} />
            <input
              aria-label="Поиск по переписке"
              placeholder="Найти в разговоре"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  moveMatch(event.shiftKey ? -1 : 1);
                }
              }}
            />
            {query.trim() && (
              <div className="ca-search-controls">
                <span role="status">
                  {matches.length
                    ? `${matchIndex + 1} / ${matches.length}`
                    : "Не найдено"}
                </span>
                <button
                  disabled={!matches.length}
                  aria-label="Предыдущее совпадение"
                  onClick={() => moveMatch(-1)}
                >
                  <ChevronUp size={14} />
                </button>
                <button
                  disabled={!matches.length}
                  aria-label="Следующее совпадение"
                  onClick={() => moveMatch(1)}
                >
                  <ChevronDown size={14} />
                </button>
                <button
                  aria-label="Очистить поиск по переписке"
                  onClick={() => setQuery("")}
                >
                  <X size={13} />
                </button>
              </div>
            )}
          </div>
          <div className="ca-transcript-scroll" ref={transcript}>
            {messages.map((message) => (
              <article
                key={message.id}
                id={`ca-message-${message.id}`}
                tabIndex={-1}
                className={`ca-message message ca-message-${message.role} ${highlighted === message.id ? "highlighted" : ""}`}
              >
                <div className="ca-message-meta">
                  <time dateTime={message.time} title={message.time}>
                    {displayTime(message.time)}
                  </time>
                  <strong>{roleName(message.role, dialog)}</strong>
                  <small>#{message.id}</small>
                </div>
                <p>
                  <MarkedText text={message.text} query={query} />
                </p>
              </article>
            ))}
          </div>
          <footer className="ca-transcript-footer">
            <FileText size={13} />
            Исходные реплики и метки времени сохранены
          </footer>
        </section>

        <section
          className="ca-quality-panel"
          aria-label="Оценка качества разговора"
        >
          <header className="ca-panel-heading">
            <h2>Оценка качества</h2>
            <span>Чек-лист v{dialog.checklistVersion || 1}</span>
          </header>
          {ready && needsReview(dialog) && (
            <div className="ca-applicability-note" role="status">
              Предварительная оценка · нужна проверка специалистом. В отдельных
              критериях есть неопределённость или неполный контекст.
            </div>
          )}
          {!ready ? (
            <>
              {qualitySummary}
              <div className="ca-pending">
                <Clock3 size={25} />
                <h3>Диалог ожидает оценки</h3>
                <p>
                  Транскрипт доступен. Для анализа требуется подключение сервиса
                  оценивания.
                </p>
              </div>
            </>
          ) : (
            <>
              {missingCount > 0 && (
                <p className="ca-incomplete" role="status">
                  Нет результатов: {missingCount} из {rules.length}. Итог не
                  рассчитан.
                </p>
              )}
              <div className="ca-quality-overview">
                {qualitySummary}
                <div
                  className="ca-criterion-list criteria-results"
                  role="group"
                  aria-label="Результаты критериев"
                >
                  {rows.map(({ rule, result }) => {
                    const issue = hasIssue(rule, result);
                    const na = result?.answer === "N/A";
                    const unknown = !validResult(rule, result);
                    const answer = unknown
                      ? "Не оценён"
                      : typeof result.answer === "number"
                        ? `${result.answer} / ${Math.max(...rule.scale)}`
                        : result.answer;
                    return (
                      <button
                        key={rule.id}
                        className={`ca-criterion-row ${String(activeRuleId) === String(rule.id) ? "is-selected" : ""} ${issue ? "has-issue" : ""} ${na ? "is-na" : ""} ${unknown ? "is-unknown" : ""}`}
                        aria-label={`Критерий: ${rule.title}`}
                        aria-describedby={`ca-answer-${rule.id}`}
                        aria-pressed={String(activeRuleId) === String(rule.id)}
                        onClick={() => {
                          setActiveRule(rule.id);
                          if (result?.evidenceId)
                            showMessage(result.evidenceId, false);
                        }}
                      >
                        <span className="ca-result-symbol">
                          {unknown ? (
                            "—"
                          ) : issue ? (
                            <AlertTriangle size={13} />
                          ) : na ? (
                            "—"
                          ) : (
                            <Check size={14} />
                          )}
                        </span>
                        <span className="ca-criterion-title">{rule.title}</span>
                        <small>
                          {rule.type === "flag" ? "Флаг" : `Вес ${rule.weight}`}
                        </small>
                        <strong id={`ca-answer-${rule.id}`}>{answer}</strong>
                        <ChevronRight size={13} />
                      </button>
                    );
                  })}
                </div>
              </div>
              {active && (
                <div className="ca-explanation" aria-live="polite">
                  <span className="ca-explanation-eyebrow">
                    ПОЧЕМУ ТАКАЯ ОЦЕНКА
                  </span>
                  <h3>{active.rule.title}</h3>
                  <p>
                    {active.result?.reason ||
                      "Результат по этому критерию ещё не получен. Он не засчитывается как успешный."}
                  </p>
                  {active.result?.answer === "N/A" && (
                    <div className="ca-applicability-note">
                      N/A: {active.rule.naCondition || active.result.reason}
                    </div>
                  )}
                  {active.result?.evidenceBasis === "absence" && (
                    <div className="ca-applicability-note">
                      Действие не найдено в проверенном диалоге. Одной
                      подтверждающей цитаты нет.
                      {active.result.checkedMessageIds?.length
                        ? ` Проверено реплик: ${active.result.checkedMessageIds.length}.`
                        : ""}
                    </div>
                  )}
                  {active.result?.reviewRecommended && (
                    <div className="ca-applicability-note">
                      Требуется ручная проверка
                      {active.result.reviewReason
                        ? `: ${active.result.reviewReason}`
                        : "."}
                    </div>
                  )}
                  {scored &&
                    ratio(active.rule, active.result) !== null &&
                    applicableWeight > 0 && (
                      <div className="ca-contribution">
                        Вклад в итог с учётом N/A{" "}
                        <strong>{format(contribution)} балла</strong>
                      </div>
                    )}
                  {evidence && (
                    <blockquote>
                      <span>
                        {roleName(evidence.role, dialog)} ·{" "}
                        {displayTime(evidence.time)}
                      </span>
                      <p>{evidence.text}</p>
                      <button onClick={() => showMessage(evidence.id)}>
                        Реплика #{evidence.id}
                        <ArrowUpRight size={12} />
                      </button>
                    </blockquote>
                  )}
                  <div className="ca-explanation-actions">
                    <button
                      className="ca-evidence-button"
                      disabled={!evidence}
                      onClick={() => evidence && showMessage(evidence.id)}
                    >
                      Показать реплику
                      <ArrowRight size={14} />
                    </button>
                    {active.result && onAppeal && (
                      <button
                        className="ca-appeal-button"
                        onClick={() => onAppeal(active.result)}
                      >
                        Оспорить оценку
                        <ArrowUpRight size={13} />
                      </button>
                    )}
                  </div>
                </div>
              )}
            </>
          )}
          {history.length > 0 && (
            <details className="ca-review-history">
              <summary>
                <History size={14} />
                История пересмотра ({history.length})
              </summary>
              {history.map((appeal) => (
                <article key={appeal.id}>
                  <strong>{appeal.title}</strong>
                  <span>
                    {appeal.date} ·{" "}
                    {appeal.status === "resolved"
                      ? "Рассмотрена"
                      : "На рассмотрении"}
                  </span>
                  <p>{appeal.comment}</p>
                  {appeal.status === "resolved" && (
                    <p>
                      Решение: {appeal.newAnswer} · {appeal.decision}
                    </p>
                  )}
                </article>
              ))}
            </details>
          )}
          <footer className="ca-quality-footer">
            {!ready ? "Оценка ещё не выполнена" : evaluationLabel(dialog)} ·{" "}
            {ready
              ? missingCount
                ? "Неполный результат"
                : `Замечания: ${issueCount}`
              : "Без готовой оценки"}{" "}
            · N/A исключается из расчёта
          </footer>
        </section>
      </div>
    </section>
  );
}
