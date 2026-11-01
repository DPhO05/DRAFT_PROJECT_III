"""The graphs and hooks every runner has, whether it lives in the app or in a CLI command."""

from tutor.config import DataPaths
from tutor.graphs import bank, session
from tutor.graphs.runner import Runner


def make_runner(paths: DataPaths, max_workers: int = 2) -> Runner:
    runner = Runner(paths, {session.GRAPH: session.build(paths), bank.GRAPH: bank.build(paths)}, max_workers)
    runner.on_fail(session.GRAPH, session.on_fail(paths))
    runner.pending_fn(session.GRAPH, session.pending(paths))
    runner.pending_fn(bank.GRAPH, bank.pending(paths))
    return runner
