import asyncio

from jarvis.tools.system import NoArgs, ShellArgs, shell_run, system_status


def test_system_status_fields():
    s = asyncio.run(system_status(NoArgs()))
    assert s["cpu_count"] >= 1
    assert 0 <= s["disk_used_pct"] <= 100


def test_shell_run_allowed():
    r = asyncio.run(shell_run(ShellArgs(command="echo salom")))
    assert r["status"] == "ok"
    assert r["stdout"].strip() == "salom"


def test_shell_run_denied_never_executes():
    r = asyncio.run(shell_run(ShellArgs(command="rm -rf /tmp/jarvis-should-not-run")))
    assert r["status"] == "denied"


def test_shell_run_confirm_without_approval():
    r = asyncio.run(shell_run(ShellArgs(command="git commit -m x")))
    assert r["status"] == "needs_approval"
