"""P2-T07: /api/catalog/error-codes."""

W = {"X-Tutor": "1"}
NEW = {"code": "computational.sign_rule", "category": "computational", "description": "Sai quy tắc dấu"}


def test_list_add_patch(client):
    codes = client.get("/api/catalog/error-codes").json()
    assert len(codes) == 18 and all(c["active"] == 1 for c in codes)
    r = client.post("/api/catalog/error-codes", json=NEW, headers=W)
    assert r.status_code == 201 and r.json()["active"] == 1 and r.json()["example"] is None
    patch = {"example": "$-(-1) = 1$", "active": False}
    r = client.patch("/api/catalog/error-codes/computational.sign_rule", json=patch, headers=W)
    assert (r.json()["example"], r.json()["active"]) == ("$-(-1) = 1$", 0)
    assert len(client.get("/api/catalog/error-codes").json()) == 19


def test_add_rejected(client):
    r = client.post("/api/catalog/error-codes", json=NEW | {"code": "conceptual.sign_rule"}, headers=W)
    assert (r.status_code, r.json()["error"]["code"]) == (422, "validation_error")
    r = client.post("/api/catalog/error-codes", json=NEW | {"code": "other.unclear", "category": "other"}, headers=W)
    assert r.status_code == 422 and "đã có" in r.json()["error"]["message"]


def test_patch_errors(client):
    r = client.patch("/api/catalog/error-codes/other.unclear", json={"active": False}, headers=W)
    assert (r.status_code, r.json()["error"]["code"]) == (422, "validation_error")
    r = client.patch("/api/catalog/error-codes/other.nope", json={"description": "d"}, headers=W)
    assert (r.status_code, r.json()["error"]["code"]) == (404, "not_found")


def test_mistakes(client):
    assert client.get("/api/catalog/error-codes/other.unclear/mistakes").json() == []
    assert client.get("/api/catalog/error-codes/other.nope/mistakes").status_code == 404


def test_export_csv(client):
    r = client.get("/api/catalog/export?file=error_code")
    assert r.headers["content-type"].startswith("text/csv")
    assert 'filename="error_code.csv"' in r.headers["content-disposition"]
    lines = r.text.splitlines()
    assert lines[0] == "code,category,description,example,active" and len(lines) == 19


def test_edits_return_the_new_03_prompt_version(client):
    first = client.post("/api/catalog/error-codes", json=NEW, headers=W).json()["prompt_version"]
    assert first.startswith("03-")
    r = client.patch("/api/catalog/error-codes/computational.sign_rule", json={"example": "$-(-1) = 1$"}, headers=W)
    second = r.json()["prompt_version"]
    r = client.patch("/api/catalog/error-codes/computational.sign_rule", json={"active": False}, headers=W)
    third = r.json()["prompt_version"]
    assert len({first, second, third}) == 3
