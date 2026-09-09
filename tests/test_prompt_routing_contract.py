from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROMPTS = ROOT / "prompts"


def read(name: str) -> str:
    return (PROMPTS / name).read_text(encoding="utf-8")


def test_direct_wz_and_xcx_recipes_exist_with_burp_contract():
    wz = read("配方WZ_网站流程.md")
    xcx = read("配方XCX_小程序流程.md")
    for text in (wz, xcx):
        assert "mcporter@0.9.0" in text
        assert "127.0.0.1:9876" in text
        assert "精确 scheme/host/port" in text
        assert "原始 history" in text
        assert "不等于获得目标主动发包授权" in text
    assert "phase_status.json" in wz
    assert "phase_status.miniapp.json" in xcx


def test_dispatcher_is_recommended_unified_route():
    p = read("配方P_提示词分发员.md")
    assert "统一评估流程路由器" in p
    assert "推荐入口" in p
    assert "runs/<run>" in p
    assert "网站域名、URL" in p
    assert "小程序名称、AppID" in p
    assert "配方WZ_网站流程.md" in p
    assert "配方XCX_小程序流程.md" in p


def test_fh_recipe_states_limited_readonly_network_review():
    text = read("配方A_复盘会话.md")
    assert "单目标" in text
    assert "并发 1" in text
    assert "同 host 请求间隔至少 3 秒" in text
    assert "每个目标最多 10 次只读 GET/HEAD" in text
    assert "不是重新扫描或主动测试" in text


def test_c_recipe_routes_wz_and_xcx_cursor_files_separately():
    text = read("配方C_单目标深挖.md")
    assert "WZ 使用 `phase_status.json`" in text
    assert "XCX 使用 `phase_status.miniapp.json`" in text
    assert "不得连续静默推进多个 phase" in text
    assert "本机 Burp 抓好包" in text


def test_manifest_and_generator_describe_direct_menu():
    manifest = (ROOT / "AGENT_MANIFEST.md").read_text(encoding="utf-8")
    generator = (ROOT / "scripts" / "gen_agent_manifest.py").read_text(encoding="utf-8")
    for text in (manifest, generator):
        assert "1-10" in text
        assert "P" in text and "WZ" in text and "XCX" in text
        assert "统一流程路由入口" in text


def test_skill_mirrors_have_burp_sections():
    for stream in ("fh", "wz", "xcx"):
        texts = [
            (ROOT / tree / "skills" / stream / "SKILL.md").read_text(encoding="utf-8")
            for tree in (".agents", ".claude", ".opencode")
        ]
        assert texts[0] == texts[1] == texts[2]
        assert "Burp" in texts[0]
