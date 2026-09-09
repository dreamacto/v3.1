from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_project(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_playbook_contains_explicit_burp_order_and_fallback():
    text = read_project("docs/BROWSER_BURP_MCP_PLAYBOOK.md")
    assert text.index("Burp MCP list") < text.index("查询只读 HTTP history")
    assert "mcporter@0.9.0 list http://127.0.0.1:9876 --allow-http" in text
    assert "--http-url" in text
    assert '"count=60" "offset=0"' in text
    assert "not_found" in text and "host_mismatch" in text and "mcp_unavailable" in text
    assert "不得先要求用户重新提供 HAR/XML/TXT/cURL" in text
    assert "重试一次" in text


def test_playbook_contains_explicit_browser_entrypoint():
    text = read_project("docs/BROWSER_BURP_MCP_PLAYBOOK.md")
    assert "mcp__node_repl__js" in text
    assert "setupBrowserRuntime" in text
    assert "agent.browsers.list()" in text
    assert "browser.tabs.list()" in text
    assert "domSnapshot()" in text
    assert "browser-firefox" in text and "不是项目内可猜测的 MCP 工具名" in text
    assert "不得委托给子代理" in text


def test_stream_skills_and_recipes_reference_playbook_and_hard_order():
    paths = [
        ".agents/skills/wz/SKILL.md",
        ".agents/skills/xcx/SKILL.md",
        "prompts/配方WZ_网站流程.md",
        "prompts/配方XCX_小程序流程.md",
        "prompts/配方C_单目标深挖.md",
    ]
    for path in paths:
        text = read_project(path)
        assert "BROWSER_BURP_MCP_PLAYBOOK.md" in text
        assert "mcporter@0.9.0" in text
        assert "mcp__node_repl__js" in text
        assert "不得先索要 HAR/XML/TXT/cURL" in text or "不得先要求用户重新提供 HAR/XML/TXT/cURL" in text
    for path in paths[:2]:
        text = read_project(path)
        assert "not_found" in text and "host_mismatch" in text and "mcp_unavailable" in text


def test_mirrored_stream_skills_remain_identical():
    for stream in ("wz", "xcx"):
        for rel in ("SKILL.md", "references/workflow.md", "references/artifact-contract.md"):
            texts = [
                (ROOT / tree / "skills" / stream / rel).read_text(encoding="utf-8")
                for tree in (".agents", ".claude", ".opencode")
            ]
            assert texts[0] == texts[1] == texts[2], (stream, rel)
