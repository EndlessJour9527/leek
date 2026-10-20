"""H002 close-total-return channel, independently implemented from its protocol.

Inspired by the 20/10 horizons of vn.py TurtleSignalStrategy (MIT). This is NOT
that intrabar, ATR-scaled, pyramiding, long/short strategy. Only past closes feed
these thresholds; execution and sizing belong to the existing shared ledger.
"""
from collections import deque
from fractions import Fraction

from .contract import DataBlocked

MODEL_ID = 'h002_channel_20_10'
ENTRY_WINDOW = 20
EXIT_WINDOW = 10


class CloseChannel2010:
    """Fixed, long-only regime; equals retain state; warmup stays OFF."""

    def __init__(self):
        self.history = deque(maxlen=ENTRY_WINDOW)
        self.state = False

    def update(self, current: Fraction) -> bool:
        if not isinstance(current, Fraction) or current <= 0:
            raise DataBlocked('H002 requires a positive exact total-return level')
        # The current close is appended only AFTER thresholds are evaluated.
        if len(self.history) == ENTRY_WINDOW:
            if self.state:
                if current < min(list(self.history)[-EXIT_WINDOW:]):
                    self.state = False
            elif current > max(self.history):
                self.state = True
        self.history.append(current)
        return self.state
