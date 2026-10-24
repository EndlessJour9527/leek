"""H003 independent close-total-return mean-reversion signal.

The Bollinger 20/2 concept is learned from mementum/backtrader
@b853d7c90b6721476eb5a5ea3135224e33db1f14 (GPL-3.0-or-later).
No third-party source is copied or imported. This class emits only regime
intent; only the shared real-history Ledger can simulate order execution.
"""
from collections import deque
from fractions import Fraction

from .contract import DataBlocked

MODEL_ID = 'h003_close_tr_bb20_2'
WINDOW = 20


class MeanReversion20:
    """Long-only OFF/ON, comparison against strictly *previous* 20 TR closes.

    Calculate population variance with exact rational arithmetic; squared
    distance detects two sigma without square roots. The current level must
    be excluded from the band. Returns state, not an executable order.
    """

    def __init__(self):
        self.history = deque(maxlen=WINDOW)
        self.state = False

    def update(self, level: Fraction) -> bool:
        if type(level) is not Fraction or level <= 0:
            raise DataBlocked('H003 requires positive exact Fraction total-return close')
        if len(self.history) == WINDOW:
            mean = sum(self.history, Fraction(0)) / WINDOW
            variance = sum(((x - mean) ** 2 for x in self.history), Fraction(0)) / WINDOW
            if self.state:
                if level >= mean:
                    self.state = False
            elif variance > 0 and level < mean and (mean - level) ** 2 >= 4 * variance:
                self.state = True
        self.history.append(level)
        return self.state
