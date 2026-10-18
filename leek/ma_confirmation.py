"""Causal MA120 confirmation research. Signals only; never places orders.

Input levels must be genuine as-of total-return observations vetted upstream. The
caller supplies the exchange trading calendar and provenance qualification.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo("Asia/Shanghai")
LOOKBACK = 120
H001_CONFIRMATION = 3


class TrendDataBlocked(ValueError):
    """Evidence is insufficient or was not available at decision time."""


@dataclass(frozen=True)
class TrendEvidence:
    model_id: str
    session: str
    asof: str
    available_at: str
    exposure_state: str  # ON | OFF; no account weight implied
    last_level: str
    last_ma: str
    streak_up: int
    streak_down: int
    observations: int
    input_sha256: str


def _decimal(value: object) -> Decimal:
    if not isinstance(value, (str, int, Decimal)) or isinstance(value, bool):
        raise TrendDataBlocked("level must be decimal text or integer")
    try:
        n = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise TrendDataBlocked("invalid total-return level") from exc
    if not n.is_finite() or n <= 0:
        raise TrendDataBlocked("total-return level must be positive and finite")
    return n


def _aware(value: str) -> datetime:
    if not isinstance(value, str):
        raise TrendDataBlocked("timezone-aware timestamp required")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TrendDataBlocked("invalid timestamp") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise TrendDataBlocked("timezone-aware timestamp required")
    return dt


def _session(value: str) -> date:
    if not isinstance(value, str):
        raise TrendDataBlocked("invalid session date")
    try:
        dt = date.fromisoformat(value)
    except ValueError as exc:
        raise TrendDataBlocked("invalid session date") from exc
    if dt.isoformat() != value:
        raise TrendDataBlocked("session must be canonical ISO date")
    return dt


def evaluate_ma_confirmation(
    observations: Sequence[Mapping[str, str]],
    *,
    decision_time: str,
    calendar_sessions: Sequence[str],
    history_qualified: bool = False,
    corporate_actions_qualified: bool = False,
    confirmation: int = H001_CONFIRMATION,
    lookback: int = LOOKBACK,
) -> TrendEvidence:
    """Replay an ON/OFF regime using only observed closed trading sessions.

    Each observation: session, level, available_at. Levels are total-return
    measures (never fill/valuation prices). calendar_sessions must list exactly
    the expected sessions in the provided range; no silent gap filling.
    An ON state neither authorizes a trade nor implies account allocation.
    The baseline uses confirmation=1, with otherwise identical inputs.
    """
    if type(history_qualified) is not bool or not history_qualified:
        raise TrendDataBlocked("point-in-time historical data not qualified")
    if type(corporate_actions_qualified) is not bool or not corporate_actions_qualified:
        raise TrendDataBlocked("total-return corporate actions not qualified")
    if type(confirmation) is not int or not 1 <= confirmation <= 20:
        raise TrendDataBlocked("invalid confirmation count")
    if type(lookback) is not int or lookback < 2:
        raise TrendDataBlocked("invalid lookback")
    now = _aware(decision_time)
    if not isinstance(observations, (list, tuple)) or not isinstance(calendar_sessions, (list, tuple)):
        raise TrendDataBlocked("ordered observations and calendar required")
    if len(observations) != len(calendar_sessions) or len(observations) < lookback:
        raise TrendDataBlocked("history incomplete or warmup insufficient")

    dates: list[str] = []
    values: list[Decimal] = []
    available: list[datetime] = []
    for row, trading_day in zip(observations, calendar_sessions):
        if not isinstance(row, Mapping):
            raise TrendDataBlocked("invalid observation")
        try:
            d = _session(row["session"])
            expected = _session(trading_day)
            n = _decimal(row["level"])
            at = _aware(row["available_at"])
        except KeyError as exc:
            raise TrendDataBlocked("required observation field missing") from exc
        if d != expected or (dates and row["session"] <= dates[-1]):
            raise TrendDataBlocked("calendar mismatch or non-increasing sessions")
        close = datetime.combine(d, time(15, 0), SHANGHAI)
        if at < close or at > now:
            raise TrendDataBlocked("price not available at decision time")
        dates.append(row["session"])
        values.append(n)
        available.append(at)

    final_close = datetime.combine(_session(dates[-1]), time(15, 0), SHANGHAI)
    if final_close > now:
        raise TrendDataBlocked("session not closed at decision time")

    up = down = 0
    state = "OFF"
    rolling = sum(values[:lookback], Decimal(0))
    last_ma = Decimal(0)
    for i in range(lookback - 1, len(values)):
        if i >= lookback:
            rolling += values[i] - values[i - lookback]
        avg = rolling / Decimal(lookback)
        last_ma = avg
        if values[i] > avg:
            up += 1
            down = 0
        elif values[i] < avg:
            down += 1
            up = 0
        else:
            up = down = 0
        if up >= confirmation:
            state = "ON"
        elif down >= confirmation:
            state = "OFF"

    canon = [{"session": d, "level": str(v), "available_at": a.isoformat()}
             for d, v, a in zip(dates, values, available)]
    digest = sha256(json.dumps(canon, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    model_id = "MA120_H001_3D" if lookback == LOOKBACK and confirmation == 3 else f"MA{lookback}_C{confirmation}"
    return TrendEvidence(
        model_id=model_id,
        session=dates[-1],
        asof=final_close.isoformat(),
        available_at=max(available).isoformat(),
        exposure_state=state,
        last_level=str(values[-1]),
        last_ma=str(last_ma),
        streak_up=up,
        streak_down=down,
        observations=len(values),
        input_sha256=digest,
    )
