// Keep infrastructure test responses distinct from actual model assessments.
export function isMockEvaluation(dialog) {
  return dialog?.is_mock === true || dialog?.source === "mock";
}

export function isModelEvaluation(dialog) {
  return (
    !isMockEvaluation(dialog) &&
    (dialog?.is_mock === false || ["ollama", "ai"].includes(dialog?.source))
  );
}

export function evaluationLabel(dialog) {
  if (dialog?.status === "pending") return "Без оценки";
  if (isMockEvaluation(dialog)) return "Тестовый результат · без AI";
  return isModelEvaluation(dialog) ? "AI-анализ" : "Демонстрационный пример";
}

export function needsReview(dialog) {
  return Boolean(
    dialog?.scoreProvisional ||
    dialog?.reviewRecommended ||
    dialog?.results?.some((r) => r.reviewRecommended),
  );
}
