import asyncio
import json
from types import SimpleNamespace as NS

from fastapi.testclient import TestClient

from jarvis.core.agent import MAX_STEPS, Agent
from jarvis.interfaces import api
from jarvis.voice import intents


def text(t):
    return NS(type="text", text=t)


def tool_use(name, input, id="t1"):
    return NS(type="tool_use", name=name, input=input, id=id)


class FakeRouter:
    """Oldindan yozilgan javoblarni qaytaradi va har bir so'rovni eslab qoladi."""

    available = True

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    async def complete(self, *, system, messages, tools, max_tokens=16000):
        self.calls.append({"messages": list(messages), "tools": tools})
        return self.responses.pop(0)


def resp(stop_reason, *blocks):
    return NS(stop_reason=stop_reason, content=list(blocks))


def run(coro):
    return asyncio.run(coro)


def test_tool_names_are_api_safe():
    agent = Agent(FakeRouter())
    names = {t["name"] for t in agent.tools}
    assert {"system__status", "shell__run"} <= names
    assert all("." not in n for n in names)


def test_plain_answer():
    agent = Agent(FakeRouter(resp("end_turn", text("Salom!"))))
    assert run(agent.run("salom")) == "Salom!"


def test_tool_call_loop():
    router = FakeRouter(
        resp("tool_use", text("Tekshiraman."), tool_use("system__status", {})),
        resp("end_turn", text("Disk yetarli.")),
    )
    agent = Agent(router)
    assert run(agent.run("disk qanday?")) == "Disk yetarli."

    tool_result = router.calls[1]["messages"][-1]["content"][0]
    assert tool_result["tool_use_id"] == "t1"
    assert "disk_free_gb" in json.loads(tool_result["content"])


def test_dangerous_shell_is_denied_by_policy():
    router = FakeRouter(
        resp("tool_use", tool_use("shell__run", {"command": "rm -rf ~"})),
        resp("end_turn", text("Bu buyruq taqiqlangan.")),
    )
    run(Agent(router).run("hamma narsani o'chir"))
    result = json.loads(router.calls[1]["messages"][-1]["content"][0]["content"])
    assert result["status"] == "denied"


def test_unknown_tool_returns_error_result():
    router = FakeRouter(
        resp("tool_use", tool_use("nope", {})),
        resp("end_turn", text("ok")),
    )
    run(Agent(router).run("x"))
    assert router.calls[1]["messages"][-1]["content"][0]["is_error"] is True


def test_invalid_tool_args_return_error_result():
    router = FakeRouter(
        resp("tool_use", tool_use("shell__run", {})),  # command yo'q
        resp("end_turn", text("ok")),
    )
    run(Agent(router).run("x"))
    assert router.calls[1]["messages"][-1]["content"][0]["is_error"] is True


def test_step_limit():
    loop = [resp("tool_use", tool_use("system__status", {}, id=f"t{i}")) for i in range(MAX_STEPS)]
    assert "to'xtatdim" in run(Agent(FakeRouter(*loop)).run("x"))


def test_refusal():
    assert "bajara olmayman" in run(Agent(FakeRouter(resp("refusal"))).run("x"))


def test_session_memory_is_kept_per_session():
    router = FakeRouter(
        resp("end_turn", text("1")), resp("end_turn", text("2")), resp("end_turn", text("3"))
    )
    agent = Agent(router)
    run(agent.run("birinchi", "a"))
    run(agent.run("ikkinchi", "a"))
    run(agent.run("boshqa", "b"))
    assert len(router.calls[1]["messages"]) == 3  # user, assistant, user
    assert len(router.calls[2]["messages"]) == 1  # yangi sessiya


def test_failed_run_resets_session():
    class Boom(FakeRouter):
        async def complete(self, **kw):
            raise RuntimeError("tarmoq")

    agent = Agent(Boom())
    try:
        run(agent.run("x", "s"))
    except RuntimeError:
        pass
    assert "s" not in agent.sessions


def test_handle_text_uses_agent_when_available(monkeypatch):
    agent = Agent(FakeRouter(resp("end_turn", text("agent javobi"))))
    monkeypatch.setattr(intents, "get_agent", lambda: agent)
    monkeypatch.setattr("jarvis.core.agent.get_agent", lambda: agent)
    assert run(intents.handle_text("nima gap")) == "agent javobi"


def test_agent_ask_endpoint_without_key():
    r = TestClient(api.app).post("/agent/ask", json={"text": "holat"})
    assert r.status_code == 200
    assert "CPU" in r.json()["reply"]
