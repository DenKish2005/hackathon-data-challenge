import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  ArrowUpRight,
  AudioLines,
  Check,
  ChevronDown,
  ChevronRight,
  Clock,
  ExternalLink,
  FileText,
  History,
  MessageCircle,
  Search,
  ShieldCheck,
  X,
} from "lucide-react";
import { initialCriteria, scoreEvaluation } from "./data";

const number = (value) =>
  value.toLocaleString("ru-RU", { maximumFractionDigits: 2 });

function resultRatio(criterion, result) {
  if (!result || result.answer === "N/A" || criterion.type === "flag")
    return null;
  if (criterion.type === "scale") {
    const max = Math.max(...criterion.scale);
    return typeof result.answer === "number" && max > 0
      ? result.answer / max
      : null;
  }
  return result.answer === "Да" ? 1 : result.answer === "Нет" ? 0 : null;
}

function isIssue(criterion, result) {
  if (!result) return false;
  return criterion.type === "flag"
    ? result.answer === "Да"
    : resultRatio(criterion, result) !== null &&
        resultRatio(criterion, result) < 1;
}

function MarkedText({ text, query }) {
  if (!query) return text;
  const lower = text.toLocaleLowerCase();
  const term = query.toLocaleLowerCase();
  const chunks = [];
  let cursor = 0;
  let at = lower.indexOf(term);
  while (at !== -1) {
    chunks.push(text.slice(cursor, at));
    chunks.push(<mark key={at}>{text.slice(at, at + query.length)}</mark>);
    cursor = at + query.length;
    at = lower.indexOf(term, cursor);
  }
  chunks.push(text.slice(cursor));
  return chunks;
}

/** Review a single immutable evaluation beside its source transcript. */
export default function ReviewWorkspace({ dialog, onAppeal, appeals = [] }) {
  const criteria = dialog.criteriaSnapshot || initialCriteria;
  const results = dialog.results || [];
  const ready = dialog.status !== "pending" && results.length > 0;
  const calculated = ready
    ? scoreEvaluation(criteria, results)
    : { score: null };
  const rows = criteria.map((criterion) => ({
    criterion,
    result: results.find((r) => String(r.criterionId) === String(criterion.id)),
  }));
  const firstExpanded = () =>
    rows.find(({ criterion, result }) => isIssue(criterion, result))?.criterion
      .id || criteria[0]?.id;
  const [expanded, setExpanded] = useState(firstExpanded);
  const [filter, setFilter] = useState(() =>
    rows.some(({ criterion, result }) => isIssue(criterion, result))
      ? "issues"
      : "all",
  );
  const [query, setQuery] = useState("");
  const [matchIndex, setMatchIndex] = useState(0);
  const [highlighted, setHighlighted] = useState(null);
  const [mobilePane, setMobilePane] = useState("evaluation");
  const [showHistory, setShowHistory] = useState(false);
  const transcript = useRef(null);
  const messages = dialog.messages || [];
  const term = query.trim();
  const matches = useMemo(
    () =>
      term
        ? messages.filter((m) =>
            m.text.toLocaleLowerCase().includes(term.toLocaleLowerCase()),
          )
        : [],
    [messages, term],
  );

  useEffect(() => {
    setExpanded(firstExpanded());
    setFilter(
      rows.some(({ criterion, result }) => isIssue(criterion, result))
        ? "issues"
        : "all",
    );
    setQuery("");
    setMatchIndex(0);
    setHighlighted(null);
    setMobilePane("evaluation");
    setShowHistory(false);
    if (transcript.current) transcript.current.scrollTop = 0;
  }, [dialog.id]);

  useEffect(() => {
    if (!highlighted) return;
    const frame = requestAnimationFrame(() => {
      const el = document.getElementById(`msg-${highlighted}`);
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
      el?.focus({ preventScroll: true });
    });
    return () => cancelAnimationFrame(frame);
  }, [highlighted, mobilePane]);

  useEffect(() => {
    setMatchIndex(0);
    if (term && matches.length) setHighlighted(matches[0].id);
  }, [term, matches]);

  const issueCount = rows.filter(({ criterion, result }) =>
    isIssue(criterion, result),
  ).length;
  const naCount = rows.filter(({ result }) => result?.answer === "N/A").length;
  const applicable = rows.filter(
    ({ criterion, result }) =>
      criterion.type !== "flag" &&
      result &&
      result.answer !== "N/A" &&
      Number(criterion.weight) > 0,
  );
  const applicableWeight = applicable.reduce(
    (sum, { criterion }) => sum + Number(criterion.weight),
    0,
  );
  const critical = rows.some(
    ({ criterion, result }) =>
      criterion.type === "flag" && result?.answer === "Да",
  );
  const history = appeals.filter((appeal) => appeal.dialogId === dialog.id);
  const visibleRows = rows.filter(({ criterion, result }) =>
    filter === "issues"
      ? isIssue(criterion, result)
      : filter === "na"
        ? result?.answer === "N/A"
        : true,
  );
  const hasScore =
    typeof calculated.score === "number" && Number.isFinite(calculated.score);

  function showEvidence(id) {
    if (!messages.some((m) => m.id === id)) return;
    setHighlighted(id);
    setMobilePane("transcript");
    // A repeated click must still return the reader to the same source message.
    requestAnimationFrame(() =>
      document
        .getElementById(`msg-${id}`)
        ?.scrollIntoView({ behavior: "smooth", block: "center" }),
    );
  }

  function moveSearch(direction) {
    if (!matches.length) return;
    const next = (matchIndex + direction + matches.length) % matches.length;
    setMatchIndex(next);
    showEvidence(matches[next].id);
  }

  function chooseFilter(value) {
    setFilter(value);
    const next = rows.find(({ criterion, result }) =>
      value === "issues"
        ? isIssue(criterion, result)
        : value === "na"
          ? result?.answer === "N/A"
          : true,
    );
    setExpanded(next?.criterion.id || null);
  }

  return (
    <section
      className="rw-workspace"
      data-mobile-tab={mobilePane}
      aria-label="Проверка выбранного диалога"
    >
      <div className="rw-score-strip">
        <div
          className="rw-overall-score"
          role="img"
          aria-label={
            hasScore
              ? `Итог ${number(calculated.score)} из 100 баллов`
              : "Итоговый балл ещё не рассчитан"
          }
        >
          <strong>{hasScore ? number(calculated.score) : "—"}</strong>
          <span>
            / 100<small>Итоговая оценка</small>
          </span>
        </div>
        <div className="rw-score-meta">
          <span>Оператор</span>
          <strong>{dialog.agent || "Не указан"}</strong>
        </div>
        <div className="rw-score-meta">
          <span>Чек-лист</span>
          <strong>Версия {dialog.checklistVersion || 1}</strong>
        </div>
        <div className="rw-score-meta">
          <span>Применимость</span>
          <strong>
            {ready
              ? `${applicable.length} критериев · ${naCount} N/A`
              : "Ожидает оценки"}
          </strong>
        </div>
        <div className={`rw-score-flag ${critical ? "is-critical" : ""}`}>
          {ready ? (
            critical ? (
              <>
                <AlertTriangle size={15} />
                Грубая ошибка
              </>
            ) : (
              <>
                <ShieldCheck size={15} />
                Грубых ошибок нет
              </>
            )
          ) : (
            <>
              <Clock size={15} />
              Не оценён
            </>
          )}
        </div>
      </div>
      {dialog.originalScore !== undefined && (
        <div className="rw-revision-note">
          <History size={14} />
          После пересмотра · исходная оценка {number(dialog.originalScore)} /
          100
        </div>
      )}
      <div
        className="rw-mobile-tabs"
        role="tablist"
        aria-label="Содержимое диалога"
      >
        <button
          role="tab"
          aria-selected={mobilePane === "evaluation"}
          onClick={() => setMobilePane("evaluation")}
        >
          Оценка <span>{criteria.length}</span>
        </button>
        <button
          role="tab"
          aria-selected={mobilePane === "transcript"}
          onClick={() => setMobilePane("transcript")}
        >
          Переписка <span>{messages.length}</span>
        </button>
      </div>
      <div className="rw-layout">
        <section className="rw-transcript" aria-label="Переписка с клиентом">
          <header className="rw-panel-heading">
            <div>
              <MessageCircle size={16} />
              <h2>Транскрипт</h2>
              <span className="rw-count">{messages.length}</span>
            </div>
            <span className="rw-panel-meta">
              {dialog.language} · {dialog.duration}
            </span>
          </header>
          {dialog.channel === "call" && (
            <div className="rw-audio">
              <AudioLines size={17} />
              <span>
                {dialog.audio_url
                  ? "Запись разговора"
                  : "Запись не приложена к демо"}
              </span>
              {dialog.audio_url && (
                <a href={dialog.audio_url} target="_blank" rel="noreferrer">
                  Открыть запись <ExternalLink size={13} />
                </a>
              )}
            </div>
          )}
          <div className="rw-transcript-search">
            <Search size={15} />
            <input
              aria-label="Поиск по переписке"
              placeholder="Найти в переписке"
              value={query}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  moveSearch(event.shiftKey ? -1 : 1);
                }
              }}
              onChange={(event) => {
                setQuery(event.target.value);
                setMatchIndex(0);
              }}
            />
            {term && (
              <>
                <span className="rw-search-count">
                  {matches.length
                    ? `${Math.min(matchIndex + 1, matches.length)} / ${matches.length}`
                    : "Нет совпадений"}
                </span>
                <button
                  className="icon-button"
                  disabled={!matches.length}
                  aria-label="Предыдущее совпадение"
                  onClick={() => moveSearch(-1)}
                >
                  <ArrowUp size={14} />
                </button>
                <button
                  className="icon-button"
                  disabled={!matches.length}
                  aria-label="Следующее совпадение"
                  onClick={() => moveSearch(1)}
                >
                  <ArrowDown size={14} />
                </button>
                <button
                  className="icon-button"
                  aria-label="Очистить поиск по переписке"
                  onClick={() => setQuery("")}
                >
                  <X size={13} />
                </button>
              </>
            )}
          </div>
          <div className="rw-scroll rw-messages" ref={transcript}>
            {messages.map((message) => (
              <article
                id={`msg-${message.id}`}
                key={message.id}
                tabIndex={-1}
                className={`message rw-message ${message.role} ${highlighted === message.id ? "highlighted" : ""}`}
              >
                <div className="rw-message-meta">
                  <span>
                    {message.role === "operator"
                      ? dialog.agent
                      : message.role === "system"
                        ? "Система"
                        : message.role === "bot"
                          ? "Бот"
                          : dialog.customer}
                  </span>
                  <time>{message.time}</time>
                </div>
                <p>
                  <MarkedText text={message.text} query={term} />
                </p>
                <small>#{message.id}</small>
              </article>
            ))}
          </div>
        </section>
        <section className="rw-evaluation" aria-label="Результаты проверки">
          <header className="rw-panel-heading">
            <div>
              <FileText size={16} />
              <h2>Критерии оценки</h2>
            </div>
            <span className="rw-panel-meta">
              Версия {dialog.checklistVersion || 1}
            </span>
          </header>
          <div
            className="rw-criteria-toolbar"
            role="group"
            aria-label="Фильтр критериев"
          >
            <button
              className={filter === "all" ? "active" : ""}
              aria-pressed={filter === "all"}
              onClick={() => chooseFilter("all")}
            >
              Все <span>{criteria.length}</span>
            </button>
            <button
              className={filter === "issues" ? "active" : ""}
              aria-pressed={filter === "issues"}
              onClick={() => chooseFilter("issues")}
            >
              Замечания <span>{ready ? issueCount : 0}</span>
            </button>
            <button
              className={filter === "na" ? "active" : ""}
              aria-pressed={filter === "na"}
              onClick={() => chooseFilter("na")}
            >
              N/A <span>{ready ? naCount : 0}</span>
            </button>
          </div>
          <div className="rw-scroll criteria-results">
            {!ready ? (
              <div className="rw-pending">
                <Clock size={22} />
                <h3>Ожидает оценки</h3>
                <p>
                  Транскрипт сохранён. Оценка и доказательства появятся после
                  обработки сервером.
                </p>
              </div>
            ) : (
              <>
                {visibleRows.map(({ criterion, result }) => {
                  const open = expanded === criterion.id;
                  const issue = isIssue(criterion, result);
                  const na = result?.answer === "N/A";
                  const ratio = resultRatio(criterion, result);
                  const evidence = messages.find(
                    (message) => message.id === result?.evidenceId,
                  );
                  const effectiveWeight =
                    applicableWeight && criterion.type !== "flag" && !na
                      ? (Number(criterion.weight) / applicableWeight) * 100
                      : null;
                  const previous = dialog.originalResults?.find(
                    (item) => String(item.criterionId) === String(criterion.id),
                  );
                  const answer = !result
                    ? "Не оценён"
                    : typeof result.answer === "number"
                      ? `${result.answer}/${Math.max(...criterion.scale)}`
                      : result.answer;
                  return (
                    <article
                      className={`rw-criterion ${open ? "expanded" : ""} ${issue ? "has-issue" : ""}`}
                      key={criterion.id}
                    >
                      <button
                        className="rw-criterion-toggle"
                        aria-expanded={open}
                        aria-controls={`criterion-body-${criterion.id}`}
                        onClick={() => setExpanded(open ? null : criterion.id)}
                      >
                        <span
                          className={`rw-result-icon ${issue ? "issue" : na ? "na" : "pass"}`}
                        >
                          {issue ? (
                            <AlertTriangle size={14} />
                          ) : na ? (
                            "—"
                          ) : (
                            <Check size={14} />
                          )}
                        </span>
                        <span className="rw-criterion-name">
                          {criterion.title}
                          <small>
                            {criterion.type === "flag"
                              ? "Отдельный флаг"
                              : `Вес ${criterion.weight}`}
                          </small>
                        </span>
                        <span
                          className={`rw-answer ${issue ? "issue" : na ? "na" : "pass"}`}
                        >
                          {answer}
                        </span>
                        {open ? (
                          <ChevronDown size={14} />
                        ) : (
                          <ChevronRight size={14} />
                        )}
                      </button>
                      {open && (
                        <div
                          id={`criterion-body-${criterion.id}`}
                          className="rw-criterion-body"
                        >
                          <p className="rw-reason">
                            {result?.reason || "Обоснование отсутствует."}
                          </p>
                          {na && (
                            <div className="rw-na-note">
                              N/A:{" "}
                              {criterion.naCondition ||
                                result?.na_reason ||
                                "Критерий неприменим по текущему чек-листу."}
                            </div>
                          )}
                          {ratio !== null && effectiveWeight !== null && (
                            <div className="rw-points">
                              <span>Вклад в итог с учётом N/A</span>
                              <strong>
                                {number(effectiveWeight * ratio)}{" "}
                                <span>/ {number(effectiveWeight)}</span>
                              </strong>
                            </div>
                          )}
                          {previous && previous.answer !== result?.answer && (
                            <div className="rw-previous-answer">
                              <History size={13} />
                              До пересмотра: {previous.answer}
                            </div>
                          )}
                          {evidence && (
                            <blockquote className="rw-evidence-quote">
                              <span>
                                {evidence.role === "operator"
                                  ? "Оператор"
                                  : evidence.role === "client"
                                    ? "Клиент"
                                    : evidence.role === "system"
                                      ? "Система"
                                      : "Бот"}{" "}
                                · {evidence.time}
                              </span>
                              <p>{evidence.text}</p>
                            </blockquote>
                          )}
                          <div className="rw-criterion-actions">
                            {evidence ? (
                              <button onClick={() => showEvidence(evidence.id)}>
                                <MessageCircle size={13} />
                                Реплика #{evidence.id}
                                <ArrowUpRight size={12} />
                              </button>
                            ) : (
                              <span className="rw-missing-evidence">
                                Ссылка на реплику не указана
                              </span>
                            )}
                            {result && onAppeal && (
                              <button onClick={() => onAppeal(result)}>
                                Оспорить
                                <ArrowUpRight size={12} />
                              </button>
                            )}
                          </div>
                        </div>
                      )}
                    </article>
                  );
                })}
                {!visibleRows.length && (
                  <div className="rw-empty-filter">
                    <Check size={21} />
                    <h3>
                      {filter === "issues"
                        ? "Замечаний нет"
                        : "Неприменимых критериев нет"}
                    </h3>
                    <p>Для просмотра всех результатов выберите «Все».</p>
                  </div>
                )}
              </>
            )}
          </div>
          <footer className="rw-evaluation-footer">
            <span>Демо-оценка · без запуска модели</span>
            <button
              onClick={() => setShowHistory((current) => !current)}
              aria-expanded={showHistory}
            >
              <History size={13} />
              История пересмотра{history.length ? ` (${history.length})` : ""}
            </button>
          </footer>
          {showHistory && (
            <section className="rw-history" aria-label="История пересмотра">
              <h3>История пересмотра</h3>
              {history.length ? (
                history.map((appeal) => (
                  <article key={appeal.id}>
                    <div>
                      <strong>{appeal.title}</strong>
                      <time>{appeal.date}</time>
                    </div>
                    <p>{appeal.comment}</p>
                    {appeal.status === "resolved" ? (
                      <p className="rw-decision">
                        Решение: {appeal.newAnswer} · {appeal.decision}
                      </p>
                    ) : (
                      <span className="rw-history-pending">
                        На рассмотрении
                      </span>
                    )}
                  </article>
                ))
              ) : (
                <p>По этому диалогу апелляций пока нет.</p>
              )}
            </section>
          )}
        </section>
      </div>
    </section>
  );
}
