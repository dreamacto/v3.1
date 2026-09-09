# 版本表（VERSIONS）

> 版本方案（操作者指定，2026-09-09）：总体 **v3**；v3 之后、APP 流程之前的全部提交归入 **v3.1.x**；
> **APP 流程整体 = v3.2（中版本）**，九个施工批次 = **v3.2.1 – v3.2.9（子版本）**。
> 历史提交的版本号以 annotated tag 为准（不打改写历史）；历史消息 d01a9c0 中的"v4.1"字样按操作者决议并入 v3 谱系，以 v3.1.1 标签为准。
>
> **GitHub Releases 版本策略（2026-09-10 起）**：Releases 仅保留 **x.y 级五个版本：v1 / v2 / v3 / v3.1 / v3.2**，
> 每个版本的说明写明该版本新增点；x.y.z 批次子号不再作为 GitHub Release/tag，仅保留在提交消息与下表记录中用于追溯。
> v3.2 标签指向中版本最终态（含 B0–B9、验收台账与 README 重写）。

## v1 – v3（既有里程碑 tag）

| 版本 | 提交 | 内容 |
|---|---|---|
| v1 | 7835f76 | 信息收集工作流初始快照 |
| v2 | 8aa14ea | W5–W14 全量施工（fh 复核编排/IDOR/竞态/SSRF/XSS/白盒 L0/knowledge_base/度量/桌面运行时统一） |
| v3 | 74ab28c | 离线完整性控制与 WZ/XCX/FH 工作流汇总 |

## v3.1.x（v3 之后、APP 之前的提交，回溯补标）

| 版本 | 提交 | 内容 |
|---|---|---|
| v3.1.1 | d01a9c0 | 冻结多 Agent 编排统一契约（原消息 v4.1，按决议归入 v3） |
| v3.1.2 | 88b68ab | 离线运行时事件与恢复控制 |
| v3.1.3 | 80694a4 | 静态评估图规划 |
| v3.1.4 | 78376c8 | table 01 验收状态记录 |
| v3.1.5 | 98fd9ba | 离线 worker 注册表与执行器 |
| v3.1.6 | 2986197 | verifier 质量证据上下文指标 |
| v3.1.7 | b7eaa6f | WZ specialist workers 与图适配 |
| v3.1.8 | 0d04b1f | XCX specialist workers 与图适配 |
| v3.1.9 | f6545ba | supervisor 编排运行时 |
| v3.1.10 | 2ad1cc4 | 编排兼容模式 |
| v3.1.11 | db67e2c | WZ/XCX P0 能力升级 + 分支待提交改动（原 18ab840 非 APP 部分） |
| v3.1.12 | 911a479 | 分支工作区收尾（construction batch 09 表/实施日志/sessions.jsonl 忽略守卫） |
| v3.1.13 | 99dce3b | 移除非项目产物（session-tool 工作区/本地靶场输出） |

## v3.2 APP 流程（中版本；第三工作流，B0 前置随 v3.2.1 落盘）

| 版本 | 批次 | 内容 |
|---|---|---|
| v3.2.1 | B1 | Skill 骨架（SKILL + 6 references × 三镜像）+ B0 工具白名单前置（jadx/apktool registry、tool_strategy 17 个 app_* 阶段与双审批门）+ 蓝图 docs/APP_WORKFLOW_CONSTRUCTION_PLAN.md |
| v3.2.2 | B2 | init_app_engagement + phase_status_routing（三流隔离 fail-closed）+ 3 测试 |
| v3.2.3 | B3 | audit_app_engagement 审计器 + fail-closed 负例测试 |
| v3.2.4 | B4 | 六个 contracts/app_*.json 契约 |
| v3.2.5 | B5 | 静态引擎（共享引擎/hardening/static_extraction/webview/ipc）+ 契约同步测试 |
| v3.2.6 | B6 | 认证/对账/云九模块引擎 + 行为锁定测试 |
| v3.2.7 | B7 | 配方APP + 配方P/C + copy_prompt 菜单 + CONTEXT_LOADING_MAP + 导航文档 |
| v3.2.8 | B8 | 端到端离线验收执行（记录落 docs/APP_CONSTRUCTION_ACCEPTANCE.md，随 v3.2.9 入库；本批无生产代码） |
| v3.2.9 | B9 | Graph/编排接入（app_graph_schema + orchestration/app_graph.py + 三测试）+ 验收台账/施工台账闭环 + 本版本表 |
| **v3.2** | — | 中版本标签，打在 v3.2.9（B0–B9 全部验收通过，详见 docs/APP_CONSTRUCTION_ACCEPTANCE.md） |

> 注：v3.2.8 为标注性空提交（--allow-empty），用于保持"九批九子版本"与批次台账一一对应。
