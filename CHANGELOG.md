# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 与 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.0.0] - 2026-10-28

### Added

- 内置 3303 条常用成语词库（只读 JSON，随包分发）
- Tools：`draw_idiom`、`idiom_detail`、`search_idiom`、`update_status`、`add_note`、`progress`、`reset_word`
- Resources：`chengyu://{word}`、`chengyu://stats`
- Prompts：`learn_idiom`、`quiz_me`
- SQLite 学习记录，默认 `~/.chengyu-mcp/idiom_progress.db`，可用 `CHENGYU_MCP_DB` 覆盖
- 端到端冒烟测试与 GitHub Actions CI（Linux/Windows × Python 3.10/3.12）

### Changed

- 掌握状态改由 AI 依据对话判断，服务端不再内置测验卷与自动判分
