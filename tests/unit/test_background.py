"""Tests for BackgroundTasks."""

import pytest

from hawkapi.background import BackgroundTasks


@pytest.fixture
def tasks():
    return BackgroundTasks()


async def test_add_and_run_sync_task(tasks):
    results = []

    def sync_task(value):
        results.append(value)

    tasks.add_task(sync_task, "hello")
    await tasks.run()
    assert results == ["hello"]


async def test_add_and_run_async_task(tasks):
    results = []

    async def async_task(value):
        results.append(value)

    tasks.add_task(async_task, "world")
    await tasks.run()
    assert results == ["world"]


async def test_multiple_tasks(tasks):
    results = []

    def task_a():
        results.append("a")

    async def task_b():
        results.append("b")

    tasks.add_task(task_a)
    tasks.add_task(task_b)
    await tasks.run()
    assert results == ["a", "b"]


async def test_task_with_kwargs(tasks):
    results = {}

    def task_with_kwargs(key, value=None):
        results[key] = value

    tasks.add_task(task_with_kwargs, "name", value="hawk")
    await tasks.run()
    assert results == {"name": "hawk"}


async def test_tasks_cleared_after_run(tasks):
    results = []

    def task():
        results.append(1)

    tasks.add_task(task)
    await tasks.run()
    assert len(results) == 1

    # Running again should not re-execute
    await tasks.run()
    assert len(results) == 1


async def test_failing_task_does_not_stop_others(tasks):
    results = []

    def failing_task():
        raise RuntimeError("boom")

    def good_task():
        results.append("ok")

    tasks.add_task(failing_task)
    tasks.add_task(good_task)
    await tasks.run()
    assert results == ["ok"]
