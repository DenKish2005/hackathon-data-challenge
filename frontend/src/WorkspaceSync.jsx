import React, { useEffect, useRef, useState } from "react";

// One shared demonstration workspace; revisions prevent overwriting another browser's edits.
export default function WorkspaceSync({ data, restore }) {
  const revision = useRef(0);
  const ready = useRef(false);
  const latest = useRef(data);
  const lastSaved = useRef("");
  const [status, setStatus] = useState("Подключение хранилища…");
  useEffect(() => {
    let active = true;
    fetch("/api/workspace")
      .then((r) => {
        if (!r.ok) throw Error();
        return r.json();
      })
      .then((w) => {
        if (!active) return;
        revision.current = w.revision;
        if (w.data) {
          restore(w.data);
          lastSaved.current = JSON.stringify(w.data);
        }
        ready.current = true;
        setStatus("Серверное хранилище подключено");
      })
      .catch(() =>
        setStatus("Сервер недоступен · изменения сохраняются в этом браузере"),
      );
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    latest.current = data;
  }, [data]);
  useEffect(() => {
    let active = true;
    let saving = false;
    const timer = setInterval(async () => {
      const body = JSON.stringify(latest.current);
      if (!ready.current || saving || body === lastSaved.current) return;
      saving = true;
      try {
        const r = await fetch("/api/workspace", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            revision: revision.current,
            data: latest.current,
          }),
        });
        const result = await r.json();
        if (!r.ok) {
          if (r.status === 409) ready.current = false;
          throw Error(result.detail);
        }
        revision.current = result.revision;
        lastSaved.current = body;
        if (active) setStatus("Изменения сохранены на сервере");
      } catch (e) {
        if (active)
          setStatus(e.message || "Ошибка сохранения · экспортируйте результат");
      } finally {
        saving = false;
      }
    }, 1500);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);
  return (
    <div className="sync-status" role="status">
      {status}
    </div>
  );
}
