"""LangGraph Studio entry (`uv run langgraph dev`): the app's four graphs on data-dev/, fake LLM only."""

from pathlib import Path

from tutor import config, devfake, llm
from tutor.db import repo
from tutor.graphs import bank, report, session, worksheet

# Studio runs the real nodes, commit included: keep it off the teacher's data/ and off the paid API.
paths = config.paths(Path(__file__).parent / "data-dev").ensure()
repo.init_db(paths.tutor_db, paths.backup)
llm.configure(paths.logs / "llm.jsonl", devfake.models())
llm.set_backend(devfake.DevFakeLLM())

g1 = session.build(paths)
g2 = bank.build(paths)
g4 = worksheet.build(paths)
g5 = report.build(paths)
