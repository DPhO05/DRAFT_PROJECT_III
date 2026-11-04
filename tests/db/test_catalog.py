"""P1-T03: import kc.csv + kc_prereq.csv; single-KC edits keep the graph acyclic."""

from pathlib import Path

import pytest

from tutor.db import repo

BANK = Path(__file__).resolve().parents[2] / "data" / "dummy" / "bank"


def bank_csv():
    return repo.read_catalog((BANK / "kc.csv").read_text("utf-8-sig"), (BANK / "kc_prereq.csv").read_text("utf-8-sig"))


def test_import_dummy_bank_then_reimport_is_noop(conn):
    kcs, pre = bank_csv()
    preview = repo.import_catalog(conn, kcs, pre, apply=False)
    assert (len(preview["new_kc"]), len(preview["new_prereq"])) == (74, 74)
    assert conn.execute("SELECT count(*) FROM kc").fetchone()[0] == 0  # preview writes nothing
    repo.import_catalog(conn, kcs, pre, apply=True)
    assert repo.row_counts(conn)["kc"] == 74 and repo.row_counts(conn)["kc_prereq"] == 74
    again = repo.import_catalog(conn, kcs, pre, apply=True)
    assert again["new_kc"] == again["changed_kc"] == again["new_prereq"] == []


def test_ensure_catalog_once(conn):
    assert repo.ensure_catalog(conn, BANK / "kc.csv", BANK / "kc_prereq.csv") == 74
    assert repo.ensure_catalog(conn, BANK / "kc.csv", BANK / "kc_prereq.csv") == 0
    assert repo.row_counts(conn)["kc"] == 74


def test_cycle_in_csv_is_rejected_with_path(conn):
    kcs = [{"code": c, "name": c, "description": "d", "parent_code": "", "lop": "8"} for c in "ABC"]
    pre = [("A", "B"), ("B", "C"), ("C", "A")]
    with pytest.raises(repo.CatalogError) as e:
        repo.import_catalog(conn, kcs, pre, apply=True)
    assert e.value.cycle in (["A", "B", "C", "A"], ["B", "C", "A", "B"], ["C", "A", "B", "C"])
    assert repo.row_counts(conn)["kc"] == 0


def test_unknown_parent_or_prereq_rejected(conn):
    kcs = [{"code": "A", "name": "a", "description": "d", "parent_code": "NOPE", "lop": "8"}]
    with pytest.raises(repo.CatalogError, match="NOPE"):
        repo.import_catalog(conn, kcs, [], apply=False)


def test_single_kc_edits_block_self_and_cycle(conn):
    a = repo.add_kc(conn, code="A", name="a", description="d", lop=8)
    b = repo.add_kc(conn, code="B", name="b", description="d", lop=8)
    repo.add_prereq(conn, a, b)
    with pytest.raises(repo.CatalogError) as e:
        repo.add_prereq(conn, b, a)
    assert e.value.cycle == ["B", "A", "B"]
    with pytest.raises(repo.CatalogError):
        repo.add_prereq(conn, a, a)
    repo.remove_prereq(conn, a, b)
    repo.add_prereq(conn, b, a)
    repo.update_kc(conn, a, description="mới")
    assert repo.list_kc(conn)[0]["description"] == "mới"


def test_export_then_import_is_noop(conn):
    kcs, pre = bank_csv()
    repo.import_catalog(conn, kcs, pre, apply=True)
    kc_csv, pre_csv = repo.export_catalog(conn)
    r = repo.import_catalog(conn, *repo.read_catalog(kc_csv, pre_csv), apply=False)
    assert r["new_kc"] == r["changed_kc"] == r["new_prereq"] == []


def test_csv_with_wrong_header_is_catalog_error(conn):
    with pytest.raises(repo.CatalogError, match="kc_code"):
        repo.read_catalog("code,name,description,parent_code,lop\n", "kc,prereq\nA,B\n")
    with pytest.raises(repo.CatalogError, match="description"):
        repo.read_catalog("code,name\nA,a\n", "kc_code,prereq_code\n")


def test_parent_must_be_a_group(conn):
    g = repo.add_kc(conn, code="G", name="nhóm", description="d")
    leaf = repo.add_kc(conn, code="L", name="lá", description="d", parent_id=g)
    with pytest.raises(repo.CatalogError):
        repo.add_kc(conn, code="X", name="x", description="d", parent_id=leaf)  # 3 levels
    with pytest.raises(repo.CatalogError):
        repo.add_kc(conn, code="Y", name="y", description="d", parent_id=999)
    with pytest.raises(repo.CatalogError):
        repo.update_kc(conn, g, parent_id=g)  # itself
    other = repo.add_kc(conn, code="G2", name="nhóm 2", description="d")
    with pytest.raises(repo.CatalogError):
        repo.update_kc(conn, g, parent_id=other)  # a group with children cannot become a leaf
    repo.update_kc(conn, leaf, parent_id=other)
