# 授权安全演练辅助平台

**当前版本：[v3.2](https://github.com/dreamacto/Information-Gathering/releases/tag/v3.2)**（APP 流程闭环） · 全部版本号见 [Releases](https://github.com/dreamacto/Information-Gathering/releases) · 版本对照表见 [`docs/VERSIONS.md`](docs/VERSIONS.md)

把**已授权**的 SRC / 护网 / 攻防演练目标，整理成低速、只读、证据导向的评估流水线：受控候选筛查 → 单目标确认编排 → 证据与质量门 → 人工终审与报告。

> 这不是全量漏扫器，也不是自动化利用器。产出不是"扫到了多少条"，而是：哪些目标确实在授权范围内、哪些线索值得人工确认、哪些阶段实际执行过、证据是否可复现、下一轮该测什么。

---

## 三大工作流 + 复核闭环

| 流程 | 输入 | 游标 | 用途 |
|---|---|---|---|
| **WZ** 网站/API | 域名、URL、run 目录 | `phase_status.json` | 子域→存活→指纹→接口/产品/注入候选→认证态复核 |
| **XCX** 小程序 | 名称、AppID、wxapkg、缓存、流量 | `phase_status.miniapp.json` | 解密解包→源码恢复→认证/云/第三方边界 |
| **APP** 移动应用（v3.2 新增） | APK/IPA/XAPK、包名、市场链接、已解包目录、流量 | `phase_status.app.json` | 解包反编译（apktool/jadx）→静态分析→认证/本地存储/IPC/云边界，对照 OWASP MASTG/MASVS |

每个流程独立 engagement 工作区（`engagements/<目标-日期>/`），**一次只推进一个阶段**，游标与阶段记录写盘后询问"继续本会话还是交接"。配套会话：FH 运行后复核（`fh_review_dispatch.py`）、B 规划、D 逻辑/竞态、F 白盒 sink、E 周度沉淀、Z 验收——统一由 `prompts/配方P_提示词分发员.md` 路由。

## 安全边界（摘要，全文见 [`ROE.md`](ROE.md)）

- **授权前提**：只处理当前授权文档/目标清单覆盖的资产；新发现域名、小程序后端、第三方路径先进归属确认队列。
- **默认动作**：只读、低速（同 host 串行、间隔 ≥2s、429/5xx 退避）、本地离线解析优先；候选 ≠ 漏洞。
- **审批门（双钥匙）**：弱口令、SQLMap、上传/导出/事务、命令执行、竞态写、SSRF 主动验证、设备 root/越狱、frida 注入、SSL pinning bypass、加固脱壳——脚本审批门 + 会话内人工确认，缺一不可。
- **禁止动作**：password_spray / bruteforce / webshell / c2 / tunnel / data_export / destructive_write / ddos / social_engineering / near_field。
- **凭证纪律**：Cookie/Token/密钥只存本地 `*.local.*` 文件，不进报告、日志、台账、git。
- **停止条件**：窗口关闭、服务劣化、范围外资产、WAF 告警迹象——立即停手并报告。

## 快速开始（Windows）

```powershell
:: 低速只读全流程（推荐）
launchers\一键保守全流程_尽量多信息_避WAF.bat

:: 或主编排器
python .\gov_exercise_runner.py --targets <目标文件> --probe --fingerprint --high-value-paths --api-discovery --api-confirm --delay 3

:: 跑完先看
runs\<本轮目录>\00_重要_人工复核入口\README_先看这里.md

:: run 完成态查询（跑完了吗/下一步是什么）
python .\run_lifecycle.py runs\<本轮目录>
```

更多入口：`launchers\`（一键完整/已有子域名/并行分批/小程序 Burp 导入/全目标作战台），根目录同名 BAT 仅为兼容转发。AI 会话配方用桌面 `AI配方_一键复制.bat`（菜单 1–12：配方 A–F/P/R/WZ/XCX/APP/Z）。

## 仓库地图

```text
gov_exercise_runner.py        主编排器（21 阶段 WZ 主流程）
run_lifecycle.py              run 完成态推导
fh_review_dispatch.py         FH 复核批次编排 + 深挖推荐
src/authorized_assessment/    包结构：orchestration / triage / miniapp / app / analysis / tools
contracts/                    JSON Schema 与流程契约（含 app_* 七件）
.agents/skills/               wZ/XCX/app/FH 等 skill canonical（.claude/.opencode 为镜像）
prompts/                      AI 会话配方 A–F/P/R/WZ/XCX/APP/Z
launchers/                    Windows 规范启动器
knowledge_base/               指纹记忆/漏洞模式/假设台账/sink 库（离线沉淀）
tests/                        pytest（离线验收基线）
docs/                         结构/规则/方案/验收/版本表
runs/ engagements/ tools/ unpacked/   本地资产（git 忽略，不入库）
```

## 文档索引

| 文档 | 内容 |
|---|---|
| [`AGENTS.md`](AGENTS.md) | AI 会话入口：定位/边界/上下文纪律/运行时表 |
| [`ROE.md`](ROE.md) | 交战规则唯一事实源：授权/速率/动作分级/凭证/停止条件 |
| [`docs/RULE_PRECEDENCE.md`](docs/RULE_PRECEDENCE.md) | 规则冲突时的唯一优先级 |
| [`docs/PROJECT_STRUCTURE.md`](docs/PROJECT_STRUCTURE.md) | 目录归类与入口规范 |
| [`docs/VERSIONS.md`](docs/VERSIONS.md) | v1 → v3.2 全部版本对照 |
| [`docs/APP_WORKFLOW_CONSTRUCTION_PLAN.md`](docs/APP_WORKFLOW_CONSTRUCTION_PLAN.md) | APP 流程施工蓝图（33 阶段/批次/附录） |
| [`docs/APP_CONSTRUCTION_ACCEPTANCE.md`](docs/APP_CONSTRUCTION_ACCEPTANCE.md) | APP 流程 B1–B9 验收台账 |
| [`AGENT_MANIFEST.md`](AGENT_MANIFEST.md) | 机器可读工具清单（生成物，勿手改） |

## 离线验收

```powershell
python -m pytest -q                                # 全量测试
python scripts/verify_offline.py --json            # 编译+漂移+测试
python scripts/maintenance/validate_run_contracts.py   # 契约↔引擎↔种子同源
python scripts/check_skill_drift.py                # skill 三镜像一致
python scripts/maintenance/rebuild_tool_inventory.py --check   # 工具登记一致性
```

以上全部只做本地检查，不连接真实目标。

---

**纪律提醒**：所有网络访问必须经过授权范围、速率控制与审批门；`runs/`、`engagements/`、凭证与真实目标材料永远不入库。历史实验脚本见 `legacy/`，不作为主流程入口。
