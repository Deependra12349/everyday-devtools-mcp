#!/usr/bin/env python3
"""End-to-end test: spawn the server and speak real MCP JSON-RPC to it.

Run:  python tests/test_mcp.py
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def send(proc, obj):
    proc.stdin.write(json.dumps(obj) + "\n")
    proc.stdin.flush()


def recv(proc):
    line = proc.stdout.readline()
    assert line, "server closed stdout unexpectedly"
    return json.loads(line)


def call(proc, req_id, name, arguments):
    send(proc, {"jsonrpc": "2.0", "id": req_id, "method": "tools/call",
                "params": {"name": name, "arguments": arguments}})
    resp = recv(proc)
    assert "result" in resp, f"{name}: no result in {resp}"
    result = resp["result"]
    return result["content"][0]["text"], result.get("isError", False)


def main() -> int:
    proc = subprocess.Popen(
        [sys.executable, "-m", "everyday_devtools_mcp"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        text=True, cwd=ROOT,
    )
    try:
        # handshake
        send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05",
                               "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}}})
        resp = recv(proc)
        assert resp["result"]["serverInfo"]["name"] == "everyday-devtools-mcp", resp
        send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})

        # tool list
        send(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = recv(proc)["result"]["tools"]
        names = [t["name"] for t in tools]
        assert len(names) >= 17, f"expected >=17 tools, got {len(names)}: {names}"
        print(f"tools/list OK: {len(names)} tools")

        checks = [
            ("base64_encode", {"text": "hello"}, "aGVsbG8="),
            ("base64_decode", {"text": "aGVsbG8="}, "hello"),
            ("url_encode", {"text": "a b&c"}, "a%20b%26c"),
            ("hash_text", {"text": "abc", "algorithm": "sha256"},
             "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"),
            ("json_minify", {"text": '{ "a": 1 }'}, '{"a":1}'),
            ("slugify", {"text": "Hello World! 2026"}, "hello-world-2026"),
            ("color_convert", {"value": "#FF0000"}, "rgb(255, 0, 0)"),
            ("color_convert", {"value": "rgb(255, 0, 0)"}, "#FF0000"),
            ("case_convert", {"text": "hello world", "mode": "snake"}, "hello_world"),
            ("timestamp_convert", {"value": "0"}, "1970-01-01 00:00:00"),
        ]
        rid = 10
        for name, args, expect in checks:
            rid += 1
            text, is_err = call(proc, rid, name, args)
            assert not is_err, f"{name} errored: {text}"
            assert expect in text, f"{name}: expected {expect!r} in {text!r}"
            print(f"{name} OK")

        # a few looser checks
        text, _ = call(proc, 99, "uuid_generate", {"count": 3})
        assert len(text.strip().splitlines()) == 3, text
        print("uuid_generate OK")
        text, _ = call(proc, 100, "password_generate", {"length": 20})
        assert len(text.strip()) == 20, text
        print("password_generate OK")
        text, _ = call(proc, 101, "cron_next", {"expression": "0 9 * * 1", "count": 2})
        assert text.count("09:00 UTC") == 2, text
        print("cron_next OK")
        text, _ = call(proc, 102, "regex_test", {"pattern": r"\d+", "text": "a12 b3"})
        assert '"match_count": 2' in text, text
        print("regex_test OK")

        # JWT: build a tiny unsigned-style token by hand
        import base64 as b64
        def seg(obj):
            return b64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()
        token = seg({"alg": "HS256", "typ": "JWT"}) + "." + seg({"sub": "123", "name": "Test"}) + ".sig"
        text, _ = call(proc, 103, "jwt_decode", {"token": token})
        assert '"Test"' in text, text
        print("jwt_decode OK")

        # error path must come back as isError, not a crash
        text, is_err = call(proc, 104, "base64_decode", {"text": "!!!not-base64!!!"})
        assert is_err, "bad base64 should be an error result"
        print("error handling OK")

        print("\nALL TESTS PASSED")
        return 0
    finally:
        proc.stdin.close()
        proc.terminate()


if __name__ == "__main__":
    sys.exit(main())
