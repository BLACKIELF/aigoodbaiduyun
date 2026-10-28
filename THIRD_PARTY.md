# Third-party software

aigoodbaiduyun is an independent MCP adapter. It does not bundle BaiduPCS-Go
binaries or login credentials. The optional patch contains excerpts of upstream
source and is distributed under Apache-2.0, with its full license in
`patches/LICENSE-Apache-2.0.txt`. The Python adapter is MIT licensed.

| Component | Purpose | Upstream license | Verified version |
| --- | --- | --- | --- |
| [qjfoidnh/BaiduPCS-Go](https://github.com/qjfoidnh/BaiduPCS-Go) | File operations | Apache-2.0 | v4.0.2 |
| [aki66938/BaiduPCS-Go-HTTP](https://github.com/aki66938/BaiduPCS-Go-HTTP) | QR login, via its CLI only | Apache-2.0 | release v1.3.2; binary reports v4.0.0-stable |
| [modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk) | MCP transport and schemas | MIT | 1.30.0 |

Install the external CLIs from their upstream releases and retain their license
notices. The QR fork is a smaller community project; review it before trusting
it with an account. This project is not affiliated with or endorsed by Baidu.

## Resume patch

The patch targets qjfoidnh/BaiduPCS-Go v4.0.2 at commit
`225bdd3b6cb298601c4d5ef7104c3e08cd1d692d`. Modified files are listed in the patch.
It restores reading saved upload blocks, includes saved block checksums in the
merge request, and exposes a credential-free resumed-byte count. Resume behavior
is enabled only with `AIGOODBAIDUYUN_RESUME=1`. The original CLI is not replaced.
