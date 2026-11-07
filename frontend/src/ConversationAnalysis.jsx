import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  ArrowUpRight,
  Check,
  ChevronRight,
  Clock3,
  FileText,
  Headphones,
  History,
  MessageCircle,
  Search,
  ShieldCheck,
} from "lucide-react";
import { initialCriteria, scoreEvaluation } from "./data";

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

function hasIssue(rule, result) {
  if (!result) return false;
  return rule.type === "flag"
    ? result.answer === "Да"
    : ratio(rule, result) !== null && ratio(rule, result) < 1;
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
  const transcript = useRef(null);
  const active = rows.find(
    ({ rule }) => String(rule.id) === String(activeRule),
  );
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

  function showMessage(id) {
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
      target?.focus({ preventScroll: true });
    });
  }

  useEffect(() => {
    if (matches.length) showMessage(matches[0].id);
  }, [matches]);

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
            ? `Итог ${format(calculation.score)} из 100 баллов`
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
        <strong>{scored ? "Итоговая оценка диалога" : "Ожидает оценки"}</strong>
        <p>
          {ready
            ? `${applicable.length} применимых критериев · ${naCount} N/A`
            : "Баллы появятся после обработки сервисом"}
        </p>
        <span
          className={calculation.critical ? "ca-critical-flag" : "ca-safe-flag"}
        >
          {ready ? (
            calculation.critical ? (
              <>
                <AlertTriangle size={14} />
                Грубая ошибка
              </>
            ) : (
              <>
                <ShieldCheck size={14} />
                Грубых ошибок нет
              </>
            )
          ) : (
            <>
              <Clock3 size={14} />
              Диалог не оценён
            </>
          )}
        </span>
        {dialog.originalScore !== undefined && (
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

      <section className="ca-conversation-track" aria-label="Ход диалога">
        <div className="ca-track-heading">
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
        </div>
        {dialog.channel === "call" && dialog.audio_url && (
          <div className="ca-audio-player">
            <Headphones size={17} />
            <audio
              controls
              preload="none"
              src={dialog.audio_url}
              aria-label="Запись разговора"
            />
          </div>
        )}
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
              aria-label={`Реплика ${index + 1}: ${roleName(message.role, dialog)}, ${message.time}`}
              title={`${roleName(message.role, dialog)} · ${message.time}`}
            >
              <span>{String(index + 1).padStart(2, "0")}</span>
              <small>{message.time}</small>
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
      </section>

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
            />
            {query.trim() && <span>{matches.length} совпадений</span>}
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
                  <time>{message.time}</time>
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
                    const answer = !result
                      ? "Не оценён"
                      : typeof result.answer === "number"
                        ? `${result.answer} / ${Math.max(...rule.scale)}`
                        : result.answer;
                    return (
                      <button
                        key={rule.id}
                        className={`ca-criterion-row ${String(activeRule) === String(rule.id) ? "is-selected" : ""} ${issue ? "has-issue" : ""} ${na ? "is-na" : ""}`}
                        aria-label={`Критерий: ${rule.title}`}
                        aria-pressed={String(activeRule) === String(rule.id)}
                        onClick={() => setActiveRule(rule.id)}
                      >
                        <span className="ca-result-symbol">
                          {issue ? (
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
                        <strong>{answer}</strong>
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
                  <p>{active.result?.reason || "Обоснование не указано."}</p>
                  {active.result?.answer === "N/A" && (
                    <div className="ca-applicability-note">
                      N/A: {active.rule.naCondition || active.result.reason}
                    </div>
                  )}
                  {ratio(active.rule, active.result) !== null &&
                    applicableWeight > 0 && (
                      <div className="ca-contribution">
                        Вклад в итог с учётом N/A{" "}
                        <strong>{format(contribution)} балла</strong>
                      </div>
                    )}
                  {evidence && (
                    <blockquote>
                      <span>
                        {roleName(evidence.role, dialog)} · {evidence.time}
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
            {dialog.source === "ollama" ? "AI-оценка" : "Демо-оценка"} ·{" "}
            {ready ? `${issueCount} замечания` : "без вымышленных результатов"}{" "}
            · N/A исключается из расчёта
          </footer>
        </section>
      </div>
    </section>
  );
}
