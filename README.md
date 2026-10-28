# chengyu-coach-mcp

<!-- mcp-name: io.github.FlowerOfFire/chengyu-coach-mcp -->

成语学习 MCP 服务器（Python，`mcp` SDK v2 的 `MCPServer`，stdio 传输）。内置 3303 条常用成语，学习进度存在本地 SQLite，让任意 MCP 客户端（Qoder / Claude Desktop / Cursor 等）帮你每天抽几个成语学，并根据聊天表现自动记录掌握程度。

- **抽词**：优先抽没抽过的；一轮抽完后按"抽得最少 + 最久没抽"轮转；默认跳过最近 20 条和已掌握的
- **查询**：每个成语抽中了几次、当前状态、备注
- **记录**：掌握状态 + 每词自由备注，由 AI 根据对话自行判断写入
- **不内置测验卷**：考不考、怎么考由客户端 AI 决定，服务端只负责抽词和记录

掌握状态：`learning`（还不熟）→ `reviewing`（基本会但不稳）→ `mastered`（能熟练解释和造句）。

## 安装

```bash
pip install chengyu-coach-mcp        # 发布到 PyPI 后
# 或使用 uv
uvx chengyu-coach-mcp
```

从源码安装：

```bash
git clone <repo-url> chengyu-coach-mcp
cd chengyu-coach-mcp
python -m venv .venv
.venv/Scripts/pip install -e .        # Windows；macOS/Linux 用 .venv/bin/pip
```

## 接入 MCP 客户端

已安装到环境后，在客户端配置里加：

```json
{
  "mcpServers": {
    "chengyu-coach": {
      "command": "uvx",
      "args": ["chengyu-coach-mcp"]
    }
  }
}
```

从源码运行时（`pip install -e .` 之后），用解释器直接启动模块：

```json
{
  "mcpServers": {
    "chengyu-coach": {
      "command": "<项目路径>/.venv/Scripts/python.exe",
      "args": ["-m", "chengyu_coach_mcp.server"]
    }
  }
}
```

调试可用官方 MCP Inspector：

```bash
npx @modelcontextprotocol/inspector uvx chengyu-coach-mcp
```

## 提供的能力

| 类型 | 名称 | 说明 |
| --- | --- | --- |
| Tool | `draw_idiom` | 随机抽成语（未抽过优先，可配数量/是否含已掌握） |
| Tool | `idiom_detail` | 查词：释义、出处、古例 + 学习进度 + 备注 |
| Tool | `search_idiom` | 按关键词/拼音/拼音缩写搜词库 |
| Tool | `update_status` | AI 根据对话表现更新掌握状态（learning/reviewing/mastered） |
| Tool | `add_note` | 写/清备注 |
| Tool | `progress` | 总进度：各状态数量、有备注数、最近抽取 |
| Tool | `reset_word` | 清空某词学习记录（destructive） |
| Resource | `chengyu://{word}` | 读取词库词条（JSON） |
| Resource | `chengyu://stats` | 学习进度统计（JSON） |
| Prompt | `learn_idiom` | 教学提示词（讲解 + 双场景造句） |
| Prompt | `quiz_me` | 口头考问流程提示词（抽词→作答→讲评→记录状态） |

造句和出题都不需要服务端：抽题/查词结果已带释义、出处、古文例句，客户端大模型据此讲解、造句、提问，并把判断结果写回 `update_status` / `add_note`。

## 数据与隐私

- 学习记录默认写入 `~/.chengyu-coach/idiom_progress.db`，可用环境变量 `CHENGYU_COACH_DB` 指定其他路径
- 数据只存在本机，不联网、不上传
- 词库随包分发，只读；替换 `src/chengyu_coach_mcp/data/chengyu_common.json` 即可换词库（数组，每条需含 `word/pinyin/explanation/derivation/example/id`）

`user_word` 表结构：

| 字段 | 说明 |
| --- | --- |
| `word` | 成语原文（主键） |
| `draw_count` | 抽中次数 |
| `status` | learning / reviewing / mastered（由 AI 判断写入） |
| `note` | 自由备注 |
| `first_drawn` / `last_drawn` | 首次/最近抽取时间 |

## 开发

```bash
python -m venv .venv
.venv/Scripts/pip install -e .
.venv/Scripts/python tests/smoke_test.py    # 端到端冒烟测试（自动使用临时数据库）
```

项目结构：

```
chengyu-coach-mcp/
├── src/chengyu_coach_mcp/
│   ├── __init__.py          # 版本号
│   ├── server.py            # 词库加载 + SQLite + 全部工具/资源/提示词
│   └── data/chengyu_common.json   # 常用成语词库（3303 条）
├── tests/smoke_test.py      # stdio 端到端测试
├── .github/workflows/ci.yml # Linux/Windows × Python 3.10/3.12
├── .github/workflows/release.yml  # 推 v* 标签自动发布到 PyPI（OIDC）
├── server.json              # 官方 MCP Registry 元数据
├── pyproject.toml
├── LICENSE                  # MIT（代码）
├── THIRD_PARTY_NOTICES.md   # 词库来源与许可
└── CHANGELOG.md
```

发布新版本时同步改三处：`pyproject.toml` 的 `version`、`src/chengyu_coach_mcp/__init__.py` 的 `__version__`、`CHANGELOG.md`；`server.json` 里的 `version` 与 `packages[0].version` 也要跟上。改完打标签并推送，`release.yml` 会校验四处版本号一致后自动构建上传：

```bash
git tag -a v1.0.1 -m "chengyu-coach-mcp v1.0.1"
git push origin main --tags
```

README 顶部那行 `<!-- mcp-name: io.github.FlowerOfFire/chengyu-coach-mcp -->` 是给官方 MCP Registry 验证包所有权用的，发布到 PyPI 的版本里必须带着它，删掉会导致 `mcp-publisher publish` 失败。

## 数据来源与许可

- 代码：[MIT](LICENSE)
- 成语词条：[chinese-xinhua](https://github.com/pwxcoo/chinese-xinhua)（MIT）
- 词频数据：[JioNLP](https://github.com/dongrixinyu/JioNLP)（Apache-2.0）

详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
