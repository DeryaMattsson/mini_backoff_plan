"""Retry schedules with full jitter and a total deadline.

The plan owns two independent limits: a per-attempt delay cap and a wall-clock
budget. Both are consulted before every sleep, so a schedule can never hand out
a delay that outlives the deadline. Time is injected as a ``clock`` callable so
that callers (and the test suite) can drive the plan without sleeping.
"""

from __future__ import annotations

import random
from typing import Callable, Iterator, Optional


class PlanExhausted(Exception):
    """Raised when the plan has no delay left to give."""


class BackoffPlan:
    """An iterator of retry delays with full jitter and a total deadline.

    Parameters
    ----------
    base:
        The first un-jittered delay, in seconds. Must be positive.
    factor:
        Multiplier applied to the un-jittered delay after each attempt.
        Must be at least 1.0; values below 1.0 would shrink the schedule.
    cap:
        Upper bound on the un-jittered delay. Must be positive and at least
        ``base``.
    deadline:
        Total wall-clock budget in seconds, measured from the first call to
        ``__next__``. Must be positive. ``None`` disables the deadline.
    max_attempts:
        Maximum number of delays the plan will yield. Must be positive.
    clock:
        Zero-argument callable returning a monotonically increasing float in
        seconds. Defaults to ``time.monotonic``. Injected so tests are
        deterministic.
    rng:
        ``random.Random`` instance used for jitter. Injected so tests are
        deterministic.

    The plan yields the delay to wait *before* the next attempt. Full jitter
    means each yielded delay is drawn uniformly from ``[0, raw_delay]``. The
    raw delay is ``min(cap, base * factor ** attempt)``.

    A delay is only yielded if it fits inside the remaining budget. If the
    budget is already exhausted, or the attempt limit is reached, iteration
    stops. ``PlanExhausted`` is raised by ``next_delay`` when that happens.
    """

    def __init__(
        self,
        base: float,
        *,
        factor: float = 2.0,
        cap: Optional[float] = None,
        deadline: Optional[float] = None,
        max_attempts: int = 8,
        clock: Optional[Callable[[], float]] = None,
        rng: Optional[random.Random] = None,
    ) -> None:
        if base <= 0:
            raise ValueError("base must be positive")
        if factor < 1.0:
            raise ValueError("factor must be >= 1.0")
        if cap is None:
            cap = base
        if cap < base:
            raise ValueError("cap must be >= base")
        if deadline is not None and deadline <= 0:
            raise ValueError("deadline must be positive")
        if max_attempts <= 0:
            raise ValueError("max_attempts must be positive")

        self.base = float(base)
        self.factor = float(factor)
        self.cap = float(cap)
        self.deadline = None if deadline is None else float(deadline)
        self.max_attempts = int(max_attempts)
        self._clock = clock if clock is not None else _monotonic
        self._rng = rng if rng is not None else random.Random()

        self._attempt = 0
        self._started = False
        self._start_time = 0.0

    def __iter__(self) -> "BackoffPlan":
        return self

    def __next__(self) -> float:
        delay = self.next_delay()
        if delay is None:
            raise StopIteration
        return delay

    def next_delay(self) -> Optional[float]:
        """Return the next delay, or ``None`` when the plan is exhausted.

        This is the non-exception form of ``__next__``. It also starts the
        deadline clock on the first call.
        """
        if not self._started:
            self._started = True
            self._start_time = self._clock()

        if self._attempt >= self.max_attempts:
            return None

        if self.deadline is not None:
            elapsed = self._clock() - self._start_time
            remaining = self.deadline - elapsed
            if remaining <= 0:
                return None
        else:
            remaining = None

        raw = self.base * (self.factor ** self._attempt)
        if raw > self.cap:
            raw = self.cap

        delay = self._rng.uniform(0.0, raw)

        # Full jitter can produce a delay longer than the remaining budget.
        # Rather than sleep past the deadline, clamp into the budget. If the
        # budget is effectively zero we stop instead of yielding 0.0, which
        # would be a busy loop for the caller.
        if remaining is not None:
            if delay > remaining:
                delay = remaining
            if delay <= 0.0:
                return None

        self._attempt += 1
        return delay

    @property
    def attempts_made(self) -> int:
        """Number of delays handed out so far."""
        return self._attempt

    def reset(self) -> None:
        """Restart the plan, including the deadline clock."""
        self._attempt = 0
        self._started = False
        self._start_time = 0.0


def _monotonic() -> float:
    import time

    return time.monotonic()
