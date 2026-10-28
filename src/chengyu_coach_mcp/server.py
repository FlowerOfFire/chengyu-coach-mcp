"""
chengyu-coach-mcp —— 成语学习 MCP 服务器

基于官方 Python SDK（mcp v2 的 MCPServer），把 chengyu_common.json（3303 条常用成语）
变成一份可以"抽卡学习"的词库：

  - 抽题：优先抽没抽过的，抽完后按"抽得最少 + 最久没抽"轮转
  - 查询：每个成语抽中了几次、当前状态、备注
  - 记录：掌握状态 + 每词自由备注。不内置测验卷——
          考不考、怎么考由对话中的 AI 决定，AI 根据用户表现调用 update_status 记录

掌握状态：learning（还不熟）→ reviewing（基本会但不稳）→ mastered（能熟练解释和造句）。
状态由 AI 依据对话自行判断更新，服务端不自动判分。

存储：SQLite（默认 ~/.chengyu-coach/idiom_progress.db，可用环境变量 CHENGYU_COACH_DB 覆盖），
      词库为随包分发的只读 JSON。
传输：stdio。

运行：python -m chengyu_coach_mcp.server
"""

import json
import os
import random
import sqlite3
import threading
from datetime import datetime
from importlib.resources import files as pkg_files
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import __version__

DICT_PATH = pkg_files("chengyu_coach_mcp").joinpath("data/chengyu_common.json")
DB_PATH = Path(
    os.environ.get("CHENGYU_COACH_DB")
    or Path.home() / ".chengyu-coach" / "idiom_progress.db"
)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

mcp = MCPServer(
    name="chengyu-coach-mcp",
    version=__version__,
    instructions=(
        "成语学习服务器：用 draw_idiom 随机抽成语，用 idiom_detail/search_idiom 查词，"
        "结果里已带释义、出处、古文例句，直接据此讲解和造句即可。"
        "根据聊天中用户的实际表现，主动用 update_status 更新掌握状态"
        "（能准确解释并举一反三→mastered，大致理解但不稳→reviewing，答错或卡壳→learning），"
        "用 add_note 记录易错点和心得。"
    ),
)

# ---------------------------------------------------------------------------
# 1. 词库：只读，启动时整表加载（约 3300 条，内存占用可忽略）
# ---------------------------------------------------------------------------

with DICT_PATH.open(encoding="utf-8") as f:
    DICT: dict[str, dict] = {r["word"]: r for r in json.load(f)}

# ---------------------------------------------------------------------------
# 2. 学习状态：SQLite 单连接 + 锁（工具可能在不同线程被调度）
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
_conn.row_factory = sqlite3.Row

_conn.execute(
    """CREATE TABLE IF NOT EXISTS user_word (
        word         TEXT PRIMARY KEY,
        idiom_id     INTEGER,
        draw_count   INTEGER NOT NULL DEFAULT 0,
        status       TEXT    NOT NULL DEFAULT 'learning',
        note         TEXT    NOT NULL DEFAULT '',
        first_drawn  TEXT    NOT NULL DEFAULT '',
        last_drawn   TEXT    NOT NULL DEFAULT ''
    )"""
)
_conn.commit()

STATUS_CN = {
    "learning": "学习中",
    "reviewing": "复习中",
    "mastered": "已掌握",
}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _get_state(word: str) -> sqlite3.Row | None:
    return _conn.execute(
        "SELECT * FROM user_word WHERE word = ?", (word,)
    ).fetchone()


def _fmt_state(row: sqlite3.Row | None) -> str:
    if row is None:
        return "未学"
    return (
        f"{STATUS_CN.get(row['status'], row['status'])}"
        f"｜抽中 {row['draw_count']} 次"
    )


def _fmt_idiom(word: str) -> str:
    r = DICT[word]
    lines = [
        f"【{r['word']}】 {r['pinyin']}",
        f"释义：{r['explanation']}",
        f"出处：{r['derivation']}",
        f"古例：{r['example']}",
    ]
    st = _get_state(word)
    if st:
        lines.append(f"进度：{_fmt_state(st)}")
        if st["note"]:
            lines.append(f"备注：{st['note']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 3. Tools
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": False})
def draw_idiom(count: int = 1, include_mastered: bool = False) -> str:
    """随机抽成语学习。优先抽没抽过的；都抽过一轮后，抽得最少且最久没抽的优先。默认跳过最近 20 条和已掌握的。

    Args:
        count: 抽几个（1~10）
        include_mastered: 是否把已掌握的也放回抽奖池
    """
    count = max(1, min(count, 10))
    with _lock:
        rows = _conn.execute(
            "SELECT word, status, draw_count, last_drawn FROM user_word"
        ).fetchall()
        recent = {r["word"] for r in rows[:20]}
        state = {r["word"]: r for r in rows}

        skip_status = set() if include_mastered else {"mastered"}
        undrawn, pool = [], []
        for w in DICT:
            if w in recent:
                continue
            st = state.get(w)
            if st is None:
                undrawn.append(w)
            elif st["status"] not in skip_status:
                pool.append(w)

        if undrawn:
            picks = random.sample(undrawn, min(count, len(undrawn)))
        elif pool:
            # 抽得最少的排前面，同次数里最久没抽的排前面
            pool.sort(key=lambda w: (state[w]["draw_count"], state[w]["last_drawn"]))
            picks = pool[:count]
        else:
            return "抽奖池空了：没抽过的都抽完了，剩下的都标记为已掌握。可用 include_mastered=true 重抽。"

        out = []
        for w in picks:
            st = _get_state(w)
            now = _now()
            if st is None:
                _conn.execute(
                    "INSERT INTO user_word (word, idiom_id, draw_count, status,"
                    " first_drawn, last_drawn) VALUES (?,?,?,?,?,?)",
                    (w, DICT[w]["id"], 1, "learning", now, now),
                )
            else:
                _conn.execute(
                    "UPDATE user_word SET draw_count = draw_count + 1,"
                    " last_drawn = ? WHERE word = ?",
                    (now, w),
                )
            _conn.commit()
            out.append(_fmt_idiom(w))
        return f"本次抽到 {len(out)} 个成语：\n\n" + "\n\n".join(out)


@mcp.tool(annotations={"readOnlyHint": True})
def idiom_detail(word: str) -> str:
    """查一个成语的释义、出处、古文例句，以及学习进度（抽中次数、状态、备注）。

    Args:
        word: 成语原文，如 守株待兔
    """
    if word not in DICT:
        raise ToolError(f"「{word}」不在常用成语词库里。")
    return _fmt_idiom(word)


@mcp.tool(annotations={"readOnlyHint": True})
def search_idiom(keyword: str, limit: int = 10) -> str:
    """按关键词搜成语（匹配成语、拼音或释义），并附各自的抽中次数。

    Args:
        keyword: 关键词，中文或拼音缩写（如 szdt）
        limit: 最多返回几条（1~20）
    """
    limit = max(1, min(limit, 20))
    k = keyword.strip().lower()
    hits = []
    for r in DICT.values():
        if (
            k in r["word"]
            or k in r["pinyin"].lower()
            or k in r["abbreviation"]
            or k in r["explanation"]
        ):
            hits.append(r)
            if len(hits) >= limit:
                break
    if not hits:
        return f"词库里没搜到包含「{keyword}」的成语。"
    lines = []
    for r in hits:
        st = _get_state(r["word"])
        extra = f"（{_fmt_state(st)}）" if st else "（未学）"
        lines.append(f"【{r['word']}】{r['pinyin']} {extra}\n  {r['explanation']}")
    return f"共 {len(hits)} 条：\n\n" + "\n".join(lines)


@mcp.tool(annotations={"readOnlyHint": False})
def update_status(word: str, status: str) -> str:
    """根据对话中用户的实际表现，更新成语的掌握状态。由 AI 自行判断调用，服务端不做判分。

    Args:
        word: 成语原文
        status: learning=还不熟/答错/卡壳；reviewing=大致理解但不够稳；mastered=能准确解释并举一反三
    """
    if word not in DICT:
        raise ToolError(f"「{word}」不在常用成语词库里。")
    if status not in STATUS_CN:
        raise ToolError(f"status 只能是 learning / reviewing / mastered，收到的是「{status}」。")
    with _lock:
        now = _now()
        if _get_state(word) is None:
            _conn.execute(
                "INSERT INTO user_word (word, idiom_id, status, first_drawn,"
                " last_drawn) VALUES (?,?,?,?,?)",
                (word, DICT[word]["id"], status, now, now),
            )
        else:
            _conn.execute(
                "UPDATE user_word SET status = ? WHERE word = ?", (status, word)
            )
        _conn.commit()
    return f"「{word}」状态已更新为：{STATUS_CN[status]}。"


@mcp.tool(annotations={"readOnlyHint": False})
def add_note(word: str, note: str) -> str:
    """给某个成语写备注（自由文本，如易错点、使用场景），会覆盖原备注。

    Args:
        word: 成语原文
        note: 备注内容；传空字符串则清除备注
    """
    if word not in DICT:
        raise ToolError(f"「{word}」不在常用成语词库里。")
    with _lock:
        now = _now()
        if _get_state(word) is None:
            _conn.execute(
                "INSERT INTO user_word (word, idiom_id, note, first_drawn,"
                " last_drawn) VALUES (?,?,?,?,?)",
                (word, DICT[word]["id"], note, now, now),
            )
        else:
            _conn.execute("UPDATE user_word SET note = ? WHERE word = ?", (note, word))
        _conn.commit()
    return f"「{word}」的备注已更新：{note or '（已清除）'}"


@mcp.tool(annotations={"readOnlyHint": True})
def progress() -> str:
    """查看整体学习进度：接触了几个、各状态数量、有备注的、最近抽的 10 个。"""
    with _lock:
        rows = _conn.execute(
            "SELECT * FROM user_word ORDER BY last_drawn DESC"
        ).fetchall()
    total = len(rows)
    if total == 0:
        return "还没开始：先用 draw_idiom 抽几个成语吧。"
    by_status = {"learning": 0, "reviewing": 0, "mastered": 0}
    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    noted = sum(1 for r in rows if r["note"])
    recent = "\n".join(
        f"  {r['word']}（抽 {r['draw_count']} 次，{STATUS_CN.get(r['status'], r['status'])}）"
        for r in rows[:10]
    )
    return (
        f"已接触 {total} / {len(DICT)} 个常用成语\n"
        f"状态：学习中 {by_status['learning']}"
        f"｜复习中 {by_status['reviewing']}｜已掌握 {by_status['mastered']}\n"
        f"有备注 {noted} 个\n"
        f"最近抽的：\n{recent}"
    )


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": True})
def reset_word(word: str) -> str:
    """清空某个成语的学习记录（抽中次数、状态、备注），词库本身不受影响。

    Args:
        word: 成语原文
    """
    with _lock:
        cur = _conn.execute("DELETE FROM user_word WHERE word = ?", (word,))
        _conn.commit()
    if cur.rowcount == 0:
        return f"「{word}」本来就没有学习记录。"
    return f"已清空「{word}」的学习记录。"


# ---------------------------------------------------------------------------
# 4. Resources：只读数据
# ---------------------------------------------------------------------------


@mcp.resource(
    "chengyu://{word}",
    title="成语词条",
    description="按成语原文读取词库词条（JSON，含释义/出处/例句/词频）",
    mime_type="application/json",
)
def idiom_resource(word: str) -> str:
    r = DICT.get(word)
    if r is None:
        return json.dumps({"error": f"「{word}」不在词库"}, ensure_ascii=False)
    return json.dumps(r, ensure_ascii=False, indent=2)


@mcp.resource(
    "chengyu://stats",
    title="学习进度",
    description="学习状态统计（JSON）：各状态数量",
    mime_type="application/json",
)
def stats_resource() -> str:
    with _lock:
        rows = _conn.execute("SELECT status, COUNT(*) n FROM user_word GROUP BY status").fetchall()
    return json.dumps(
        {
            "dict_size": len(DICT),
            "by_status": {r["status"]: r["n"] for r in rows},
        },
        ensure_ascii=False, indent=2,
    )


# ---------------------------------------------------------------------------
# 5. Prompts：预设提示词（造句/教学场景交给客户端大模型完成）
# ---------------------------------------------------------------------------


@mcp.prompt(title="学一个成语", description="生成教用户学某个成语的提示词（含释义讲解与造句任务）")
def learn_idiom(word: str) -> str:
    r = DICT.get(word, {})
    return (
        f"请教我成语「{word}」：\n"
        f"1. 用一两句话通俗解释：{r.get('explanation', '')}\n"
        f"2. 讲讲出处故事：{r.get('derivation', '')}\n"
        f"3. 造两个例句——一个生活口语场景、一个职场/书面场景，并说明容易用错的地方。\n"
        f"4. 讲完后根据我的反馈调用 update_status 记录掌握程度。\n"
        f"参考古文例句：{r.get('example', '')}"
    )


@mcp.prompt(title="考考我", description="让 AI 随机抽成语口头考你，并根据表现更新掌握状态")
def quiz_me(count: str = "5") -> str:
    return (
        f"随机抽 {count} 个成语考我：一次只出一道，先给释义让我猜成语，"
        f"或给我成语让我解释并举一个例句。等我答完再公布答案并讲解出处和易错点。"
        f"每题结束后根据我的表现调用 update_status 记录（答错或卡壳→learning，"
        f"大致会但不稳→reviewing，解释准确且例句贴切→mastered），"
        f"最后用 progress 汇报本次结果。"
    )


# ---------------------------------------------------------------------------
# 6. 启动：stdio 传输。协议消息走 stdout，日志一律走 stderr。
# ---------------------------------------------------------------------------


def main() -> None:
    import sys

    print(
        f"chengyu-coach-mcp {__version__} 已启动：词库 {len(DICT)} 条，学习记录 {DB_PATH}",
        file=sys.stderr,
    )
    mcp.run()


if __name__ == "__main__":
    main()
