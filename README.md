# mini_backoff_plan

Retry schedules with full jitter and a total deadline, as a single iterable object.

```python
import random
from mini_backoff_plan import BackoffPlan

plan = BackoffPlan(
    base=0.5,
    factor=2.0,
    cap=8.0,
    deadline=30.0,
    max_attempts=10,
    rng=random.Random(0),
)

for delay in plan:
    # delay is a float in seconds, drawn uniformly from [0, raw]
    # and never larger than the remaining deadline budget.
    print("waiting", delay)
```

`BackoffPlan` is iterable and also exposes `next_delay()`, which returns `None`
instead of raising `StopIteration` when the plan is spent. `attempts_made` counts
the delays handed out, and `reset()` restarts the schedule (including the
deadline clock).

## Why this exists

Most backoff helpers give you either a jittered delay or a deadline, not both.
When you combine them naively, a long jittered delay can be handed out after the
deadline has already passed, and the caller sleeps past its budget. This library
makes the deadline a first-class part of the schedule: every yielded delay is
clamped into the remaining budget, and a schedule with no budget left stops
instead of yielding `0.0` (which would be a busy loop).

The trade-off is that the schedule is stateful and single-use unless you call
`reset()`. That is deliberate: the deadline is measured from the first call to
`next_delay()`, not from construction, so a plan can sit in a queue for a while
before it starts consuming its budget. If you want the deadline to start at
construction, call `next_delay()` once and discard the result.

## The awkward edge

Clamping means the last delay in a plan can be shorter than the raw backoff
formula would suggest. If you need the delay to match the formula exactly, this
is not the library for you. For retries, a shorter final wait is almost always
the right behaviour.

## API

- `BackoffPlan(base, *, factor=2.0, cap=None, deadline=None, max_attempts=8, clock=None, rng=None)`
- `BackoffPlan.next_delay() -> float | None`
- `BackoffPlan.attempts_made -> int`
- `BackoffPlan.reset() -> None`
- `PlanExhausted`

`clock` is a zero-argument callable returning a monotonically increasing float;
it defaults to `time.monotonic`. `rng` is a `random.Random` instance. Both are
injected so tests can be deterministic.
