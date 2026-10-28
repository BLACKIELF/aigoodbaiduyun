# Changelog

## 1029v2 (Python package 0.3.0) — 2026-10-29

- New verified file management: folder creation, copy, move, rename and exact-path metadata.
- Explicit destination paths and refusal to overwrite existing targets.
- File-operation locks prevent new transfers from racing with path changes.
- Live checks cover specified download directories, Chinese/space-containing names, idempotent folder creation, conflict refusal, copied source retention, and moved-file SHA-256 verification.

## 1029v1 (Python package 0.2.0) — 2026-10-29

- QR login through a separate, local BaiduPCS-Go QR helper.
- Ten MCP tools for account checks, listing, upload/download, progress, pause/resume and cancellation.
- Atomic local task persistence, cross-process locks, duplicate and overlapping destination checks.
- Independent task configurations with restrictive permissions; normal stop removes temporary credential copies.
- Patched BaiduPCS-Go v4.0.2 backend reuses completed upload blocks, retains merge checksums and reports resumed byte counts.
- Download resume validates remote file identity; individual downloads check available disk space.
- SHA-256 verification, bandwidth limits, source/account change checks and damaged checkpoint detection.
- Real macOS tests include upload/download, Unicode and space-containing names, and interrupted 16 MiB transfers across fresh MCP processes.

The original upstream executables are retained. Windows, GB-scale and directory resume have not been accepted through live tests.
