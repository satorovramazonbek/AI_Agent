from fastapi.testclient import TestClient

from jarvis.interfaces.api import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_tools_listed():
    names = {t["name"] for t in client.get("/tools").json()}
    assert {"system.status", "shell.run"} <= names


def test_policy_endpoint_denies_sudo():
    r = client.post("/policy/check", json={"command": "sudo rm -rf /"})
    assert r.json()["decision"] == "deny"
