# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 与 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.0.0] - 2026-10-29

### Added

- 内置 3303 条常用成语词库（只读 JSON，随包分发）
- Tools：`draw_idiom`、`idiom_detail`、`search_idiom`、`update_status`、`add_note`、`progress`、`reset_word`
- Resources：`chengyu://{word}`、`chengyu://stats`
- Prompts：`learn_idiom`、`quiz_me`
- SQLite 学习记录，默认 `~/.chengyu-coach/idiom_progress.db`，可用 `CHENGYU_COACH_DB` 覆盖
- 端到端冒烟测试与 GitHub Actions CI（Linux/Windows × Python 3.10/3.12）
- `server.json`：官方 MCP Registry 的服务器元数据
- `.github/workflows/release.yml`：推送 `v*` 标签时自动构建并发布到 PyPI（OIDC Trusted Publishing），并校验标签与版本号一致

### Changed

- 掌握状态改由 AI 依据对话判断，服务端不再内置测验卷与自动判分
- `LICENSE` 换成 SPDX 官方 MIT 文本（措辞不变，仅换行与来源不同）
- `pyproject.toml` 改用 PEP 639 的 `license = "MIT"` 与 `license-files`

### Fixed

- Windows 英文区（cp1252）下启动横幅输出为 `\uXXXX` 乱码、冒烟测试打印中文时抛 `UnicodeEncodeError`：两处都显式切到 UTF-8
