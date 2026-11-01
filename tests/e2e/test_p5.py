"""P5-T05: bank import end to end over HTTP, no LLM call (C-34)."""

import shutil
import time
from contextlib import closing
from pathlib import Path

from tests.api.test_sessions import W
from tests.fakes import FakeLLM
from tutor import llm
from tutor.db import repo, seed_dummy

ROOT = Path(__file__).resolve().parents[2]
MIX = ROOT / "tests" / "fixtures" / "bank" / "import-mix.tex"


def card_at(client, tid, *stages) -> dict:
    for _ in range(100):
        card = client.get(f"/api/threads/{tid}?view=teacher").json()["card"]
        if card["stage"] in stages:
            return card
        time.sleep(0.05)
    raise AssertionError(card)


def total(client) -> int:
    return client.get("/api/backup").json()["total"]


def test_bank_import_end_to_end(client, paths):
    fake = FakeLLM({})
    llm.set_backend(fake)
    with closing(repo.connect(paths.tutor_db)) as conn:
        seed_dummy.seed(conn, ROOT / "data" / "dummy" / "bank")
        kc = {k["code"]: k["id"] for k in repo.list_kc(conn)}
    shutil.copy(MIX, paths.inbox / "bank" / "mix.tex")
    before = total(client)
    assert [f["status"] for f in client.get("/api/bank/inbox").json()] == ["partly"]

    r = client.post("/api/bank/imports", json={"file": "mix.tex"}, headers=W)
    assert (r.status_code, r.json()["status"]) == (202, "running")
    tid = r.json()["thread_id"]
    card = card_at(client, tid, "preview", "failed")
    assert (card["stage"], card["n_total"], card["n_ready"], card["n_need"], card["n_existing"]) == (
        "preview", 5, 1, 3, 1)  # fmt: skip

    r = client.post(f"/api/threads/{tid}/resume", headers=W)
    assert (r.status_code, r.json()["error"]["code"], r.json()["error"]["detail"]) == (409, "undecided_items", {"n": 2})
    answer = {"items": {"8DS-NEW-002": {"kc_ids": [kc["8DS-HSBN-02"]]}, "8DS-NEW-003": {"kc_ids": [kc["8DS-HSBN-01"]]}}}
    assert client.put(f"/api/threads/{tid}/decisions", json=answer, headers=W).json() == {"saved": True, "pending": 0}
    assert total(client) == before  # nothing is written before the last resume

    assert client.post(f"/api/threads/{tid}/resume", headers=W).status_code == 202
    card = card_at(client, tid, "saved", "failed")
    assert (card["stage"], card["receipt"]) == ("saved", {"added": 4, "skipped_existing": 1})
    assert total(client) > before

    grid = client.get("/api/bank/problems?view=teacher&q=den long").json()
    assert "8DS-NEW-002" in [i["ref"] for i in grid["items"][:5]]
    assert [f["status"] for f in client.get("/api/bank/inbox").json()] == ["imported"]

    r = client.post("/api/bank/imports", json={"file": "mix.tex"}, headers=W)
    assert r.status_code == 202 and r.json()["thread_id"] != tid
    again = r.json()["thread_id"]
    card_at(client, again, "preview", "failed")
    assert client.post(f"/api/threads/{again}/resume", headers=W).status_code == 202
    assert card_at(client, again, "saved", "failed")["receipt"]["added"] == 0
    assert fake.calls == []
