import json
import logging
from datetime import UTC, datetime
from decimal import Decimal

from .models import RunSnapshot

logger = logging.getLogger("tokenops_guard")


def log_event(event: dict):
    """Call with safe structured ledger metadata only; never provider exceptions/prompts."""
    event = {"timestamp": datetime.now(UTC).isoformat(), **event}
    logger.info(json.dumps(event, ensure_ascii=False, separators=(",", ":")))


def console_summary(snapshot: RunSnapshot) -> str:
    def money(value):
        return f"${Decimal(value) / Decimal(1000000):.6f}"

    return (
        f"run={snapshot.run_id} status={snapshot.status}\n"
        f"spent={money(snapshot.spent)} reserved={money(snapshot.reserved)} "
        f"remaining={money(snapshot.remaining)} budget={money(snapshot.budget)}\n"
        f"tokens={snapshot.input_tokens + snapshot.output_tokens}/{snapshot.max_tokens} "
        f"calls={snapshot.calls} steps={snapshot.steps} active={snapshot.active} "
        f"halt_reason={snapshot.halt_reason or '-'}"
    )
