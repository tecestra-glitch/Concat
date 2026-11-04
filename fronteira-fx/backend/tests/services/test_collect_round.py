"""One serverless round (`Collector.run_round`): due sources only, no browser, budget checked before each start."""

from sqlalchemy import select

from fronteira_fx.models import Task
from fronteira_fx.services.collector import Collector
from tests.conftest import NOW, make_settings
from tests.fakes import Clock, FakeAdapter


class SlowAdapter(FakeAdapter):
    """Each fetch advances the budget clock by `cost_s`, as a slow provider would."""

    def __init__(self, source_id, *, box, cost_s, **kwargs):
        super().__init__(source_id, **kwargs)
        self.box = box
        self.cost_s = cost_s

    async def fetch(self, **params):
        self.box["t"] += self.cost_s
        return await super().fetch(**params)


def queue_task(session_factory, source_id: str) -> str:
    with session_factory() as s:
        task = Task(
            source_id=source_id, kind="fetch_quote", params={}, status="queued", data_mode="real", created_at=NOW
        )
        s.add(task)
        s.commit()
        return task.id


def task_row(session_factory, task_id: str) -> Task:
    with session_factory() as s:
        return s.scalars(select(Task).where(Task.id == task_id)).one()


async def test_budget_stops_starting_new_sources(session_factory):
    box = {"t": 0.0}
    adapters = {sid: SlowAdapter(sid, box=box, cost_s=60) for sid in ("a", "b", "c")}
    collector = Collector(session_factory, make_settings(), adapters=adapters, now_fn=Clock())

    result = await collector.run_round(budget_s=45, clock=lambda: box["t"])

    assert [o.source_id for o in result.outcomes] == ["a"]  # started at t=0, ran until t=60
    assert adapters["b"].calls == 0 and adapters["c"].calls == 0
    assert result.budget_exhausted is True
    assert {s.source_id: s.reason for s in result.skipped} == {
        "b": "orçamento de tempo da rodada esgotado",
        "c": "orçamento de tempo da rodada esgotado",
    }


async def test_browser_sources_are_skipped_and_their_tasks_stay_queued(session_factory):
    box = {"t": 0.0}
    wu = FakeAdapter("wu", method="browser")
    collector = Collector(
        session_factory,
        make_settings(),
        adapters={"chaco": FakeAdapter("chaco"), "wu": wu},
        now_fn=Clock(),
    )
    collector.ensure_sources()
    wu_task = queue_task(session_factory, "wu")

    result = await collector.run_round(budget_s=45, clock=lambda: box["t"])

    assert wu.calls == 0
    assert any(s.source_id == "wu" and "navegador" in s.reason for s in result.skipped)
    assert task_row(session_factory, wu_task).status == "queued"
    assert result.tasks_processed == 0


async def test_scheduled_sources_are_not_forced(session_factory):
    box = {"t": 0.0}
    adapter = FakeAdapter("chaco")
    collector = Collector(session_factory, make_settings(), adapters={"chaco": adapter}, now_fn=Clock())

    first = await collector.run_round(budget_s=45, clock=lambda: box["t"])
    second = await collector.run_round(budget_s=45, clock=lambda: box["t"])

    assert [o.source_id for o in first.outcomes] == ["chaco"]
    assert second.outcomes == []
    assert second.skipped[0].source_id == "chaco" and second.skipped[0].reason.startswith("próxima sondagem")
    assert adapter.calls == 1


async def test_tasks_not_started_inside_the_budget_go_back_to_the_queue(session_factory):
    box = {"t": 0.0}
    adapter = SlowAdapter("a", box=box, cost_s=60)
    collector = Collector(session_factory, make_settings(), adapters={"a": adapter}, now_fn=Clock())
    collector.ensure_sources()
    task_id = queue_task(session_factory, "a")

    result = await collector.run_round(budget_s=45, clock=lambda: box["t"])

    assert [o.source_id for o in result.outcomes] == ["a"]
    assert result.tasks_processed == 0 and result.budget_exhausted is True
    task = task_row(session_factory, task_id)
    assert task.status == "queued" and task.started_at is None


async def test_process_tasks_skip_browser_leaves_browser_tasks_queued(session_factory):
    collector = Collector(
        session_factory,
        make_settings(),
        adapters={"chaco": FakeAdapter("chaco"), "wu": FakeAdapter("wu", method="browser")},
        now_fn=Clock(),
    )
    collector.ensure_sources()
    chaco_task = queue_task(session_factory, "chaco")
    collector.ensure_sources()
    wu_task = queue_task(session_factory, "wu")

    done = await collector.process_tasks(skip_browser=True)

    assert done == 1
    assert task_row(session_factory, chaco_task).status == "done"
    assert task_row(session_factory, wu_task).status == "queued"


async def test_round_does_nothing_outside_real_mode(session_factory):
    adapter = FakeAdapter("chaco")
    collector = Collector(session_factory, make_settings(data_mode="demo"), adapters={"chaco": adapter}, now_fn=Clock())

    result = await collector.run_round(budget_s=45)

    assert result.data_mode == "demo" and result.outcomes == [] and result.skipped == []
    assert adapter.calls == 0
