"""Data-only adapter boundary. Importing this module never connects to services."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from .contract import DataBlocked
from .ledger import dec


def timestamp(value: str) -> datetime:
    try:
        if not isinstance(value, str):
            raise ValueError("timestamp must be text")
        # Python 3.10 requires an explicit offset instead of the RFC 3339 Z.
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError('timezone required')
        return parsed
    except (ValueError, TypeError) as exc:
        raise DataBlocked('invalid timezone-aware timestamp') from exc


@dataclass(frozen=True)
class SignalEnvelope:
    instrument: str
    asof: str
    available_at: str
    target_weight: str
    model_id: str
    dataset_hash: str

    def validate(self, decision_time: str) -> Decimal:
        """Validate a long-only paper target; this does not place an order."""
        if any(not isinstance(v, str) or not v for v in (self.instrument, self.model_id)):
            raise DataBlocked('instrument and model_id are required')
        if not isinstance(self.dataset_hash, str) or len(self.dataset_hash) != 64 or any(c not in '0123456789abcdef' for c in self.dataset_hash):
            raise DataBlocked('lowercase SHA-256 dataset hash required')
        if not timestamp(self.asof) <= timestamp(self.available_at) <= timestamp(decision_time):
            raise DataBlocked('signal was unavailable at decision time')
        try:
            weight = dec(self.target_weight)
        except ValueError as exc:
            raise DataBlocked("invalid target weight") from exc
        if not 0 <= weight <= 1:
            raise DataBlocked('long-only target weight must be in [0, 1]')
        return weight


class SignalProvider(Protocol):
    """Optional external research adapters implement this data-only interface."""

    def signal(self, instrument: str, decision_time: str) -> SignalEnvelope:
        ...
