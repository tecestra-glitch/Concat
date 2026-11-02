from __future__ import annotations

import random
from datetime import timedelta

import pytest

from fronteira_fx.watch.scheduler import Scheduler, SchedulerConfig
from tests.watch.conftest import BUSINESS_NOW, NIGHT_NOW, FakeClock


def make(clock: FakeClock, **cfg) -> Scheduler:
    return Scheduler(SchedulerConfig(**cfg), clock=clock, rng=random.Random(42))


def test_new_source_is_due_immediately_and_interval_is_clamped(clock):
    s = make(clock)
    sched = s.add_source("fast", 10)  # below the 60 s floor
    assert sched.interval_s == 60
    slow = s.add_source("slow", 5000)  # above the 900 s ceiling
    assert slow.interval_s == 900
    assert s.due() == ["fast", "slow"]
    assert s.next_wakeup() == clock.now


def test_change_shortens_and_quiet_polls_lengthen(clock):
    s = make(clock, unchanged_polls_before_lengthen=2)
    s.add_source("x", 300)
    s.mark_started("x")
    sched = s.record_result("x", changed=True)
    assert sched.interval_s == 150
    assert sched.next_run_at == clock.now + timedelta(seconds=150)
    assert sched.last_change_at == clock.now
    # two quiet polls -> x1.5
    s.record_result("x", changed=False)
    assert sched.interval_s == 150 and sched.unchanged_in_row == 1
    s.record_result("x", changed=False)
    assert sched.interval_s == 225 and sched.unchanged_in_row == 0
    # never below the floor, never above the ceiling
    for _ in range(10):
        s.record_result("x", changed=True)
    assert sched.interval_s == 60
    for _ in range(30):
        s.record_result("x", changed=False)
    assert sched.interval_s == 900


def test_not_due_before_next_run_and_due_after(clock):
    s = make(clock)
    s.add_source("x", 300)
    s.mark_started("x")
    s.record_result("x", changed=False)
    assert s.due() == []
    clock.advance(299)
    assert s.due() == []
    clock.advance(1)
    assert s.due() == ["x"]


def test_running_source_is_not_dispatched_twice(clock):
    s = make(clock)
    s.add_source("x", 300)
    s.mark_started("x")
    assert s.due() == []
    assert s.next_wakeup() is None
    s.record_result("x", changed=False)
    clock.advance(300)
    assert s.due() == ["x"]


def test_error_backoff_is_exponential_with_jitter_and_capped(clock):
    s = make(clock, jitter=0.1, backoff_cap_s=1800)
    s.add_source("x", 300)
    delays = []
    for _ in range(5):
        s.mark_started("x")
        sched = s.record_result("x", error=True, changed=False)
        delays.append((sched.next_run_at - clock.now).total_seconds())
    assert sched.errors_in_row == 5
    # 600, 1200, then capped at 1800 (all ±10 %)
    assert 540 <= delays[0] <= 660
    assert 1080 <= delays[1] <= 1320
    for d in delays[2:]:
        assert 1620 <= d <= 1980
    # the adaptive interval itself is untouched by errors; a success resets the counter
    assert sched.interval_s == 300
    s.record_result("x", changed=False)
    assert sched.errors_in_row == 0
    assert sched.next_run_at == clock.now + timedelta(seconds=300)


def test_blocked_backs_off_one_step_further_than_error(clock):
    s = make(clock, jitter=0.0)
    s.add_source("x", 300)
    s.record_result("x", changed=False, blocked=True)
    assert (s.get("x").next_run_at - clock.now).total_seconds() == 1200  # 300 * 2**(1+1)


def test_jitter_is_deterministic_with_seeded_rng(clock):
    a = Scheduler(SchedulerConfig(jitter=0.2), clock=clock, rng=random.Random(7))
    b = Scheduler(SchedulerConfig(jitter=0.2), clock=clock, rng=random.Random(7))
    for s in (a, b):
        s.add_source("x", 300)
        s.record_result("x", changed=False, error=True)
    assert a.get("x").next_run_at == b.get("x").next_run_at


def test_business_hours_detection_in_asuncion():
    s = Scheduler(SchedulerConfig(), clock=lambda: BUSINESS_NOW)
    assert s.is_business_hours(BUSINESS_NOW) is True
    assert s.is_business_hours(NIGHT_NOW) is False
    sunday = BUSINESS_NOW - timedelta(days=1)  # 2026-11-01 is a Sunday
    assert s.is_business_hours(sunday) is False
    saturday = BUSINESS_NOW - timedelta(days=2)
    assert s.is_business_hours(saturday) is True
    cfg = SchedulerConfig(business_days=frozenset({0, 1, 2, 3, 4}))
    assert Scheduler(cfg, clock=lambda: saturday).is_business_hours() is False


def test_off_hours_interval_is_slower():
    night = FakeClock(NIGHT_NOW)
    s = make(night, off_hours_factor=3.0)
    s.add_source("x", 300)
    assert s.effective_interval("x") == 900
    s.mark_started("x")
    sched = s.record_result("x", changed=False)
    assert sched.next_run_at == night.now + timedelta(seconds=900)
    # the stored (daytime) interval is untouched
    assert sched.interval_s == 300
    # capped at max_interval * factor
    s.override("x", interval_s=None)
    sched.interval_s = 900
    assert s.effective_interval("x") == 2700


def test_manual_override_fixes_interval_and_ignores_adaptivity(clock):
    s = make(clock)
    s.add_source("x", 300)
    sched = s.override("x", interval_s=30)  # below the floor -> clamped
    assert sched.interval_s == 60 and sched.manual_interval_s == 60
    sched = s.override("x", interval_s=120)
    assert sched.next_run_at == clock.now + timedelta(seconds=120)
    s.mark_started("x")
    s.record_result("x", changed=True)
    assert sched.interval_s == 120  # no shortening
    for _ in range(10):
        s.record_result("x", changed=False)
    assert sched.interval_s == 120  # no lengthening
    night = FakeClock(NIGHT_NOW)
    s2 = make(night)
    s2.add_source("x", 300)
    s2.override("x", interval_s=120)
    assert s2.effective_interval("x") == 120  # no off-hours scaling either
    s.clear_override("x")
    assert sched.manual_interval_s is None and sched.interval_s == 300


def test_disable_enable_and_run_now(clock):
    s = make(clock)
    s.add_source("x", 300)
    sched = s.override("x", enabled=False)
    assert sched.enabled is False and sched.next_run_at is None
    assert s.due() == []
    # a manual poll is still allowed once
    s.run_now("x")
    assert s.due() == ["x"]
    s.mark_started("x")
    s.record_result("x", changed=False)
    assert sched.next_run_at is None and s.due() == []
    clock.advance(1000)
    sched = s.override("x", enabled=True)
    assert sched.enabled is True and sched.next_run_at == clock.now
    assert s.due() == ["x"]


def test_run_now_requests_are_dispatched_first(clock):
    s = make(clock)
    s.add_source("a", 300)
    s.add_source("b", 300)
    for sid in ("a", "b"):
        s.mark_started(sid)
        s.record_result(sid, changed=False)
    clock.advance(400)
    assert s.due() == ["a", "b"]
    s.run_now("b")
    assert s.due() == ["b", "a"]


def test_restore_from_persisted_state(clock):
    s = make(clock)
    later = clock.now + timedelta(seconds=120)
    sched = s.add_source("x", 300, interval_s=150, manual_interval_s=None, first_run_at=later)
    assert sched.interval_s == 150 and sched.next_run_at == later
    assert s.due() == []
    assert s.next_wakeup() == later
    sched2 = s.add_source("y", 300, manual_interval_s=200, enabled=False)
    assert sched2.manual_interval_s == 200 and sched2.interval_s == 200 and sched2.next_run_at is None


def test_config_validation():
    with pytest.raises(ValueError):
        SchedulerConfig(min_interval_s=0)
    with pytest.raises(ValueError):
        SchedulerConfig(min_interval_s=100, max_interval_s=50)
    with pytest.raises(ValueError):
        SchedulerConfig(business_hours=(20, 7))
    s = make(FakeClock())
    with pytest.raises(KeyError):
        s.get("nope")
