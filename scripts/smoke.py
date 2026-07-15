"""End-to-end smoke test against a running stack (docker compose up).

Usage: uv run python scripts/smoke.py [BASE_URL]
Reads UI_PASSWORD and MCP_API_KEY from the environment (.env values).
"""

import os
import pathlib
import sys

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
UI_AUTH = ("admin", os.environ["UI_PASSWORD"])
MCP_HEADERS = {
    "Authorization": f"Bearer {os.environ['MCP_API_KEY']}",
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


def rpc(method: str, params: dict | None = None) -> dict:
    return {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}


def main() -> None:
    with httpx.Client(base_url=BASE, timeout=60) as c:
        assert c.get("/healthz").json()["status"] == "ok", "healthz failed"
        print("healthz ok")

        doc = pathlib.Path("test_corpus/meridian/docs/meridian-aml-policy.md")
        r = c.post(
            "/api/documents", auth=UI_AUTH,
            files={"file": (doc.name, doc.read_bytes(), "text/markdown")},
            data={"tags": "compliance"},
        )
        r.raise_for_status()
        print(f"upload ok: {r.json()['outcome']}")

        r = c.post("/mcp", headers=MCP_HEADERS, json=rpc(
            "tools/call",
            {"name": "search", "arguments": {"query": "tier-2 transfer cap"}},
        ))
        r.raise_for_status()
        body = r.text
        assert "aml-policy.md" in body, f"expected aml-policy.md in results: {body[:500]}"
        print("mcp search ok — found aml-policy.md")

        r = c.post("/mcp", json=rpc("tools/list"))  # no auth header
        assert r.status_code == 401, "MCP endpoint must reject unauthenticated calls"
        print("mcp auth ok — 401 without token")

    print("SMOKE PASSED")


if __name__ == "__main__":
    main()
