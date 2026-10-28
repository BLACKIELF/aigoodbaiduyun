# aigoodbaiduyun

1029v1 · Python package 0.2.0

百度网盘 MCP：扫码登录、上传下载、暂停续传，以及跨会话保存的传输任务。

基于 [BaiduPCS-Go](https://github.com/qjfoidnh/BaiduPCS-Go) 和支持扫码的
[BaiduPCS-Go-HTTP](https://github.com/aki66938/BaiduPCS-Go-HTTP)。使用本机登录状态；
不需要把 Cookie、BDUSS 或密码交给模型。只通过 stdio 提供 MCP，不开启 HTTP 服务。

## 安装

当前支持 macOS / Linux，需要 Python 3.11+，以及以下两个外部程序：

1. [BaiduPCS-Go v4.0.2](https://github.com/qjfoidnh/BaiduPCS-Go/releases/tag/v4.0.2)：上传下载主程序。
2. [扫码分支 v1.3.2](https://github.com/aki66938/BaiduPCS-Go-HTTP/releases/tag/v1.3.2)：仅用于扫码登录。

分别下载适合系统的程序，设置可执行权限。把主程序放入 PATH，名称为 `BaiduPCS-Go`；
把扫码版本另存为 `baidupcs-qr`，避免覆盖主程序。也可以在 MCP 配置中指定完整路径。
扫码分支的发布编号是 v1.3.2，程序自身显示 v4.0.0-stable。

```sh
git clone https://github.com/BLACKIELF/aigoodbaiduyun.git
cd aigoodbaiduyun
uv sync
uv run aigoodbaiduyun login
uv run aigoodbaiduyun doctor
```

`login` 会显示二维码，用手机百度网盘 App 扫描并确认。`doctor` 会向百度查询容量，
验证当前登录，而不只是检查配置文件是否存在。也可以在独立虚拟环境中运行 `pip install .`。

## 上传断点续传

上游 v4.0.2 已关闭上传断点恢复，直接重跑上传会重新传输文件。本项目提供独立、默认不替换原程序的
修复版本：恢复保存的分片状态，并在合并请求中带回已完成分片的校验值。

安装 Go 1.23+ 和 `patch` 后构建：

```sh
python3 scripts/build_resume_backend.py --build-dir /absolute/path/to/baidupcs-resume
```

构建脚本校验固定上游源码包的 SHA-256，应用补丁，运行分片回归测试，再编译可执行文件。
在 MCP 配置中加入 `AIGOODBAIDUYUN_RESUME_BIN`，指向生成的 `BaiduPCS-Go-resume`。
未配置此后端时，普通上传仍可用，但 MCP 会明确拒绝上传分片恢复；下载续传仍由上游支持。

恢复任务沿用原来的上传会话和已完成分片，不保证百度长期保留已上传分片。
服务端会话过期时会报告失败。恢复前会核对账号、文件大小和高精度修改时间；请保持源文件不变。
分片保存间隔内尚未记录的数据可能需要重传。
下载恢复前会核对远端文件大小、标识、校验值和修改时间；单文件下载也会检查目标磁盘空间。

## 接入 MCP 客户端

将下面的路径替换为实际安装路径。配置属于通用 `mcpServers` 格式，按客户端要求放入对应配置文件。

```json
{
  "mcpServers": {
    "aigoodbaiduyun": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/aigoodbaiduyun", "run", "--no-sync", "aigoodbaiduyun"],
      "env": {
        "AIGOODBAIDUYUN_PCS_BIN": "/absolute/path/to/BaiduPCS-Go",
        "AIGOODBAIDUYUN_QR_BIN": "/absolute/path/to/baidupcs-qr",
        "AIGOODBAIDUYUN_RESUME_BIN": "/absolute/path/to/baidupcs-resume/BaiduPCS-Go-resume",
        "AIGOODBAIDUYUN_STATE_DIR": "/absolute/path/to/private-transfer-state"
      }
    }
  }
}
```

Codex 项目配置可使用以下 TOML：

```toml
[mcp_servers.aigoodbaiduyun]
command = "uv"
args = ["--directory", "/absolute/path/to/aigoodbaiduyun", "run", "--no-sync", "aigoodbaiduyun"]

[mcp_servers.aigoodbaiduyun.env]
AIGOODBAIDUYUN_PCS_BIN = "/absolute/path/to/BaiduPCS-Go"
AIGOODBAIDUYUN_QR_BIN = "/absolute/path/to/baidupcs-qr"
AIGOODBAIDUYUN_RESUME_BIN = "/absolute/path/to/baidupcs-resume/BaiduPCS-Go-resume"
AIGOODBAIDUYUN_STATE_DIR = "/absolute/path/to/private-transfer-state"
```

两个程序默认共用 `~/.config/BaiduPCS-Go/pcs_config.json`。非默认位置可通过
`BAIDUPCS_GO_CONFIG_DIR` 指定。配置包含凭证，保存在本机，不应提交到 Git。

## 工具

| 工具 | 用途 |
| --- | --- |
| `status` | 检查本地登录，并向百度验证账号和容量 |
| `login_qr` | macOS 打开扫码终端；其他系统提供本机登录命令 |
| `list_files` | 列出一个网盘目录 |
| `upload` | 上传一个本地文件或文件夹，返回任务编号 |
| `download` | 下载一个网盘文件或文件夹，返回任务编号 |
| `task_status` | 查看进度、结果、文件 SHA-256 |
| `pause_transfer` | 暂停任务，保留断点 |
| `resume_transfer` | 恢复暂停、失败或停止的任务 |
| `list_transfers` | 分页查看已保存的任务 |
| `cancel_transfer` | 停止传输，保留部分文件和断点 |

上传下载在后台执行，创建任务不代表传输成功。使用 `task_status` 查看百分比、当前文件速度、
预计剩余时间和状态。MCP 正常关闭会暂停任务；下次用 `list_transfers` 找到任务，再调用
`resume_transfer`。不会自动恢复任务或自动传输用户文件。

任务保存在 `~/.local/state/aigoodbaiduyun`，可通过 `AIGOODBAIDUYUN_STATE_DIR` 更改。
跨进程锁阻止同一任务同时执行；重复提交返回已有任务，重叠目标会报错。
最多同时运行两个任务，每个任务默认单线程。`rate_limit_bps` 可设置限速，0 表示不限速。
`list_transfers` 默认每页 20 项，最多 100 项，较早的任务仍保留。

正常关闭后的任务及断点可跨 MCP 进程恢复。若强制杀死 MCP，正在运行的底层传输可能继续一段时间；
其进程锁会阻止重复启动，底层进程退出后任务可恢复。断点文件损坏时保留原件并报告错误，
不会悄悄从头上传。

上传和下载均跳过已存在的同名文件。成功状态表示 CLI 完成了本次操作，可能包含跳过的文件。
上传固定使用普通上传，避开上游秒传在目标目录尚不存在时的报错。
单文件会计算本地 SHA-256；下载时提供 `expected_sha256` 可验证与源文件是否一致。
文件夹只报告 CLI 结果，不声称已校验每个文件。网盘路径必须以 `/` 开头，本地路径必须为绝对路径。

例如：先上传 `/Users/me/Documents/example.pdf` 到 `/Documents`，待任务成功后，
把返回的 SHA-256 传入 `download` 的 `expected_sha256`，下载至新的空目录。

## 验证

```sh
uv run python -m unittest discover -s tests -v
```

离线测试涵盖 MCP 握手、工具调用、凭证脱敏、路径约束、错误识别、任务取消和哈希校验。
可选择运行真实账号测试，需指定测试目录；会保留一个小文件作为验收记录：

```sh
uv run python tests/live_roundtrip.py --local-dir /absolute/path/to/test-output --remote-dir /aigoodbaiduyun-test
```

2026-10-29 在 macOS Apple Silicon 上使用真实账号验证：

- 原始 CLI：约 128 KB 文件上传、下载和 SHA-256 一致。
- MCP：中文及空格文件名，约 64 KB 上传、下载和 SHA-256 一致。
- 上传续传：16 MiB 文件，完成 4 MiB 后暂停，关闭 MCP，再启动新进程恢复；已完成分片被复用。
- 下载续传：同一 16 MiB 文件，中途暂停后跨进程恢复；后端报告从已保存的字节位置继续，最终 SHA-256 一致。
- 重新从固定上游源码构建补丁后端，运行针对已完成分片的回归测试。

复验断点续传（会创建并保留一个 16 MiB 测试文件）：

```sh
uv run python tests/live_resume.py --local-dir /absolute/path/to/test-output --resume-backend /absolute/path/to/BaiduPCS-Go-resume
```

这些结果不代表 GB 级大文件、目录批量传输、长期断网、登录过期和其他系统的实网验收。
百度侧接口、账号状态和限速可能改变。

## 本地数据

MCP 返回值和任务记录不包含 Cookie、BDUSS 等登录凭证；日志中的凭证及链接会脱敏。
每个运行中的任务使用权限为 600 的独立账号配置，正常停止后删除该临时副本，恢复时再从主配置读取。
任务记录和断点仅存在本地，状态目录权限为 700。不要把状态目录、主配置或测试账号资料提交到 Git。
公开测试使用虚构账号；实网测试结果只记录能力和验收范围。

## 许可

本项目采用 [MIT](LICENSE) 许可。上游工具的许可、版本和来源见 [THIRD_PARTY.md](THIRD_PARTY.md)。
这是社区项目，与百度官方无关联。
