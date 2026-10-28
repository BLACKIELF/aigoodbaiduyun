"""Offline contract tests; no account or network required."""

import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from aigoodbaiduyun import server


FAKE = '''
import os, sys, time
from pathlib import Path
args = sys.argv[1:]
if args[0] == "quota":
    print("用户名: test, 总空间: 1TB, 已用空间: 1KB")
elif args[0] == "ls":
    print("test.txt")
elif args[0] == "meta":
    print("文件大小 12, 12B")
    print("fs_id 123")
    print("修改日期 2026-10-29 00:00:00")
elif args[0] == "upload":
    assert "--norapid" in args, "new remote folders need ordinary upload"
    if "zero-error" in args[-2]:
        print("上传失败: BDUSS=secret-test-value-123456")
    elif "slow" in args[-2]:
        time.sleep(60)
    else:
        print("上传文件成功")
        print("上传结束")
elif args[0] == "download":
    folder = Path(args[args.index("--saveto")+1])
    (folder / Path(args[-1]).name).write_bytes(b"test payload")
    print("下载完成")
    print("下载结束")
'''


class ServerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bin = self.root / "fake-cli"
        self.bin.write_text(f"#!{sys.executable}\n" + FAKE)
        self.bin.chmod(0o700)
        self.config = self.root / "config"
        self.config.mkdir()
        (self.config / "pcs_config.json").write_text(json.dumps({
            "baidu_active_uid": 123,
            "baidu_user_list": [{"uid": 123, "bduss": "secret-test-value-123456"}],
            "savedir": str(self.root / "downloads"),
        }))
        self.env = patch.dict(os.environ, {"AIGOODBAIDUYUN_PCS_BIN": str(self.bin), "AIGOODBAIDUYUN_QR_BIN": str(self.bin), "AIGOODBAIDUYUN_RESUME_BIN": str(self.bin), "AIGOODBAIDUYUN_STATE_DIR": str(self.root / "state"), "BAIDUPCS_GO_CONFIG_DIR": str(self.config)})
        self.env.start()
        server.transfers = server.Transfers()

    async def asyncTearDown(self):
        await server.transfers.close()
        self.env.stop()
        self.temp.cleanup()

    async def finished(self, job):
        await asyncio.wait_for(server.transfers.tasks[job["job_id"]], 5)
        return await server.task_status(job["job_id"])

    def test_path_boundaries(self):
        self.assertEqual(server.remote_path("/中文 空格/file.txt"), "/中文 空格/file.txt")
        for path in ["--help", "/../secret", "/folder/*", "/file\nwho"]:
            with self.assertRaises(ValueError):
                server.remote_path(path)
        with self.assertRaises(ValueError):
            server.remote_path("/", allow_root=False)
        with self.assertRaises(ValueError):
            server.local_path("relative/file")

    def test_redaction(self):
        value = server.redact("value secret-test-value-123456\nBDUSS=another-token\nhttps://example.test/?token=x")
        self.assertNotIn("secret-test", value)
        self.assertNotIn("another-token", value)
        self.assertNotIn("https://", value)

    def test_numeric_progress(self):
        result = server.transfer_progress("4.00MB", "16.00MB", "512.00KB")
        self.assertEqual(result["percent"], 25.0)
        self.assertEqual(result["seconds_remaining"], 24)

    async def test_status_and_reuse_login(self):
        self.assertTrue((await server.status())["remote_verified"])
        self.assertEqual((await server.login_qr())["state"], "already_logged_in")

    async def test_upload_unicode_path_and_checksum(self):
        source = self.root / "中文 空格.txt"
        source.write_bytes(b"test payload")
        result = await self.finished(await server.upload(str(source), "/test"))
        self.assertEqual(result["state"], "succeeded")
        self.assertEqual(result["sha256"], hashlib.sha256(source.read_bytes()).hexdigest())

    async def test_zero_exit_failure_is_not_success(self):
        source = self.root / "zero-error.txt"
        source.write_bytes(b"x")
        result = await self.finished(await server.upload(str(source), "/test"))
        self.assertEqual(result["state"], "failed")
        self.assertNotIn("secret-test-value", json.dumps(result))

    async def test_download_checksum_and_mismatch(self):
        expected = hashlib.sha256(b"test payload").hexdigest()
        ok = await self.finished(await server.download("/test.txt", str(self.root / "ok"), expected))
        self.assertEqual(ok["state"], "succeeded")
        self.assertTrue(ok["sha256_match"])
        bad = await self.finished(await server.download("/test.txt", str(self.root / "bad"), "0"*64))
        self.assertEqual(bad["state"], "failed")
        self.assertFalse(bad["sha256_match"])

    async def test_cancel_running_process(self):
        source = self.root / "slow.txt"
        source.write_bytes(b"x")
        job = await server.upload(str(source), "/test")
        await asyncio.sleep(0.1)
        result = await server.cancel_transfer(job["job_id"])
        self.assertEqual(result["state"], "cancelled")
        self.assertTrue(server.transfers.tasks[job["job_id"]].done())

    async def test_stdio_handshake_tool_call_and_schema(self):
        params = StdioServerParameters(command=sys.executable, args=["-m", "aigoodbaiduyun"], env=dict(os.environ))
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as client:
                initialized = await client.initialize()
                self.assertEqual(initialized.serverInfo.name, "aigoodbaiduyun")
                tools = await client.list_tools()
                names = {tool.name for tool in tools.tools}
                self.assertEqual(names, {"status", "login_qr", "list_files", "upload", "download", "task_status", "cancel_transfer", "pause_transfer", "resume_transfer", "list_transfers"})
                result = await client.call_tool("status", {})
                self.assertFalse(result.isError)
                self.assertTrue(result.structuredContent["remote_verified"])
                invalid = await client.call_tool("download", {"remote": "--help"})
                self.assertTrue(invalid.isError)

    async def test_persistence_resume_source_change_and_private_config(self):
        source = self.root / "slow.txt"
        source.write_bytes(b"x")
        job = await server.upload(str(source), "/persist")
        await asyncio.sleep(0.1)
        folder = server.transfers.folder(job["job_id"])
        self.assertEqual((folder / "pcs_config.json").stat().st_mode & 0o777, 0o600)
        await server.pause_transfer(job["job_id"])
        self.assertEqual((folder / "record.json").stat().st_mode & 0o777, 0o600)
        self.assertNotIn("secret-test-value", (folder / "record.json").read_text())
        self.assertFalse((folder / "pcs_config.json").exists())
        server.transfers = server.Transfers()
        self.assertEqual((await server.task_status(job["job_id"]))["state"], "paused")
        resumed = await server.resume_transfer(job["job_id"])
        self.assertEqual(resumed["attempt"], 2)
        await asyncio.sleep(0.1)
        await server.pause_transfer(job["job_id"])
        source.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "source changed"):
            await server.resume_transfer(job["job_id"])

    async def test_duplicate_job_and_cross_process_lock(self):
        source = self.root / "slow.txt"
        source.write_bytes(b"x")
        first = await server.upload(str(source), "/duplicate")
        again = await server.upload(str(source), "/duplicate")
        self.assertEqual(first["job_id"], again["job_id"])
        other = server.Transfers()
        self.assertIn(other.get(first["job_id"])["state"], {"queued", "running"})
        with self.assertRaisesRegex(ValueError, "already running"):
            other.activate(other.get(first["job_id"]))

    async def test_account_change_corrupt_checkpoint_and_overlap(self):
        source = self.root / "slow.txt"
        source.write_bytes(b"x")
        job = await server.upload(str(source), "/guard")
        await asyncio.sleep(0.1)
        await server.pause_transfer(job["job_id"])
        other = self.root / "second" / "slow.txt"
        other.parent.mkdir()
        other.write_bytes(b"second")
        with self.assertRaisesRegex(ValueError, "owns this destination"):
            await server.upload(str(other), "/guard")
        checkpoint = server.transfers.folder(job["job_id"]) / "pcs_uploading.json"
        checkpoint.write_text('{"upload_state":')
        with self.assertRaisesRegex(ValueError, "checkpoint is damaged"):
            await server.resume_transfer(job["job_id"])
        checkpoint.unlink()
        config = self.config / "pcs_config.json"
        data = json.loads(config.read_text())
        data.update(baidu_active_uid=456, baidu_user_list=[{"uid":456}])
        config.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "active account differs"):
            await server.resume_transfer(job["job_id"])

    async def test_stale_record_recovers_paused(self):
        job_id = "a" * 32
        folder = server.transfers.folder(job_id)
        folder.mkdir()
        (folder / "record.json").write_text(json.dumps({"job_id":job_id,"kind":"download","local":str(self.root/'out'),"state":"running","started_at":1}))
        other = server.Transfers()
        self.assertEqual(other.get(job_id)["state"], "paused")


if __name__ == "__main__":
    unittest.main()
