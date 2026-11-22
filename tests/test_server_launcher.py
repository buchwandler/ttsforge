from __future__ import annotations

import builtins
import errno
import ipaddress
import json
import select
import socket
import subprocess
import sys
from pathlib import Path
from urllib.request import urlopen

import pytest
from typer.testing import CliRunner

from ttsforge.cli.app import app
from ttsforge.server import launcher


def test_serve_command_uses_shared_launcher_and_options(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(launcher, "run_server", lambda **kwargs: calls.append(kwargs))

    result = CliRunner().invoke(
        app,
        [
            "serve",
            "--host",
            "127.0.0.2",
            "--port",
            "0",
            "--token",
            "cli-test-token",
            "--state-dir",
            str(tmp_path),
            "--allow-origin",
            "https://studio.example",
            "--log-level",
            "warning",
            "--debug",
        ],
    )

    assert result.exit_code == 0, result.output
    assert calls == [
        {
            "host": "127.0.0.2",
            "port": 0,
            "token": "cli-test-token",
            "state_dir": tmp_path,
            "allowed_origins": ["https://studio.example"],
            "log_level": "warning",
            "debug": True,
        }
    ]


def test_server_module_help_does_not_require_optional_server_dependencies() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "ttsforge.server", "--help"],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0
    assert "--port" in result.stdout
    assert "--token" in result.stdout
    assert result.stderr == ""


def test_missing_optional_server_dependencies_have_precise_diagnostic(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    original_import = builtins.__import__

    def import_without_uvicorn(name: str, *args: object, **kwargs: object) -> object:
        if name == "uvicorn":
            raise ModuleNotFoundError("No module named 'uvicorn'", name="uvicorn")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_uvicorn)

    with pytest.raises(SystemExit) as error:
        launcher.run_server(token="test-token", port=0)

    assert error.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        "The local API requires the TTSForge server extra.\n"
        'Install with: uv pip install "ttsforge[server]"\n'
    )


@pytest.mark.parametrize("host", ["0.0.0.0", "2001:db8::1"])
def test_non_loopback_binding_is_rejected(
    capsys: pytest.CaptureFixture[str], host: str
) -> None:
    with pytest.raises(SystemExit) as error:
        launcher.run_server(host=host, token="test-token", port=0)

    assert error.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        "Unable to start the TTSForge local API: ValueError: "
        "The local API can bind only to a loopback host.\n"
    )


@pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.2", "localhost"])
def test_loopback_hosts_bind_to_loopback_addresses(host: str) -> None:
    listener = launcher._create_listener(host, 0)
    try:
        address = ipaddress.ip_address(listener.getsockname()[0])
        assert address.is_loopback
        expected_family = socket.AF_INET6 if address.version == 6 else socket.AF_INET
        assert listener.family == expected_family
    finally:
        listener.close()


@pytest.mark.skipif(not socket.has_ipv6, reason="IPv6 is disabled by the OS")
def test_ipv6_loopback_listener_uses_ipv6_family() -> None:
    try:
        listener = launcher._create_listener("::1", 0)
    except OSError as error:
        if error.errno in {errno.EADDRNOTAVAIL, errno.EAFNOSUPPORT}:
            pytest.skip("The OS has no configured IPv6 loopback address")
        raise
    with listener:
        assert listener.family == socket.AF_INET6
        assert ipaddress.ip_address(listener.getsockname()[0]).is_loopback


@pytest.mark.parametrize("entrypoint", ["module", "console"])
def test_server_entrypoints_port_zero_emit_readiness_after_startup(
    tmp_path: Path, entrypoint: str
) -> None:
    pytest.importorskip("fastapi")
    pytest.importorskip("uvicorn")
    command = [sys.executable, "-m", "ttsforge.server"]
    if entrypoint == "console":
        command = [
            sys.executable,
            "-c",
            "from ttsforge.launcher import main; main()",
            "serve",
        ]
    command.extend(
        [
            "--host",
            "127.0.0.1",
            "--port",
            "0",
            "--token",
            "module-test-token",
            "--state-dir",
            str(tmp_path / "server-state"),
        ]
    )
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None
        readable, _, _ = select.select([process.stdout], [], [], 15)
        assert readable, "server did not publish its readiness line"
        line = process.stdout.readline()
        assert line.endswith("\n")
        ready = json.loads(line)
        assert ready == {
            "type": "server.ready",
            "host": "127.0.0.1",
            "port": ready["port"],
            "api_version": 1,
        }
        assert isinstance(ready["port"], int) and ready["port"] > 0

        with urlopen(
            f"http://127.0.0.1:{ready['port']}/api/v1/health", timeout=5
        ) as response:
            assert json.load(response) == {"ok": True}
    finally:
        process.terminate()
        try:
            extra_stdout, stderr = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            extra_stdout, stderr = process.communicate(timeout=5)

    assert extra_stdout == ""
    assert "Traceback" not in stderr
