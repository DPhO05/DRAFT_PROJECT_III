"""MONO-P1-02: /api/students, /api/catalog."""

from pathlib import Path

BANK = Path(__file__).resolve().parents[2] / "data" / "dummy" / "bank"
W = {"X-Tutor": "1"}


def test_students_crud(client):
    r = client.post("/api/students", json={"name": "Trần Thị Bình", "grade": 9}, headers=W)
    assert r.status_code == 201 and r.json()["code"] == "HS-01"
    sid = r.json()["id"]
    assert client.patch(f"/api/students/{sid}", json={"note": "chăm"}, headers=W).json()["note"] == "chăm"
    assert [s["code"] for s in client.get("/api/students").json()] == ["HS-01"]
    assert client.post(f"/api/students/{sid}/archive", headers=W).json()["archived_at"]
    assert client.get("/api/students").json() == []
    assert len(client.get("/api/students?archived=1").json()) == 1


def test_student_errors(client):
    assert client.post("/api/students", json={"name": " "}, headers=W).json()["error"]["code"] == "validation_error"
    r = client.patch("/api/students/99", json={"name": "Lê Minh"}, headers=W)
    assert (r.status_code, r.json()["error"]["code"]) == (404, "not_found")


def test_name_needs_two_words(client):
    msg = "Nhập đủ họ và tên (ít nhất 2 chữ)"
    r = client.post("/api/students", json={"name": "Minh"}, headers=W)
    assert (r.status_code, r.json()["error"]["code"], r.json()["error"]["message"]) == (422, "validation_error", msg)
    sid = client.post("/api/students", json={"name": "Lê Minh"}, headers=W)
    assert sid.status_code == 201
    r = client.patch(f"/api/students/{sid.json()['id']}", json={"name": " Minh "}, headers=W)
    assert (r.status_code, r.json()["error"]["message"]) == (422, msg)
    assert client.patch(f"/api/students/{sid.json()['id']}", json={"note": "chăm"}, headers=W).status_code == 200


def csv_body():
    return {"kc_csv": (BANK / "kc.csv").read_text("utf-8-sig"), "prereq_csv": (BANK / "kc_prereq.csv").read_text()}


def test_import_preview_apply_export_roundtrip(client):
    p = client.post("/api/catalog/import/preview", json=csv_body(), headers=W).json()
    assert (len(p["new_kc"]), len(p["new_prereq"])) == (74, 74)
    assert client.get("/api/catalog/kc").json() == []
    assert len(client.post("/api/catalog/import", json=csv_body(), headers=W).json()["new_kc"]) == 74
    kc = client.get("/api/catalog/export?file=kc")
    assert kc.headers["content-type"].startswith("text/csv")
    pre = client.get("/api/catalog/export?file=prereq").text
    again = client.post("/api/catalog/import/preview", json={"kc_csv": kc.text, "prereq_csv": pre}, headers=W).json()
    assert again == {"new_kc": [], "changed_kc": [], "new_prereq": []}


def test_prereq_cycle_is_422_with_path(client):
    a = client.post("/api/catalog/kc", json={"code": "A", "name": "a", "description": "d", "lop": 8}, headers=W).json()
    b = client.post("/api/catalog/kc", json={"code": "B", "name": "b", "description": "d", "lop": 8}, headers=W).json()
    assert client.post(f"/api/catalog/kc/{a['id']}/prereqs", json={"prereq_id": b["id"]}, headers=W).status_code == 200
    r = client.post(f"/api/catalog/kc/{b['id']}/prereqs", json={"prereq_id": a["id"]}, headers=W)
    assert r.status_code == 422 and r.json()["error"]["detail"]["cycle"] == ["B", "A", "B"]
    assert client.delete(f"/api/catalog/kc/{a['id']}/prereqs/{b['id']}", headers=W).status_code == 200
    r = client.patch(f"/api/catalog/kc/{a['id']}", json={"description": "mới"}, headers=W)
    assert r.json()["description"] == "mới"


def test_csv_cycle_import_rejected(client):
    body = {"kc_csv": "code,name,description,parent_code,lop\nA,a,d,,8\nB,b,d,,8\n",
            "prereq_csv": "kc_code,prereq_code\nA,B\nB,A\n"}  # fmt: skip
    r = client.post("/api/catalog/import", json=body, headers=W)
    assert r.status_code == 422 and r.json()["error"]["detail"]["cycle"]
