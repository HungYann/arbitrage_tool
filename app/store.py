from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .strategy import Portfolio, StrategyConfig


class JsonlEventStore:
    def __init__(self, data_dir: str | None = None):
        self.data_dir = Path(data_dir or os.getenv("ARBITRAGE_DATA_DIR", "./data"))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.event_path = self.data_dir / "events.jsonl"

    def append(self, event_type: str, payload: dict[str, Any]) -> None:
        event = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            "payload": payload,
        }
        with self.event_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def tail(self, limit: int = 100) -> list[dict[str, Any]]:
        if not self.event_path.exists():
            return []
        lines = self.event_path.read_text(encoding="utf-8").splitlines()
        events = []
        for line in lines[-limit:]:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                events.append({"type": "corrupt_log_line", "payload": {"line": line}})
        return events


class RuntimeState:
    def __init__(self, config: StrategyConfig):
        self.config = config
        self.portfolio = Portfolio.from_config(config)

    def reset(self) -> None:
        self.portfolio = Portfolio.from_config(self.config)

    def config_dict(self) -> dict[str, Any]:
        return asdict(self.config)

    def portfolio_dict(self) -> dict[str, Any]:
        return asdict(self.portfolio)

