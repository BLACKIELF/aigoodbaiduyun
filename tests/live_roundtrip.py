"""Opt-in live check. Creates one small remote file; never deletes user files."""

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import uuid

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def check(local_dir: Path, remote_parent: str):
    run_id = uuid.uuid4().hex[:12]
    run = local_dir.expanduser().resolve() / f"mcp-roundtrip-{run_id}"
    run.mkdir(parents=True, mode=0o700)
    source = run / "aigoodbaiduyun-中文 空格.txt"
    source.write_text("aigoodbaiduyun MCP roundtrip\n" + os.urandom(32768).hex() + "\n")
    expected = hashlib.sha256(source.read_bytes()).hexdigest()
    remote = remote_parent.rstrip("/") + "/" + run_id
    dest = run / "download"
    evidence = {"source": str(source), "remote": remote + "/" + source.name, "bytes": source.stat().st_size, "expected_sha256": expected, "passed": False}
    params = StdioServerParameters(command=sys.executable, args=["-m", "aigoodbaiduyun"], env=dict(os.environ))
    try:
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as client:
                evidence["mcp_server"] = (await client.initialize()).serverInfo.name
                evidence["tools"] = [tool.name for tool in (await client.list_tools()).tools]

                async def call(name, arguments):
                    result = await client.call_tool(name, arguments)
                    if result.isError:
                        raise RuntimeError(f"{name}: {result.content}")
                    return result.structuredContent or json.loads(result.content[0].text)

                async def wait_job(job_id):
                    until = time.monotonic() + 150
                    while time.monotonic() < until:
                        result = await call("task_status", {"job_id": job_id})
                        if result["state"] in {"succeeded", "failed", "cancelled"}:
                            if result["state"] != "succeeded":
                                raise RuntimeError(json.dumps(result, ensure_ascii=False))
                            return result
                        await asyncio.sleep(1)
                    await call("cancel_transfer", {"job_id": job_id})
                    raise TimeoutError("Transfer timed out")

                evidence["remote_verified"] = (await call("status", {}))["remote_verified"]
                assert evidence["remote_verified"]
                evidence["login_reused"] = (await call("login_qr", {}))["state"] == "already_logged_in"
                up = await wait_job((await call("upload", {"local": str(source), "remote_dir": remote}))["job_id"])
                evidence["upload"] = {key: up.get(key) for key in ["state", "sha256", "bytes"]}
                evidence["listed"] = source.name in (await call("list_files", {"path": remote}))["output"]
                assert evidence["listed"]
                down = await wait_job((await call("download", {"remote": evidence["remote"], "local_dir": str(dest), "expected_sha256": expected}))["job_id"])
                evidence["download"] = {key: down.get(key) for key in ["state", "sha256", "bytes", "sha256_match"]}
                evidence["passed"] = hashlib.sha256((dest / source.name).read_bytes()).hexdigest() == expected
                assert evidence["passed"]
    finally:
        (run / "receipt.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-dir", required=True, type=Path)
    parser.add_argument("--remote-dir", required=True)
    args = parser.parse_args()
    asyncio.run(check(args.local_dir, args.remote_dir))
