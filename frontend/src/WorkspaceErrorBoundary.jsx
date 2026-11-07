import React from "react";

export default class WorkspaceErrorBoundary extends React.Component {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }

  downloadBackup = () => {
    const data = {};
    for (const key of ["dialogs", "criteria", "version", "appeals"]) {
      try {
        data[key] = localStorage.getItem(`freedom-cqa-${key}`);
      } catch {
        data[key] = null;
      }
    }
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = "freedom-workspace-backup.json";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <section className="workspace-error" role="alert">
        <img src="./freedom-logo.png" alt="Freedom" />
        <span>РАБОЧЕЕ МЕСТО КОНТРОЛЯ КАЧЕСТВА</span>
        <h1>Не удалось открыть рабочее пространство</h1>
        <p>
          Сохранённые данные не удалось отобразить. Скачайте их копию перед
          повторным открытием.
        </p>
        <div>
          <button className="button primary" onClick={this.downloadBackup}>
            Скачать копию данных
          </button>
          <button className="button" onClick={() => window.location.reload()}>
            Обновить страницу
          </button>
        </div>
      </section>
    );
  }
}
