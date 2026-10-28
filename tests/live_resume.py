"""Opt-in interrupted-upload/download test with a fresh MCP process on resume."""

import argparse
import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import uuid

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@asynccontextmanager
async def session(env):
    params = StdioServerParameters(command=sys.executable, args=["-m", "aigoodbaiduyun"], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as client:
            await client.initialize()
            yield client


async def call(client, name, **args):
    result = await client.call_tool(name, args)
    if result.isError:
        raise RuntimeError(f"{name}: {result.content}")
    return result.structuredContent or json.loads(result.content[0].text)


async def wait(client, job_id, timeout=180):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        job = await call(client, "task_status", job_id=job_id)
        if job["state"] in {"succeeded", "failed", "cancelled"}:
            if job["state"] != "succeeded":
                raise RuntimeError(json.dumps(job, ensure_ascii=False))
            return job
        await asyncio.sleep(1)
    raise TimeoutError("Transfer did not finish")


async def check(root, backend):
    run = root.expanduser().resolve() / ("resume-" + uuid.uuid4().hex[:12])
    run.mkdir(parents=True, mode=0o700)
    source = run / "aigoodbaiduyun-resume.bin"
    source.write_bytes(os.urandom(16 * 1024 * 1024))
    expected = hashlib.sha256(source.read_bytes()).hexdigest()
    state = run / "private-state"
    env = dict(os.environ, AIGOODBAIDUYUN_STATE_DIR=str(state), AIGOODBAIDUYUN_RESUME_BIN=str(backend.resolve()))
    remote = "/aigoodbaiduyun-resume-test/" + run.name
    evidence = {"bytes": source.stat().st_size, "sha256": expected, "passed": False, "remote": remote + "/" + source.name}
    try:
        async with session(env) as client:
            up = await call(client, "upload", local=str(source), remote_dir=remote, rate_limit_bps=512 * 1024)
            up_id = up["job_id"]
            checkpoint = state / up_id / "pcs_uploading.json"
            completed = 0
            until = time.monotonic() + 120
            while time.monotonic() < until:
                await asyncio.sleep(1)
                job = await call(client, "task_status", job_id=up_id)
                if job["state"] in {"failed", "succeeded"}:
                    raise RuntimeError("Upload ended before interruption: " + json.dumps(job, ensure_ascii=False))
                try:
                    data = json.loads(checkpoint.read_text())
                    blocks = data["upload_state"][0]["state"]["block_list"]
                    completed = sum(b["range"].get("end", 0) - b["range"].get("begin", 0) for b in blocks if b.get("checksum"))
                except (OSError, ValueError, KeyError, IndexError, TypeError):
                    continue
                if 0 < completed < source.stat().st_size:
                    break
            assert completed > 0, "No uploaded block checkpoint found"
            paused = await call(client, "pause_transfer", job_id=up_id)
            assert paused["state"] == "paused"
            evidence["upload_checkpoint_bytes"] = completed
            print(json.dumps({"phase": "upload_paused", "completed_bytes": completed}), flush=True)
        async with session(env) as client:
            assert (await call(client, "task_status", job_id=up_id))["state"] == "paused"
            await call(client, "resume_transfer", job_id=up_id, rate_limit_bps=0)
            finished = await wait(client, up_id)
            evidence["upload_resumed_bytes"] = finished.get("resumed_bytes", 0)
            assert evidence["upload_resumed_bytes"] >= completed
            dest = run / "download"
            down = await call(client, "download", remote=evidence["remote"], local_dir=str(dest), expected_sha256=expected, rate_limit_bps=512 * 1024)
            down_id = down["job_id"]
            until = time.monotonic() + 120
            sidecar = Path(str(dest / source.name) + ".BaiduPCS-Go-downloading")
            while time.monotonic() < until:
                await asyncio.sleep(1)
                job = await call(client, "task_status", job_id=down_id)
                if job["state"] in {"failed", "succeeded"}:
                    raise RuntimeError("Download ended before interruption: " + json.dumps(job, ensure_ascii=False))
                if sidecar.exists() and sidecar.stat().st_size and job.get("progress"):
                    await asyncio.sleep(2)
                    break
            assert sidecar.exists() and sidecar.stat().st_size > 0
            await call(client, "pause_transfer", job_id=down_id)
            evidence["download_checkpoint_bytes"] = sidecar.stat().st_size
            evidence["partial_local_file_bytes"] = (dest / source.name).stat().st_size
            evidence["download_before_pause"] = job.get("progress")
            print(json.dumps({"phase": "download_paused", "checkpoint_bytes": sidecar.stat().st_size}), flush=True)
        async with session(env) as client:
            assert (await call(client, "task_status", job_id=down_id))["state"] == "paused"
            await call(client, "resume_transfer", job_id=down_id, rate_limit_bps=0)
            finished = await wait(client, down_id)
            evidence["download_resumed_bytes"] = finished.get("resumed_bytes", 0)
            assert evidence["download_resumed_bytes"] > 0, "Downloader did not report using the checkpoint"
            evidence["download_sha256_match"] = finished.get("sha256_match")
            evidence["checkpoint_removed_after_success"] = not sidecar.exists()
            evidence["independent_hash_match"] = hashlib.sha256((dest / source.name).read_bytes()).hexdigest() == expected
            evidence["passed"] = all([evidence["download_sha256_match"], evidence["checkpoint_removed_after_success"], evidence["independent_hash_match"], evidence["upload_resumed_bytes"] > 0, evidence["download_resumed_bytes"] > 0])
            assert evidence["passed"]
    finally:
        (run / "receipt.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"receipt": str(run / "receipt.json"), **evidence}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-dir", required=True, type=Path)
    parser.add_argument("--resume-backend", required=True, type=Path)
    args = parser.parse_args()
    asyncio.run(check(args.local_dir, args.resume_backend))
