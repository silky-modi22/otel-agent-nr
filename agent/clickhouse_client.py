"""Read-only ClickHouse queries for the pipeline dashboard."""

from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


def _read_secret_file(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    value = text.strip()
    return value or None


def clickhouse_status(repo_root: Path) -> dict[str, Any]:
    endpoint = os.environ.get("CLICKHOUSE_ENDPOINT", "").strip()
    user = os.environ.get("CLICKHOUSE_USER", "").strip()
    password = os.environ.get("CLICKHOUSE_PASSWORD", "").strip()
    if not endpoint:
        endpoint = _read_secret_file(repo_root / ".clickhouse_endpoint") or ""
    if not user:
        user = _read_secret_file(repo_root / ".clickhouse_user") or ""
    if not password:
        password = _read_secret_file(repo_root / ".clickhouse_password") or ""
    return {
        "configured": bool(endpoint and user and password),
        "endpoint_set": bool(endpoint),
        "user_set": bool(user),
        "password_set": bool(password),
    }


def _resolve_credentials(repo_root: Path) -> tuple[str, str, str]:
    status = clickhouse_status(repo_root)
    if not status["configured"]:
        raise RuntimeError(
            "ClickHouse not configured. Set CLICKHOUSE_* env vars or create "
            ".clickhouse_endpoint, .clickhouse_user, .clickhouse_password."
        )
    endpoint = os.environ.get("CLICKHOUSE_ENDPOINT", "").strip()
    user = os.environ.get("CLICKHOUSE_USER", "").strip()
    password = os.environ.get("CLICKHOUSE_PASSWORD", "").strip()
    if not endpoint:
        endpoint = _read_secret_file(repo_root / ".clickhouse_endpoint") or ""
    if not user:
        user = _read_secret_file(repo_root / ".clickhouse_user") or ""
    if not password:
        password = _read_secret_file(repo_root / ".clickhouse_password") or ""
    return endpoint.rstrip("/"), user, password


def run_query(repo_root: Path, query: str, *, timeout: float = 30.0) -> list[list[Any]]:
    endpoint, user, password = _resolve_credentials(repo_root)
    url = f"{endpoint}/?query={urllib.parse.quote(query)}"
    req = urllib.request.Request(url, method="GET")
    token = f"{user}:{password}".encode("utf-8")
    import base64

    req.add_header("Authorization", "Basic " + base64.b64encode(token).decode("ascii"))
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            body = resp.read().decode("utf-8", errors="replace").strip()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"ClickHouse HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"ClickHouse connection failed: {exc}") from exc

    if not body:
        return []
    rows: list[list[Any]] = []
    for line in body.splitlines():
        if "\t" in line:
            rows.append(line.split("\t"))
        else:
            rows.append([line])
    return rows


def fetch_summary(repo_root: Path) -> dict[str, Any]:
    trace_total = run_query(
        repo_root, "SELECT count() FROM otel.otel_traces FORMAT TabSeparated"
    )
    log_total = run_query(
        repo_root, "SELECT count() FROM otel.otel_logs FORMAT TabSeparated"
    )
    by_service = run_query(
        repo_root,
        "SELECT ServiceName, SpanName, count() "
        "FROM otel.otel_traces "
        "GROUP BY ServiceName, SpanName "
        "ORDER BY count() DESC "
        "LIMIT 15 "
        "FORMAT TabSeparated",
    )
    github_like = run_query(
        repo_root,
        "SELECT count() FROM otel.otel_traces "
        "WHERE ServiceName = 'otel-ai-ingest' "
        "OR SpanName LIKE '%github%' "
        "OR SpanAttributes LIKE '%github%' "
        "FORMAT TabSeparated",
    )
    latest = run_query(
        repo_root,
        "SELECT Timestamp, ServiceName, SpanName "
        "FROM otel.otel_traces "
        "ORDER BY Timestamp DESC "
        "LIMIT 8 "
        "FORMAT TabSeparated",
    )
    return {
        "trace_count": int(trace_total[0][0]) if trace_total else 0,
        "log_count": int(log_total[0][0]) if log_total else 0,
        "github_related_trace_count": int(github_like[0][0]) if github_like else 0,
        "by_service_span": [
            {"service": r[0], "span": r[1], "count": int(r[2])}
            for r in by_service
            if len(r) >= 3
        ],
        "latest_traces": [
            {"timestamp": r[0], "service": r[1], "span": r[2]}
            for r in latest
            if len(r) >= 3
        ],
    }
