"""
端到端冒烟测试：以 stdio 子进程启动 chengyu_coach_mcp 服务器，
覆盖 initialize → 能力列表 → 抽题（不重复）→ 查词/搜索 → 更新状态/备注 → 进度 → 资源 → prompt。

运行：python tests/smoke_test.py（需要先 pip install -e .）
使用临时数据库（CHENGYU_COACH_DB），不会污染本机学习记录。
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

TMP_DB = Path(tempfile.gettempdir()) / "chengyu-coach-mcp-smoke.db"
TMP_DB.unlink(missing_ok=True)


def text(result) -> str:
    return result.content[0].text


async def main() -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "chengyu_coach_mcp.server"],
        env={**os.environ, "CHENGYU_COACH_DB": str(TMP_DB)},
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("✔ 已连接到服务器\n")

            tools = await session.list_tools()
            print("Tools:")
            for t in tools.tools:
                print(f"  - {t.name}: {t.description.splitlines()[0]}")

            resources = await session.list_resources()
            print("\nResources:")
            for r in resources.resources:
                print(f"  - {r.uri}: {r.title}")

            templates = await session.list_resource_templates()
            for t in templates.resource_templates:
                print(f"  - {t.uri_template}（模板）: {t.title}")

            prompts = await session.list_prompts()
            print("\nPrompts:")
            for p in prompts.prompts:
                print(f"  - {p.name}: {p.description}")

            print("\n--- 抽 2 个成语 ---")
            r = text(await session.call_tool("draw_idiom", {"count": 2}))
            print(r)
            drawn = [line.split("】")[0].lstrip("【") for line in r.splitlines() if line.startswith("【")]

            print("\n--- 再抽 1 个（不应与刚抽的重复） ---")
            r2 = text(await session.call_tool("draw_idiom", {"count": 1}))
            again = [line.split("】")[0].lstrip("【") for line in r2.splitlines() if line.startswith("【")]
            print(f"再抽到：{again}，与上次重叠：{set(again) & set(drawn) or '无'}")
            assert not set(again) & set(drawn)

            print("\n--- 查词 守株待兔 ---")
            print(text(await session.call_tool("idiom_detail", {"word": "守株待兔"})))

            print("\n--- 搜索 keyword=兔 ---")
            print(text(await session.call_tool("search_idiom", {"keyword": "兔", "limit": 3})))

            print("\n--- AI 判定后更新状态：守株待兔 → mastered ---")
            print(text(await session.call_tool("update_status", {"word": "守株待兔", "status": "mastered"})))
            print(text(await session.call_tool("add_note", {"word": "守株待兔", "note": "写周报可用来讽刺不主动的人"})))

            print("\n--- 非法状态（预期 isError） ---")
            r = await session.call_tool("update_status", {"word": "守株待兔", "status": "背下来了"})
            print(f"isError={r.is_error} text={r.content[0].text!r}")

            print("\n--- 进度 ---")
            print(text(await session.call_tool("progress")))

            print("\n--- 不存在的词（预期 isError） ---")
            r = await session.call_tool("idiom_detail", {"word": "不存在的成语"})
            print(f"isError={r.is_error}")

            print("\n--- 读取资源 chengyu://守株待兔 与 chengyu://stats ---")
            r1 = await session.read_resource("chengyu://守株待兔")
            print(r1.contents[0].text[:80], "…")
            r2 = await session.read_resource("chengyu://stats")
            print(r2.contents[0].text)

            print("\n--- 获取 prompt learn_idiom / quiz_me ---")
            r = await session.get_prompt("learn_idiom", {"word": "画蛇添足"})
            print(r.messages[0].content.text[:80], "…")
            r = await session.get_prompt("quiz_me", {"count": "3"})
            print(r.messages[0].content.text[:80], "…")

    print("\n✔ 全部测试完成")


if __name__ == "__main__":
    asyncio.run(main())
