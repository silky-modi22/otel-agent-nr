"""Process orchestration for local pipeline controls."""

from __future__ import annotations

import asyncio
import os
import signal
import socket
import subprocess
import time
from collections import deque
from pathlib import Path
from typing import Sequence

MAX_LOG_LINES = 200


def _collector_listening(endpoint_port: int = 4318) -> bool:
    try:
        with socket.create_connection(
            ("127.0.0.1", endpoint_port), timeout=0.75
        ):
            return True
    except OSError:
        return False


def _read_secret_file(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    value = text.strip()
    return value or None


def _resolve_github_token(repo_root: Path) -> str | None:
    for key in ("GITHUB_TOKEN", "GH_TOKEN"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    file_path = os.environ.get("GITHUB_TOKEN_FILE", "").strip()
    if file_path:
        token = _read_secret_file(Path(file_path))
        if token:
            return token
    return _read_secret_file(repo_root / ".github_token")


def _resolve_anthropic_key(repo_root: Path) -> str | None:
    value = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if value:
        return value
    file_path = os.environ.get("ANTHROPIC_API_KEY_FILE", "").strip()
    if file_path:
        key = _read_secret_file(Path(file_path))
        if key:
            return key
    return _read_secret_file(repo_root / ".anthropic_api_key")


class ProcessManager:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self._lock = asyncio.Lock()

        self._collector_proc: asyncio.subprocess.Process | None = None
        self._collector_mode: str | None = None
        self._collector_exit_code: int | None = None
        self._collector_task: asyncio.Task[None] | None = None
        self._collector_logs: deque[str] = deque(maxlen=MAX_LOG_LINES)

        self._job_proc: asyncio.subprocess.Process | None = None
        self._job_name: str | None = None
        self._job_exit_code: int | None = None
        self._job_task: asyncio.Task[None] | None = None
        self._job_logs: deque[str] = deque(maxlen=MAX_LOG_LINES)
        self._synthetic_logs: deque[str] = deque(maxlen=MAX_LOG_LINES)
        self._github_poll_logs: deque[str] = deque(maxlen=MAX_LOG_LINES)
        self._ingest_logs: deque[str] = deque(maxlen=MAX_LOG_LINES)
        self._gemini_logs: deque[str] = deque(maxlen=MAX_LOG_LINES)
        self._anthropic_logs: deque[str] = deque(maxlen=MAX_LOG_LINES)

    def _collector_bin_path(self) -> Path:
        resolved = self._resolve_collector_binary()
        if resolved is None:
            return self.repo_root / "dist" / "otel-custom" / "otel-custom"
        return resolved

    def _resolve_collector_binary(self) -> Path | None:
        candidates = [
            self.repo_root / "dist" / "otelcol-contrib" / "otelcol-contrib.exe",
            self.repo_root / "dist" / "otelcol-contrib" / "otelcol-contrib",
            self.repo_root / "dist" / "otel-custom" / "otel-custom.exe",
            self.repo_root / "dist" / "otel-custom" / "otel-custom",
        ]
        for path in candidates:
            if os.access(path, os.X_OK):
                return path
        return None

    def collector_binary_ready(self) -> bool:
        return self._resolve_collector_binary() is not None

    def clickhouse_settings_set(self) -> bool:
        return self._clickhouse_credentials()[0]

    def _clickhouse_credentials(self) -> tuple[bool, str, str, str]:
        endpoint = os.environ.get("CLICKHOUSE_ENDPOINT", "").strip()
        user = os.environ.get("CLICKHOUSE_USER", "").strip()
        password = os.environ.get("CLICKHOUSE_PASSWORD", "").strip()
        if not endpoint:
            endpoint = _read_secret_file(self.repo_root / ".clickhouse_endpoint") or ""
        if not user:
            user = _read_secret_file(self.repo_root / ".clickhouse_user") or ""
        if not password:
            password = _read_secret_file(self.repo_root / ".clickhouse_password") or ""
        ok = bool(endpoint and user and password)
        return ok, endpoint, user, password

    def _apply_clickhouse_env(self, env: dict[str, str]) -> None:
        ok, endpoint, user, password = self._clickhouse_credentials()
        if not ok:
            raise RuntimeError(
                "Missing ClickHouse settings. Set CLICKHOUSE_* env vars or create "
                ".clickhouse_endpoint, .clickhouse_user, .clickhouse_password."
            )
        env.setdefault("CLICKHOUSE_ENDPOINT", endpoint)
        env.setdefault("CLICKHOUSE_USER", user)
        env.setdefault("CLICKHOUSE_PASSWORD", password)

    def new_relic_key_set(self) -> bool:
        env = os.environ.get("NEW_RELIC_LICENSE_KEY", "").strip()
        if env:
            return True
        return (
            _read_secret_file(self.repo_root / ".new_relic_license_key")
            is not None
        )

    def github_token_set(self) -> bool:
        return _resolve_github_token(self.repo_root) is not None

    def anthropic_key_set(self) -> bool:
        return _resolve_anthropic_key(self.repo_root) is not None

    def resolve_anthropic_key(self) -> str | None:
        return _resolve_anthropic_key(self.repo_root)

    def collector_listening(self) -> bool:
        return _collector_listening()

    def _append_collector_log(self, line: str) -> None:
        self._collector_logs.append(line.rstrip("\n"))

    def _append_job_log(self, line: str) -> None:
        self._job_logs.append(line.rstrip("\n"))

    def _append_to_sinks(self, sinks: Sequence[deque[str]], line: str) -> None:
        text = line.rstrip("\n")
        for sink in sinks:
            sink.append(text)

    def _job_log_sinks(self, name: str) -> tuple[deque[str], ...]:
        if name == "synthetic-agent":
            return (self._job_logs, self._synthetic_logs)
        if name == "github-poll-once":
            return (self._job_logs, self._github_poll_logs)
        if name == "ingest-sample":
            return (self._job_logs, self._ingest_logs)
        if name == "gemini-sample":
            return (self._job_logs, self._gemini_logs)
        if name == "anthropic-sample":
            return (self._job_logs, self._anthropic_logs)
        return (self._job_logs,)

    async def _drain_output(
        self, proc: asyncio.subprocess.Process, sinks: Sequence[deque[str]]
    ) -> None:
        stream = proc.stdout
        if stream is None:
            return
        while True:
            line = await stream.readline()
            if not line:
                break
            self._append_to_sinks(
                sinks, line.decode("utf-8", errors="replace")
            )

    async def _watch_collector(self, proc: asyncio.subprocess.Process) -> None:
        await self._drain_output(proc, (self._collector_logs,))
        code = await proc.wait()
        async with self._lock:
            if self._collector_proc is proc:
                self._collector_exit_code = code
                self._collector_proc = None
                self._collector_mode = None
                self._collector_task = None

    async def _watch_job(
        self, proc: asyncio.subprocess.Process, sinks: Sequence[deque[str]]
    ) -> None:
        await self._drain_output(proc, sinks)
        code = await proc.wait()
        async with self._lock:
            if self._job_proc is proc:
                self._job_exit_code = code
                self._job_proc = None
                self._job_name = None
                self._job_task = None

    async def start_collector(self, mode: str) -> dict[str, str]:
        if mode not in {"local", "newrelic", "dual", "clickhouse"}:
            raise RuntimeError(
                "mode must be local, newrelic, dual, or clickhouse"
            )
        binary_path = self._resolve_collector_binary()
        if binary_path is None:
            raise RuntimeError(
                "Collector binary not found. "
                "Run ./scripts/build-collector.sh or place otelcol-contrib under dist/."
            )

        if mode == "local":
            config_rel = "collector/collector-config.yaml"
        elif mode == "dual":
            config_rel = "collector/collector-config-dual.yaml"
        elif mode == "clickhouse":
            config_rel = "collector/collector-config-clickhouse.yaml"
        else:
            config_rel = "collector/collector-config-nr.yaml"
        config_path = self.repo_root / config_rel
        if not config_path.is_file():
            raise RuntimeError(f"Config not found: {config_rel}")

        env = os.environ.copy()
        if mode in {"newrelic", "dual"}:
            license_key = env.get("NEW_RELIC_LICENSE_KEY", "").strip()
            if not license_key:
                from_file = _read_secret_file(
                    self.repo_root / ".new_relic_license_key"
                )
                if from_file:
                    license_key = from_file
                    env["NEW_RELIC_LICENSE_KEY"] = from_file
            if not license_key:
                raise RuntimeError(
                    "NEW_RELIC_LICENSE_KEY is required for New Relic mode."
                )

        if mode in {"dual", "clickhouse"}:
            self._apply_clickhouse_env(env)

        async with self._lock:
            if (
                self._collector_proc is not None
                and self._collector_proc.returncode is None
            ):
                raise RuntimeError("Collector is already running.")
            self._collector_logs.clear()
            self._collector_exit_code = None
            proc = await asyncio.create_subprocess_exec(
                str(binary_path),
                f"--config={config_rel}",
                cwd=str(self.repo_root),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            self._collector_proc = proc
            self._collector_mode = mode
            self._collector_task = asyncio.create_task(self._watch_collector(proc))
            self._append_collector_log(
                "Started collector in "
                f"{mode} mode with {config_rel} (pid={proc.pid})"
            )
        return {"status": "started", "mode": mode}

    async def ensure_collector_for_clickhouse(self) -> dict[str, str]:
        """Start clickhouse or dual collector if nothing is listening on :4318."""
        if self.collector_listening():
            mode = self._collector_mode
            if mode in {"local", "newrelic"}:
                raise RuntimeError(
                    f"Collector is running in '{mode}' mode. "
                    "Stop it and start ClickHouse or dual export first."
                )
            return {"status": "ready", "mode": mode or "external"}
        preferred = "dual" if self.new_relic_key_set() else "clickhouse"
        return await self.start_collector(preferred)

    async def wait_for_job(self, *, timeout_sec: float = 180.0) -> int | None:
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            async with self._lock:
                proc = self._job_proc
                inline_name = self._job_name if proc is None else None
            if proc is None and inline_name is None:
                async with self._lock:
                    return self._job_exit_code
            if proc is not None and proc.returncode is not None:
                return proc.returncode
            await asyncio.sleep(0.25)
        raise RuntimeError("Timed out waiting for pipeline job to finish.")

    async def stop_collector(self) -> dict[str, str]:
        async with self._lock:
            proc = self._collector_proc
        if proc is not None and proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
            self._append_collector_log("Collector stopped.")
            return {"status": "stopped", "mode": "managed"}

        # Fallback: stop collector process started outside the UI.
        stopped = await asyncio.to_thread(self._stop_external_collectors)
        if stopped:
            self._append_collector_log("Stopped external collector process.")
            return {"status": "stopped", "mode": "external"}
        return {"status": "noop", "mode": "none"}

    async def start_job(
        self,
        *,
        name: str,
        command: Sequence[str],
        env: dict[str, str] | None = None,
    ) -> dict[str, str]:
        async with self._lock:
            if self._job_proc is not None and self._job_proc.returncode is None:
                active = self._job_name or "unknown"
                raise RuntimeError(
                    f"Another pipeline job is currently running: {active}."
                )
            sinks = self._job_log_sinks(name)
            self._job_logs.clear()
            for sink in sinks:
                if sink is not self._job_logs:
                    sink.clear()
            self._job_exit_code = None
            run_env = os.environ.copy()
            # Force line/stream flushing so child stdout streams to the log
            # buffers in real time instead of being block-buffered until exit.
            run_env["PYTHONUNBUFFERED"] = "1"
            if env:
                run_env.update(env)
            proc = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(self.repo_root),
                env=run_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            self._job_proc = proc
            self._job_name = name
            self._job_task = asyncio.create_task(self._watch_job(proc, sinks))
            self._append_to_sinks(
                sinks,
                f"Started {name}: {' '.join(command)} (pid={proc.pid})"
            )
        return {"status": "started", "job": name}

    async def stop_job(self, expected_name: str | None = None) -> dict[str, str]:
        async with self._lock:
            proc = self._job_proc
            name = self._job_name
        if proc is None or proc.returncode is not None:
            raise RuntimeError("No running pipeline job to stop.")
        if expected_name and name != expected_name:
            raise RuntimeError(
                f"Running job is '{name or 'unknown'}', not '{expected_name}'."
            )
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
        self._append_job_log(f"Stopped job: {name or 'unknown'}")
        return {"status": "stopped", "job": name or "unknown"}

    def _stop_external_collectors(self) -> bool:
        try:
            output = subprocess.check_output(
                ["pgrep", "-f", r"dist/otel-custom/otel-custom"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

        pids: list[int] = []
        for raw in output.splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                pid = int(raw)
            except ValueError:
                continue
            if pid != os.getpid():
                pids.append(pid)

        if not pids:
            return False

        for pid in pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass

        deadline = time.time() + 5.0
        while time.time() < deadline:
            alive = False
            for pid in pids:
                try:
                    os.kill(pid, 0)
                    alive = True
                except OSError:
                    continue
            if not alive:
                return True
            time.sleep(0.1)

        for pid in pids:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        return True

    async def begin_inline_job(self, name: str) -> None:
        async with self._lock:
            if self._job_proc is not None and self._job_proc.returncode is None:
                active = self._job_name or "unknown"
                raise RuntimeError(
                    f"Another pipeline job is currently running: {active}."
                )
            if self._job_name is not None:
                raise RuntimeError(
                    f"Another pipeline job is currently running: {self._job_name}."
                )
            sinks = self._job_log_sinks(name)
            self._job_logs.clear()
            for sink in sinks:
                if sink is not self._job_logs:
                    sink.clear()
            self._job_exit_code = None
            self._job_name = name
            self._append_to_sinks(sinks, f"Started {name}")

    async def end_inline_job(
        self, *, exit_code: int, message: str | None = None
    ) -> None:
        async with self._lock:
            sinks = self._job_log_sinks(self._job_name or "ingest-sample")
            if message:
                self._append_to_sinks(sinks, message)
            self._job_exit_code = exit_code
            self._job_name = None

    def append_inline_log(self, line: str) -> None:
        sinks = self._job_log_sinks(self._job_name or "ingest-sample")
        self._append_to_sinks(sinks, line)

    def status(self) -> dict[str, object]:
        collector_running = (
            self._collector_proc is not None and self._collector_proc.returncode is None
        )
        job_running = self._job_proc is not None and self._job_proc.returncode is None
        if not job_running and self._job_name is not None:
            # Inline job is active.
            job_running = True
        return {
            "collector": {
                "running": collector_running,
                "mode": self._collector_mode,
                "pid": self._collector_proc.pid if collector_running else None,
                "last_exit_code": self._collector_exit_code,
            },
            "job": {
                "running": job_running,
                "name": self._job_name,
                "pid": (
                    self._job_proc.pid
                    if self._job_proc and self._job_proc.returncode is None
                    else None
                ),
                "last_exit_code": self._job_exit_code,
            },
            "signals": {
                "collector_listening_4318": self.collector_listening(),
                "collector_binary_ready": self.collector_binary_ready(),
                "new_relic_key_set": self.new_relic_key_set(),
                "clickhouse_settings_set": self.clickhouse_settings_set(),
                "github_token_set": self.github_token_set(),
                "anthropic_api_key_set": self.anthropic_key_set(),
            },
        }

    def logs(self) -> dict[str, list[str]]:
        return {
            "collector": list(self._collector_logs),
            "job": list(self._job_logs),
            "synthetic": list(self._synthetic_logs),
            "github_poll": list(self._github_poll_logs),
            "ingest": list(self._ingest_logs),
            "gemini": list(self._gemini_logs),
            "anthropic": list(self._anthropic_logs),
        }

    async def clear_logs(self) -> dict[str, str]:
        async with self._lock:
            self._collector_logs.clear()
            self._job_logs.clear()
            self._synthetic_logs.clear()
            self._github_poll_logs.clear()
            self._ingest_logs.clear()
            self._gemini_logs.clear()
            self._anthropic_logs.clear()
        return {"status": "cleared"}
