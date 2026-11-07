"""Conservative reversible UTF-8 repair; raw records remain separately preserved."""

NORMALIZATION_VERSION = "utf8-repair-v1"


def repair_mojibake(text):
    if not any(marker in text for marker in ("Ð", "Ñ", "Â", "â", "Ã")):
        return text
    for encoding in ("latin-1", "cp1252"):
        try:
            candidate = text.encode(encoding).decode("utf-8")
        except UnicodeError:
            continue
        # Demand an improvement in Cyrillic text, without replacement characters.
        # Ambiguous Latin-only strings are deliberately left alone.
        before = sum("\u0400" <= ch <= "\u052f" for ch in text)
        after = sum("\u0400" <= ch <= "\u052f" for ch in candidate)
        if after > before and "\ufffd" not in candidate:
            return candidate
    return text


def normalize_messages(messages):
    normalized = []
    changes = []
    for message in messages:
        text = repair_mojibake(message.text)
        normalized.append(message.model_copy(update={"text": text}))
        if text != message.text:
            changes.append({"messageId": message.id, "originalText": message.text})
    return normalized, changes
