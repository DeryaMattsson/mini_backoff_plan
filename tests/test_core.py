import random
import unittest

from mini_backoff_plan import BackoffPlan, PlanExhausted


class FakeClock:
    """A deterministic monotonic clock the test can advance by hand."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class TestConstruction(unittest.TestCase):
    def test_rejects_non_positive_base(self) -> None:
        with self.assertRaises(ValueError):
            BackoffPlan(0)
        with self.assertRaises(ValueError):
            BackoffPlan(-1)

    def test_rejects_factor_below_one(self) -> None:
        with self.assertRaises(ValueError):
            BackoffPlan(1.0, factor=0.5)

    def test_rejects_cap_below_base(self) -> None:
        with self.assertRaises(ValueError):
            BackoffPlan(2.0, cap=1.0)

    def test_rejects_non_positive_deadline(self) -> None:
        with self.assertRaises(ValueError):
            BackoffPlan(1.0, deadline=0)

    def test_rejects_non_positive_max_attempts(self) -> None:
        with self.assertRaises(ValueError):
            BackoffPlan(1.0, max_attempts=0)

    def test_cap_defaults_to_base(self) -> None:
        plan = BackoffPlan(1.5)
        self.assertEqual(plan.cap, 1.5)


class TestDelays(unittest.TestCase):
    def test_delays_are_bounded_by_raw_schedule(self) -> None:
        rng = random.Random(1234)
        plan = BackoffPlan(1.0, factor=2.0, cap=8.0, max_attempts=5, rng=rng)
        bounds = [1.0, 2.0, 4.0, 8.0, 8.0]
        for bound in bounds:
            delay = plan.next_delay()
            self.assertIsNotNone(delay)
            self.assertGreaterEqual(delay, 0.0)
            self.assertLessEqual(delay, bound)

    def test_stops_after_max_attempts(self) -> None:
        rng = random.Random(7)
        plan = BackoffPlan(0.1, max_attempts=3, rng=rng)
        self.assertIsNotNone(plan.next_delay())
        self.assertIsNotNone(plan.next_delay())
        self.assertIsNotNone(plan.next_delay())
        self.assertIsNone(plan.next_delay())
        self.assertEqual(plan.attempts_made, 3)

    def test_iteration_raises_stop_iteration(self) -> None:
        rng = random.Random(7)
        plan = BackoffPlan(0.1, max_attempts=1, rng=rng)
        collected = list(plan)
        self.assertEqual(len(collected), 1)

    def test_plan_exhausted_is_exported(self) -> None:
        # The exception exists for callers that prefer it over None checks.
        self.assertTrue(issubclass(PlanExhausted, Exception))

    def test_reset_restarts_schedule(self) -> None:
        rng = random.Random(99)
        plan = BackoffPlan(0.5, max_attempts=2, rng=rng)
        self.assertIsNotNone(plan.next_delay())
        self.assertIsNotNone(plan.next_delay())
        self.assertIsNone(plan.next_delay())
        plan.reset()
        self.assertEqual(plan.attempts_made, 0)
        self.assertIsNotNone(plan.next_delay())


class TestDeadline(unittest.TestCase):
    def test_deadline_starts_on_first_call(self) -> None:
        clock = FakeClock()
        rng = random.Random(5)
        plan = BackoffPlan(1.0, deadline=10.0, max_attempts=100, clock=clock, rng=rng)
        # Advancing before the first call must not consume budget.
        clock.advance(100.0)
        self.assertIsNotNone(plan.next_delay())

    def test_deadline_exhausted_returns_none(self) -> None:
        clock = FakeClock()
        rng = random.Random(5)
        plan = BackoffPlan(1.0, deadline=1.0, max_attempts=100, clock=clock, rng=rng)
        self.assertIsNotNone(plan.next_delay())
        clock.advance(2.0)
        self.assertIsNone(plan.next_delay())

    def test_delay_is_clamped_into_remaining_budget(self) -> None:
        clock = FakeClock()
        rng = random.Random(5)
        plan = BackoffPlan(10.0, deadline=3.0, max_attempts=100, clock=clock, rng=rng)
        delay = plan.next_delay()
        self.assertIsNotNone(delay)
        # The raw delay is 10.0 but only 3.0 seconds of budget exist.
        self.assertLessEqual(delay, 3.0)
        self.assertGreater(delay, 0.0)

    def test_zero_remaining_budget_stops_without_yielding_zero(self) -> None:
        clock = FakeClock()
        rng = random.Random(5)
        plan = BackoffPlan(1.0, deadline=1.0, max_attempts=100, clock=clock, rng=rng)
        self.assertIsNotNone(plan.next_delay())
        clock.advance(1.0)
        self.assertIsNone(plan.next_delay())

    def test_no_deadline_allows_full_schedule(self) -> None:
        rng = random.Random(5)
        plan = BackoffPlan(1.0, max_attempts=4, rng=rng)
        delays = [plan.next_delay() for _ in range(4)]
        self.assertTrue(all(d is not None for d in delays))
        self.assertIsNone(plan.next_delay())


if __name__ == "__main__":
    unittest.main()
