import React, { useEffect, useRef, useState } from "react";

const serialize = (value) =>
  JSON.stringify(value, (_key, item) =>
    item && typeof item === "object" && !Array.isArray(item)
      ? Object.fromEntries(
          Object.keys(item)
            .sort()
            .map((key) => [key, item[key]]),
        )
      : item,
  );

// One shared workspace; local edits and server revisions must never be overwritten silently.
export default function WorkspaceSync({ data, restore }) {
  const revision = useRef(0);
  const ready = useRef(false);
  const latest = useRef(data);
  const restoreRef = useRef(restore);
  const pendingRestore = useRef(null);
  const lastSaved = useRef("");
  const [status, setStatus] = useState("Подключение хранилища…");
  const [retry, setRetry] = useState(0);
  const [canRetry, setCanRetry] = useState(false);
  latest.current = data;
  restoreRef.current = restore;

  useEffect(() => {
    if (
      pendingRestore.current !== null &&
      serialize(data) === pendingRestore.current
    ) {
      pendingRestore.current = null;
      ready.current = true;
      setStatus("Рабочее пространство восстановлено с сервера");
    }
  }, [data]);

  useEffect(() => {
    let active = true;
    ready.current = false;
    const baseline = serialize(latest.current);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    setCanRetry(false);
    setStatus("Подключение хранилища…");
    fetch("/api/workspace", { signal: controller.signal })
      .then(async (r) => {
        if (!r.ok) throw Error("Серверное хранилище недоступно");
        return r.json();
      })
      .then((w) => {
        if (!active) return;
        if (!Number.isInteger(w.revision) || w.revision < 0)
          throw Error("Некорректная версия серверного хранилища");
        revision.current = w.revision;
        const current = serialize(latest.current);
        if (w.data) {
          if (
            !Array.isArray(w.data.dialogs) ||
            !Array.isArray(w.data.criteria) ||
            !Array.isArray(w.data.appeals) ||
            !Number.isInteger(w.data.version)
          )
            throw Error("Сервер вернул некорректное рабочее пространство");
          const saved = serialize(w.data);
          if ((current !== baseline || retry > 0) && current !== saved) {
            setStatus(
              "Данные изменены во время подключения. Локальные правки сохранены в браузере: экспортируйте их перед обновлением страницы.",
            );
            return;
          }
          lastSaved.current = saved;
          if (current !== saved) {
            // Do not PUT the old render before React has applied the restored state.
            pendingRestore.current = saved;
            restoreRef.current(w.data);
            return;
          }
        }
        ready.current = true;
        setStatus("Серверное хранилище подключено");
      })
      .catch(() => {
        if (!active) return;
        let localAvailable = false;
        try {
          localStorage.setItem("freedom-cqa-storage-probe", "1");
          localStorage.removeItem("freedom-cqa-storage-probe");
          localAvailable = true;
        } catch {
          /* Browser storage may be blocked or full. */
        }
        setStatus(
          localAvailable
            ? "Сервер недоступен · изменения сохраняются в этом браузере"
            : "Хранилище недоступно · экспортируйте изменения перед закрытием страницы",
        );
        setCanRetry(true);
      })
      .finally(() => clearTimeout(timeout));
    return () => {
      active = false;
      clearTimeout(timeout);
      controller.abort();
    };
  }, [retry]);

  useEffect(() => {
    let active = true;
    let saving = false;
    let controller;
    const timer = setInterval(async () => {
      const snapshot = latest.current;
      const body = serialize(snapshot);
      if (!ready.current || saving || body === lastSaved.current) return;
      saving = true;
      controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 15000);
      setStatus("Сохранение изменений…");
      try {
        const r = await fetch("/api/workspace", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          signal: controller.signal,
          body: JSON.stringify({ revision: revision.current, data: snapshot }),
        });
        const result = await r.json();
        if (!r.ok) {
          if (r.status === 409) ready.current = false;
          throw Error(
            result.detail || "Ошибка сохранения · экспортируйте результат",
          );
        }
        if (
          !Number.isInteger(result.revision) ||
          result.revision <= revision.current
        )
          throw Error(
            "Сервер не подтвердил сохранение · экспортируйте результат",
          );
        revision.current = result.revision;
        lastSaved.current = body;
        if (active)
          setStatus(
            body === serialize(latest.current)
              ? "Изменения сохранены на сервере"
              : "Есть новые несохранённые изменения…",
          );
      } catch (e) {
        if (active)
          setStatus(
            e.name === "AbortError"
              ? "Сервер не подтвердил сохранение · копия остаётся в браузере"
              : e.message,
          );
      } finally {
        clearTimeout(timeout);
        saving = false;
      }
    }, 1500);
    return () => {
      active = false;
      clearInterval(timer);
      controller?.abort();
    };
  }, []);
  return (
    <div className="sync-status" role="status">
      {status}
      {canRetry && (
        <>
          {" "}
          <button type="button" onClick={() => setRetry((n) => n + 1)}>
            Подключить снова
          </button>
        </>
      )}
    </div>
  );
}
