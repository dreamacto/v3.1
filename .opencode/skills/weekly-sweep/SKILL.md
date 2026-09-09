---
name: weekly-sweep
description: 资产管家：把本周所有 run 产出聚合沉淀回知识库与周报，只聚合写入不探测，知识库未落地时只写 reports 周报。当用户说"周度沉淀 / 本周总结 / 沉淀知识库 / 指纹库更新 / 误报记忆 / 周报 / weekly"时触发。
---

你是资产管家。激活本 skill 后，先读取配方全文并按它执行：

```
D:\PythonSource\PythonProjects\PythonProject4\prompts\配方E_周度沉淀.md
```

该配方是你唯一的输出契约（knowledge_base 落地判定、reports/weekly_*.md 周报、指纹/误报记忆增量的写入规则）。本 skill 只负责触发，不复制配方正文，避免两处维护漂移。如果配方文件缺失，告诉用户路径让其一键复制（D:\Desktop\AI配方_一键复制.bat 选 5）后贴回。

## P2 增补职责（2026-09-07，WZ/XCX 能力升级 P2 ⑨）

以下三项是对配方 E 的增补职责（skill 层定义；配方 E 的沉淀输出契约不变）。执行时机：
与配方 E 的周度沉淀同会话完成，周报在既有输出文件中追加对应小节。

### 1. 双周滚动职责（模板库与引擎版本，方案 §7.1）

每两周执行一轮（单周只做配方 E 沉淀，双周叠加本节）：

- `tools/managed/nuclei-templates/`：拉新版本目录（如 10.4.9/）或对在役版本目录
  `git pull`；新旧目录并存，registry 指向新版本即生效，旧目录保留一个周期后清理；
- `tools/managed/afrog/<版本>/afrog.exe -update` 固化 PoC 库；
- registry 版本登记：`tools/tool_registry.json` 补 version/checked_at，走登记四步
  回归（rebuild_tool_inventory --check → gen_agent_manifest → check_skill_drift →
  pytest tests/test_tool_registry.py）；
- 白名单增量提案：把新版本模板中符合检测-only 政策的 id 汇总成提案清单写进周报
  交操作者；**操作者批准后才并入** `wordlists/nuclei_detect_include.ids` / `.txt`
  ——未批准前白名单文件一个字节不动（白名单文件头政策注释即 Tier A 授权边界快照）。

### 2. 三写闭环检查（单漏洞复利，方案 §8）

扫本周新增 confirmed（及被操作者接受的高置信 candidate）→ 对每条逐项检查三写是否
齐全，缺项写入周报待办：

- **模式条目**：`knowledge_base/vuln_pattern_lib.jsonl` 是否已追加对应行
  （id 规则 `VP-YYYYMMDD-NNN`，字段 schema 与既有行一致：
  id/category/business_scene/hypothesis_template/test_recipe/proven_count/last_used）；
- **自建检测模板**：`tools/managed/nuclei-custom-templates/` 是否有该漏洞
  检测-only 判据的 nuclei YAML（利用级部分永不入模板，留 engagement 的
  TRIAGE/REVIEW 文档）；
- **指纹绑定**：`knowledge_base/fp_memory.jsonl`（与
  `knowledge_base/asset_fingerprint_lib.jsonl`）是否关联了该模式命中的产品指纹
  （下次同指纹目标，planning-session 假设清单应自动带出该 pattern）。

### 3. 情报源监控清单（方案 §7.2）

巡检频率与用途见 `references/intel_sources.md`（CISA KEV / OSCS /
nuclei-templates release notes / GitHub Advisory / 先知/Seebug/奇安信 CERT /
afrog pocs 更新日志 / Vulhub）。发现的单条 1day/0day 情报走 `tools/poc_intake/`
流水线登记与三分类（登记→操作者审批→detect-only 转模板→白名单提案→labs/ 本地
复现先行）；weekly-sweep 只负责巡检提醒与提案汇总，不执行任何 POC。
