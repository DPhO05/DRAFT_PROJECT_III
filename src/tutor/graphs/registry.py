"""The graphs and hooks every runner has, whether it lives in the app or in a CLI command."""

from tutor.config import DataPaths
from tutor.graphs import bank, report, session, worksheet
from tutor.graphs.runner import Runner


def make_runner(paths: DataPaths, max_workers: int = 2) -> Runner:
    graphs = {
        session.GRAPH: session.build(paths),
        bank.GRAPH: bank.build(paths),
        worksheet.GRAPH: worksheet.build(paths),
        report.GRAPH: report.build(paths),
    }
    runner = Runner(paths, graphs, max_workers)
    runner.on_fail(session.GRAPH, session.on_fail(paths))
    runner.pending_fn(session.GRAPH, session.pending(paths))
    runner.pending_fn(bank.GRAPH, bank.pending(paths))
    runner.pending_fn(worksheet.GRAPH, worksheet.pending(paths))
    runner.resume_check(worksheet.GRAPH, worksheet.check(paths))
    runner.pending_fn(report.GRAPH, report.pending(paths))
    return runner
