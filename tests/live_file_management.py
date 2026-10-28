"""Opt-in mkdir/copy/rename/move test using newly created test files only."""

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import uuid

from live_resume import call, session, wait


async def check(root):
    tag = uuid.uuid4().hex[:12]
    local = root.expanduser().resolve() / ("file-management-" + tag)
    local.mkdir(parents=True)
    source = local / "原始 测试.txt"
    source.write_text("aigoodbaiduyun file management " + tag + "\n")
    remote = "/aigoodbaiduyun-management-test/" + tag
    receipt = {"remote_test_directory": remote, "passed": False}
    try:
        async with session(dict(os.environ)) as client:
            created = await call(client, "mkdir", path=remote)
            assert created["ok"] and created["created"]
            receipt["mkdir"] = True
            assert not (await call(client, "mkdir", path=remote))["created"]
            receipt["mkdir_idempotent"] = True
            await wait(client, (await call(client, "upload", local=str(source), remote_dir=remote))["job_id"])
            original = remote + "/" + source.name
            duplicate = remote + "/复制.txt"
            assert (await call(client, "copy", source=original, destination=duplicate))["ok"]
            receipt["copy"] = True
            conflict = await client.call_tool("copy", {"source": original, "destination": duplicate})
            assert conflict.isError
            receipt["existing_target_refused"] = True
            assert (await call(client, "rename", path=duplicate, new_name="重命名 空格.txt"))["ok"]
            receipt["rename"] = True
            assert (await call(client, "mkdir", path=remote + "/子文件夹"))["ok"]
            moved = remote + "/子文件夹/重命名 空格.txt"
            assert (await call(client, "move", source=remote + "/重命名 空格.txt", destination=moved))["ok"]
            receipt["move"] = True
            assert (await call(client, "file_info", path=original))["exists"]
            checksum = hashlib.sha256(source.read_bytes()).hexdigest()
            downloaded = await wait(client, (await call(client, "download", remote=moved, local_dir=str(local / "指定 下载目录"), expected_sha256=checksum))["job_id"])
            receipt["specified_download_directory"] = True
            receipt["sha256_match"] = downloaded["sha256_match"]
            receipt["passed"] = True
    finally:
        (local / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"receipt": str(local / "receipt.json"), **receipt}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-dir", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(check(args.local_dir))
