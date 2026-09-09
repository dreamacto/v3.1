# APP 流程（第三个工作流）详细施工方案

> **状态**：施工蓝图（B0 已完成，B1-B9 待操作者确认后推进）。本文档对应 CONSTRUCTION_STATUS.md 的 W15-W20（+B9=W21）工单。
> **编写时间**：2026-09-07。编写会话完成摸底、权威对照、B0 全部施工与全量离线验收（见 §9）。
> **规则层级**：本方案不是授权事实源；施工与运行全程受 `AGENTS.md`、`ROE.md`、`docs/RULE_PRECEDENCE.md` 约束。

---

## 0. 一句话结论

在现有 **WZ（网站/API）**、**XCX（小程序）** 两个流程之外，按 **XCX 的工程模式**（engagement 工作区 + 独立游标 + 离线优先 + 审批门 + 阶段推进/询问交接）建立第三个流程 **APP（移动应用 Android/iOS）**：新增 `.agents/skills/app/`（含镜像）、`contracts/app_*.json` 契约、`src/authorized_assessment/app/` 离线评审模块、`prompts/配方APP_App流程.md` 配方，并把阶段与工具登记进 `tool_strategy.json`、`gov_exercise_config.json`、`tools/tool_registry.json`。阶段集对照 **OWASP MASTG v2 / MASVS v2.1** 权威结构设计，默认离线、只读，设备类与绕过类动作全部进审批门。

---

## 1. 背景与目标

### 1.1 为什么是第三个流程

- 现有 `gov_exercise_workflow.json` 的 21 个阶段是 WZ 主流程；XCX 是独立 engagement 流（`phase_status.miniapp.json` + `tool_strategy.json` 注册 + `src/authorized_assessment/miniapp/` 离线引擎），与 WZ 游标严格隔离。
- 移动 App（APK/IPA）的输入形态、攻击面（客户端静态、本地存储、IPC、WebView 桥、传输与后端）与小程序高度同构但平台语义不同（加固壳、exported 组件、allowBackup、设备动态分析），复用 XCX 模式 + MASTG 阶段字典是改动面最小、纪律一致性最高的路线。

### 1.2 使用方式（与 wz/xcx 完全一致）

1. 操作员提供任一入口材料：APK/IPA/XAPK 文件、包名、应用市场链接、已解包目录、Burp 流量导出、设备缓存目录等。
2. AI 会话读 `AGENTS.md`、`ROE.md`、`.agents/skills/app/SKILL.md`，跑 `init_app_engagement.py` 建/续 workspace。
3. 读 `phase_status.app.json` 游标，**一次只推进一个 phase**，写盘（游标 + phase note + target-model），然后询问"继续本会话还是交接"。
4. 审批门阶段（设备 root/越狱、frida/objection 注入、SSL pinning bypass、加固脱壳、任何写动作）双钥匙停止。

---

## 2. 权威对照（OWASP MASTG / MASVS）

权威来源（2026-09 在线核对）：

- OWASP MASTG v2（mas.owasp.org/MASTG）：Android/iOS 两平台章节均为 Platform Overview → Data Storage → Cryptographic APIs → Local Authentication → Network Communication → Platform APIs → Code Quality and Build Settings → Anti-Reversing Defenses；Tests/Knowledge/Demos 目录按 MASVS 域组织。
- MASVS v2.1 域：**STORAGE / CRYPTO / AUTH / NETWORK / PLATFORM / CODE / RESILIENCE / PRIVACY**。
- MASTG v2 重构为原子测试（MASTG-TEST-XXXX）+ MASWE 弱点目录，机器可读、按平台 × MASVS 域索引。

### 2.1 MASVS 域 → APP 阶段映射

| MASVS 域 | APP 阶段 | 说明 |
|---|---|---|
| STORAGE | `local_data_exposure` | shared_prefs/sqlite/realm/keychain/plist/备份/日志/剪贴板 |
| CRYPTO | `crypto_and_secret_handling` | 硬编码密钥、自研 crypto、弱随机、secret_candidate 红线 |
| AUTH | `platform_login_exchange` / `session_token_lifecycle` / `signature_replay` | 三拆，同 XCX Batch10 模式 |
| NETWORK | `backend_web_api_testing` + 动态传输观察 | TLS/pinning/cleartext 观察进 `dynamic_mapping`，主动验证走审批门 |
| PLATFORM | `ipc_component_boundary` / `webview_bridge_links` | exported 组件、deeplink、JS 桥、universal link |
| CODE | `static_analysis` / `source_reconstruction` | 源码恢复、secrets、SDK、白盒 sink |
| RESILIENCE | `package_integrity_hardening_review` | 加固/混淆/反调试/完整性/热更新信任——只观察，不绕过 |
| PRIVACY | `third_party_sdk_platform_boundary` | 第三方 SDK 数据流、平台共享资产归属 |

APP 特有补充（超出 MASVS 但属授权评估必要）：`package_inventory`/`package_unpack_decompile`（壳识别与解包）、`host_classification`（host 归属与 scope，对齐 wz/xcx 状态机）、`dynamic_setup`/`dynamic_mapping`（设备代理基线）、`access_control_testing`（IDOR 复用）、`business_logic_testing`（复用 logic-workshop 语义）。

---

## 3. 三流隔离模型（硬约束）

| 项 | WZ | XCX | APP（新） |
|---|---|---|---|
| 游标文件 | `phase_status.json` | `phase_status.miniapp.json` | **`phase_status.app.json`** |
| stream 标识 | （网站主流程） | `miniapp_xcx` | **`app`** |
| identity 文件 | — | `miniapp.json` | **`app.json`**（platform/name/package_name/version/signing/operator/identity_status） |
| 脚本 | `init_engagement.py` / `audit_engagement.py` | `init_miniapp_engagement.py` / `audit_miniapp_engagement.py` | **`init_app_engagement.py` / `audit_app_engagement.py` / `phase_status_routing.py`** |
| 离线引擎 | — | `src/authorized_assessment/miniapp/` | **`src/authorized_assessment/app/`** |

- **命名规范（操作者指定）**：流程名一律小写 `app`——skill 目录 `.agents/skills/app/`、引擎包 `src/authorized_assessment/app/`、契约前缀 `app_`、游标 `phase_status.app.json`、身份文件 `app.json`、stream 值 `app`；中文显示名"APP 流程"，配方菜单键 `APP`。
- APP 只写 `phase_status.app.json`，永不读写 WZ/XCX 游标；routing fail-closed：工作区里缺 `phase_status.app.json` 时报 `APP_PHASE_STATUS_MISSING`，绝不回落到其他流的游标（克隆 `.agents/skills/xcx/scripts/phase_status_routing.py` 的 `resolve_phase_status` 语义，见 `phase_status_routing.py:62-89`）。
- 同资产单工作区：`init_app_engagement.py <input> --resume <workspace>`，与 xcx 相同（`init_miniapp_engagement.py:820-829` 的 resume 输入 hash 校验语义）；L 编号沿用 `<host-short>-L<N>` 按站点隔离。
- hosts.csv / scope 语义与 wz/xcx 完全一致：域级授权根域自动继承（`--scope-root`），精确子域/兄弟域/第三方/平台共享保持 pending；host 分类状态机不新造一套。

---

## 4. APP 阶段集（33 阶段，种子进 `phase_status.app.json`）

与 XCX 的 33 阶段同构（`init_miniapp_engagement.py:51-81` PHASES 常量），新增/改名处以粗体标注。`required=true`，状态枚举沿用 `pending / in_progress / complete / blocked / not_applicable`（not_applicable/blocked 必须带 reason，审计强制）。

| # | phase | 分支/工件要点 | 红线与门 |
|---|---|---|---|
| 1 | authorization | 种子即 complete，basis=`user_supplied_initial_target` | 同 xcx |
| 2 | identity | 应用名、包名（`com.*`）、版本、签名/证书指纹、分发渠道、开发者/备案线索 → `app.json` | 身份不明保持 pending，不阻塞离线分析 |
| 3 | platform_identification | android / ios / dual / other | 不把 Android 假设强加 iOS |
| 4 | material_acquisition | `materials.csv`（material_id/platform/type/path/sha256/provenance/analysis_status） | 原始包只留本地受限目录，分析用副本 |
| 5 | initial_decoding | 输入自动分类（apk/ipa/xapk/apks/链接/目录/流量导出）→ `artifacts/decoding-ledger.csv` | 全离线 |
| 6 | preflight | 工具发现：jadx/apktool/java 可用性、版本、输出路径 → `notes/runtime-inventory.md`；设备可用性登记（不连接） | 缺工具记录 unavailable，不临时下载替代 |
| 7 | package_inventory | `artifacts/app/package-inventory.csv`：dex 数量、so、assets、split/xapk、**加固识别**（libjiagu/libDexHelper/libexecmain/libshella 等特征 so，特征表见附录 F；iOS FairPlay encrypted 标志） | 加固识别=signal，不构成结论 |
| 8 | package_unpack_decompile | apktool（资源+manifest）+ jadx（dex→java）→ `artifacts/app/unpacked/<pkg>/`；iOS：未加密 ipa 的 Info.plist/class-dump 字符串 | **壳包 → blocked + 操作者决策；不自动脱壳**（见 §6 审批门） |
| 9 | source_reconstruction | `artifacts/source-map.csv`；AndroidManifest 深解析（权限、exported、intent-filter、allowBackup、debuggable、networkSecurityConfig、cleartext） | 记录未还原区域（负空间） |
| 10 | **package_integrity_hardening_review** | 分支：`package_version_inventory / signing_integrity / hardening_obfuscation_markers / debug_switches / debug_info_exposure / update_endpoint_environment（热更新/dex.zip 下载源）/ trusted_update_config` → `artifacts/app/package/hardening-review.json`（契约 `app_storage_package_schema`） | MASVS-RESILIENCE；**只观察记录，任何绕过=审批门** |
| 11 | static_analysis | secrets 模式（复用现有 secret 逻辑+app 特征：AK/SK、jpush/umeng/maps key）、第三方 SDK 清单及域名、API 路径提取、**白盒 sink 复用 `whitebox_triage.py` 62 条库** | secret_candidate 红线同 xcx |
| 12 | endpoint_inventory | `endpoints.csv`（client 端静态基线） | — |
| 13 | host_classification | 提取 host → `hosts.csv` + scope 对账；own backend / third_party / CDN / platform / vendor | 归属未确认=confirmation_required，禁主动请求 |
| 14 | **dynamic_setup**（重量级） | 指定测试设备登记、代理拓扑、用户 CA 信任观察（Android 7+ networkSecurityConfig 影响）、录屏约束 | **设备改动（root/越狱/装证书/装 frida-server）= 审批门** |
| 15 | dynamic_mapping（重量级） | 用户旅程→流量基线（endpoint/method/参数名/状态/结构，不留敏感值）；pinning/反调试/root 检测=控制观察记录 | **SSL pinning bypass、frida 注入=审批门**；429/5xx 退避即停 |
| 16 | static_dynamic_reconciliation | 五分支同 xcx（`static_endpoint_base / dynamic_endpoint_base / match_status_classification / hidden_flow_identification / stale_entry_disposition`）→ `artifacts/app/reconciliation/static-dynamic-endpoints.csv`，行级十态同 xcx | 纯离线对账，不发"验证"请求 |
| 17 | platform_login_exchange | 分支（app 语境）：`oauth_code_one_time / oauth_code_expiry / one_click_login_device_binding / access_token_custody / uid_authorization_basis` → `artifacts/app/auth/platform-login-review.json`（契约 `app_auth_schema`） | 只分析操作者提供材料/本地流量 |
| 18 | session_token_lifecycle | 五分支同 xcx：`token_rotation / token_revocation_logout / multi_device_login / stale_token_new_api / device_user_tenant_binding` → `artifacts/app/auth/session-lifecycle-review.json` | 不自动登录/签发/吊销 |
| 19 | signature_replay | 四分支同 xcx：`nonce_timestamp / signature_canonicalization / replay_window / binding_scope` → `artifacts/app/auth/signature-replay-review.json` | **永不自动重放任何请求（含读）** |
| 20 | backend_web_api_testing | 与 WZ 同构（endpoint-role-object 矩阵）；确认归属且 in_scope 的后端才可低速只读请求 | 写/导出/下载/支付=审批门 |
| 21 | access_control_testing | 只读 IDOR 差分，语义复用 `idor_triage.py`（同 host ≥2 凭证、GET/HEAD、delay≥3s、每 host≤5 端点、A 凭证 401/302 即停） | 需 ≥2 套授权会话；不足记 blocked |
| 22 | input_file_testing | 复用 wz `input_testing` 编排语义（候选筛查 only） | 不自动探测写型参数 |
| 23 | business_logic_testing | 复用 logic-workshop 状态机产物语义；只重建模型不发并发请求 | 真实支付/影响他人=禁止 |
| 24 | local_data_exposure | 五分支同 xcx：`token_persistence / logout_cleanup / local_cache_database / logs_clipboard_screenshots / temp_files` → `artifacts/app/storage/local-data-review.json`；行内 `platform` 列区分 android(shared_prefs/db/backup)/ios(keychain/plist/快照) | 只用操作者授权材料与指定测试设备 |
| 25 | crypto_and_secret_handling | 四分支同 xcx：`hardcoded_secrets / custom_crypto / weak_random_key_derivation / debug_config_env_keys` → `artifacts/app/crypto/secret-review.json` | **secret_candidate 红线**：未证实有效性只是线索 |
| 26 | webview_bridge_links | 七分支：`webview_allowed_domains / postmessage_origin / cookie_token_sharing_boundary / bridge_method_exposure / custom_scheme / deep_link_sensitive_params / external_app_browser_jump`；三 CSV 同 xcx Batch13（路径 `artifacts/app/webview/`） | 不注入/不重放 cookie/token |
| 27 | **ipc_component_boundary**（新增，App 特有） | 分支：`exported_activity / exported_service / exported_receiver / exported_provider / custom_scheme_deeplink / universal_link / ios_extension_boundary` → `artifacts/app/ipc/component-inventory.csv` + `deeplink-review-queue.csv`（契约 `app_ipc_schema`） | 静态清单离线完成；**实际触发写组件的 intent/deeplink=审批门** |
| 28 | cloud_function_testing | 三分支：`anonymous_invocation / function_parameter_role_validation / cloud_env_id_mixing` → `artifacts/app/cloud/cloud-function-review.json` | 对多数 App=not_applicable(带理由)；不触发写型函数 |
| 29 | cloud_storage_acl_testing | 三分支：`cloud_database_rules / object_storage_acl / signed_url_binding` → `artifacts/app/cloud/object-storage-review.json` | 不批量读对象 |
| 30 | third_party_sdk_platform_boundary | 分支同 xcx：`third_party_service_boundary / platform_shared_asset_attribution` → `artifacts/app/cloud/third-party-boundary.csv` | 不触发真实支付 |
| 31 | candidate_validation | 假设/预期行为/最小证明/负控/停止条件/审批需求/cleanup 全记录后才验证；八态结论模板 + 四问否决（同 wz/xcx SKILL 顶部） | confirmed 仍写 `needs_manual_validation`，人工终审门不可越 |
| 32 | reporting | 报告契约继承 xcx（同一 DOCX 模板固定结构；client/backend/platform/third-party 分节）；无可报告成果时 = not_applicable | 人工终审门不可越 |
| 33 | cleanup | 测试账号/对象/文件/会话/设备改动清理记录；cleanup 必须完成 | 未清理不得闭合 |

---

## 5. 文件全景清单（要创建/修改的每一个文件）

### 5.1 Skill（canonical + 双镜像，`check_skill_drift.py` 强制三处字节一致）

| 路径 | 新建/修改 | 作用 |
|---|---|---|
| `.agents/skills/app/SKILL.md` | 新建 | APP 流 skill 主文件。**全文底稿见 [APP_SKILL_DRAFT.md](APP_SKILL_DRAFT.md)**（含与 xcx 的逐节差异清单）。骨架逐条克隆 `.agents/skills/xcx/SKILL.md`（242 行）骨架：顶部 9 条硬约束（0 规则优先级 ~ 9 拒绝端到端）、AI 结论模板/四问否决/成立最小链条（原文照抄）、Session scope、目标接受与平台识别、workspace 创建、工具发现（登记 jadx/apktool 用法，禁止临时手写解包脚本）、一次一个 phase（读 `phase_status.app.json`）、台账清单、浏览器/Burp MCP 协议（照抄）、验收关闭（audit 命令）、Burp 输入节。**关键差异**：游标文件名、`dynamic_setup` 设备审批门、"壳包不自动脱壳"、iOS 材料受限的 blocked 语义 |
| `.agents/skills/app/references/workflow.md` | 新建 | 阶段字典（§4 的 33 阶段展开：每阶段覆盖范围/输入/工件/红线/MASTG 映射），克隆 xcx workflow.md 的 7 节结构（Intake routing → Initial decoding → Static → Dynamic → Backend/business → Validation/closure → Resume logic） |
| `.agents/skills/app/references/test-matrix.md` | 新建 | 覆盖索引：MASVS 八域 × Android/iOS × 分支矩阵（克隆 xcx test-matrix.md 的 Area/Coverage questions 表 + Required dimensions + 各 phase 分支表，增加 ipc/hardening 两节；每阶段按附录 G 锚定 MASTG-TEST ID） |
| `.agents/skills/app/references/data-to-test-playbook.md` | 新建 | 把 manifest 字段、源码线索、流量、设备观察转成具体测试：payload 按参数类型/角色/状态选择、配对正负控、canary 纪律（克隆 wz/xcx 同名文件的选型规则） |
| `.agents/skills/app/references/package-analysis.md` | 新建 | 包分支手册：apktool/jadx 标准命令（含实测参数，见 §7.1）、split/xapk/apks 处理、**加固特征识别表**（直接引用本文档附录 F，施工时随文件落到 package-analysis.md）、iOS 解密状态检查、解包失败→blocked 的记录格式 |
| `.agents/skills/app/references/artifact-contract.md` | 新建 | 工作区布局契约 + 报告契约（继承 xcx：用户 DOCX 模板固定结构、生成器禁写章节清单、canonical finding 字段、同资产同类别合并规则、`【请补充实际复现命令】` 规则） |
| `.agents/skills/app/references/evidence-reporting.md` | 新建 | 证据分级、脱敏最小化（3-5 条例外引用 ROE）、severity、cleanup、最终报告清单（克隆 xcx 同名文件改写） |
| `.agents/skills/app/scripts/init_app_engagement.py` | 新建 | 零网络初始化器（见 §7.2 规格） |
| `.agents/skills/app/scripts/audit_app_engagement.py` | 新建 | 只读审计器（见 §7.3 规格） |
| `.agents/skills/app/scripts/phase_status_routing.py` | 新建 | 三流路由（见 §7.4 规格） |
| `.claude/skills/app/**`、`.opencode/skills/app/**` | 新建（复制） | 客户端镜像，与 canonical 逐字节一致；`python scripts/check_skill_drift.py` 必须绿 |

### 5.2 契约（`contracts/`）

| 路径 | 作用 | 克隆源 |
|---|---|---|
| `contracts/app_auth_schema.json` | `platform_login_exchange / session_token_lifecycle / signature_replay` 三 phase 的分支、coverage_substatus 六值、observation/artifact 字段、authorization_basis_values、red_lines、invariants（12-key 形状） | `contracts/miniapp_auth_schema.json` |
| `contracts/app_storage_package_schema.json` | `package_integrity_hardening_review / local_data_exposure / crypto_and_secret_handling` 三 phase（含 secret_candidate 红线、`PACKAGE_NO_REPACKING_RULE` 对应的 `APP_NO_REPACKING_RULE`） | `contracts/miniapp_storage_package_schema.json` |
| `contracts/app_reconciliation_schema.json` | static_dynamic_reconciliation 五分支 + 十个行级 endpoint 状态枚举 | `contracts/miniapp_reconciliation_schema.json` |
| `contracts/app_ipc_schema.json` | **新增**：ipc_component_boundary 七分支 + `component-inventory.csv`/`deeplink-review-queue.csv` 字段（boundary_status 遵循 finding 八态） | `contracts/miniapp_webview_schema.json`（结构模板） |
| `contracts/app_webview_schema.json` | webview_bridge_links 三 CSV 字段（与 xcx 同构，路径改 `artifacts/app/webview/`） | `contracts/miniapp_webview_schema.json` |
| `contracts/app_cloud_schema.json` | cloud_function_testing / cloud_storage_acl_testing / third_party_platform_boundary | `contracts/miniapp_cloud_schema.json` |

`scripts/maintenance/validate_run_contracts.py` 的 REQUIRED 契约清单（该文件第 75-97 行区域）追加全部 `app_*.json`，并加 app 三模块引擎 ↔ 契约常量的漂移校验（同 miniapp_auth/miniapp_storage_package 现有校验行的模式）。

### 5.3 离线评审引擎（`src/authorized_assessment/app/`）

| 路径 | 作用 |
|---|---|
| `__init__.py` | 包声明 |
| `README.md` | 模块地图 + 复用边界说明 |
| `app_review_common.py` | 共享引擎（12-key review JSON 骨架、coverage_substatus 枚举、observation→evidence kind 判定、confirm 升级门），克隆 `src/authorized_assessment/miniapp/package_integrity_update.py` 的共享引擎模式 |
| `platform_login_exchange.py` | app 语境五分支；复用 `miniapp/platform_login_exchange.py` 引擎结构，分支常量取 `app_auth_schema` |
| `session_token_lifecycle.py` | 五分支（分支名与 xcx 相同，引擎可直接薄封装复用） |
| `signature_replay_review.py` | 四分支（同上） |
| `hardening_integrity_review.py` | 七分支（RESILIENCE 观察；产物 `hardening-review.json`） |
| `local_data_exposure.py` / `crypto_secret_review.py` | 薄封装复用 Batch11 引擎 + app 行内 platform 列 |
| `static_dynamic_reconciliation.py` | 薄封装复用 Batch12 对账引擎（十态分类确定性规则原样） |
| `webview_bridge_review.py` / `ipc_component_review.py` | 三 CSV / 两 CSV 清单引擎（克隆 xcx webview 模式） |
| `cloud_function_review.py` / `cloud_storage_review.py` / `third_party_boundary_review.py` | 薄封装复用 Batch12 云引擎 |
| `static_extraction.py` | 静态提取编排：apktool/jadx 子进程封装（超时/输出上限/hash 记录/失败→ledger）、manifest 深解析、secrets/SDK/API 路径模式、白盒 sink 调 `whitebox_triage.py --scan` 的薄包装 |

**复用边界（重要）**：分支常量不同的引擎（auth 平台登录分支、hardening 新增分支）复用"代码模式"而非直接 import miniapp 常量；契约↔引擎常量一致性由测试锁定（同 `tests/test_xcx_storage_package_phase_split.py` 模式）。

### 5.4 配方与路由（`prompts/`、`tools/copy_prompt.py`、`docs/CONTEXT_LOADING_MAP.yaml`）

| 路径 | 新建/修改 | 作用 |
|---|---|---|
| `prompts/配方APP_App流程.md` | 新建 | 克隆 `配方XCX_小程序流程.md`（56 行）结构：目标输入（APK/IPA/包名/市场链接/解包目录/流量）、抓包前置（Burp MCP 同款 list→只读 history 协议）、工具调用协议、init/恢复命令（`.agents/skills/app/scripts/init_app_engagement.py`）、读 `phase_status.app.json`+`app.json`+`materials.csv`+`hosts.csv`+`endpoints.csv`、一次一个 phase、网络与请求预算（同 xcx §网络预算原文）、结论边界（包内字符串/密钥候选/静态 sink=signal/candidate） |
| `prompts/配方P_提示词分发员.md` | 修改 | 输入识别加一行："App 名称/包名、APK/IPA/XAPK、已解包 App 目录、App 抓包流量或已有 APP engagement → 路由到 APP"；正式配方来源加 `prompts/配方APP_App流程.md`；加 "APP 路由规则" 节（游标 `phase_status.app.json`，不读写 wz/xcx 游标；设备/注入/脱壳=审批门） |
| `prompts/配方C_单目标深挖.md` | 修改 | 规则 1 与规则 6 的游标清单增补："APP 使用 `phase_status.app.json`（stream=app）"，共址工作区三流互不读写对方状态文件 |
| `tools/copy_prompt.py` | 修改 | `RECIPES` 加 `"APP": "配方APP_App流程.md"`；`ALIASES` 加 `"12": "APP"`（当前 `tools/copy_prompt.py:19-31`） |
| `D:\Desktop\AI配方_一键复制.bat`（桌面入口，位于仓库外，`launchers/` 无副本） | 修改 | echo 菜单文案 1-10 → 1-12，加 "12 = APP流程"（菜单数据源本身在 `tools/copy_prompt.py`，见上行） |
| `docs/CONTEXT_LOADING_MAP.yaml` | 修改 | `workflows:` 增 `app:` 段（skill 三件套，required true）；`phases:` 增 `app_*` 域条目（契约/引擎模块/锁定测试，required false）——schema 与 fh/wz/xcx 段一致，engagement 工作区文件不在 CLM 登记。草案见附录 D |

### 5.5 配置与登记（工具白名单落地）

| 路径 | 新建/修改 | 作用 |
|---|---|---|
| `tools/managed/app/jadx/1.5.6/**`、`tools/managed/app/apktool/3.0.3/apktool_3.0.3.jar` | **已完成（B0 预置）** | 静态解包/反编译工具，sha256 已登记并核对官方摘要 |
| `tools/tool_registry.json` | **已完成（B0 预置，+2 条 active）**；后续追加 `frida`/`objection`/`MobSF`/`FRIDA-DEXDump` 四条 **`unavailable`**（本地不存在，操作者放置并登记前不接入——同 ffuf 先例；草案见附录 H） | 本地工具登记（8 字段；`python scripts/maintenance/rebuild_tool_inventory.py --check` 退出码 0 才算完成） |
| `gov_exercise_config.json` → `tools` | 修改：加 `"jadx": ["{base}/tools/managed/app/jadx/1.5.6/bin/jadx.bat"]`、`"apktool": ["{base}/tools/managed/app/apktool/3.0.3/apktool_3.0.3.jar"]` | 运行时工具路径白名单（frida/objection **不进**此表，保持 unavailable，直到操作者放置） |
| `tool_strategy.json` → `phases` | 修改：追加 §4 全部 app 阶段条目（一主一备：离线评审类 primary=`manual_offline_review_orchestration_only` + backup=`manual_review`；解包类 primary=`apktool_jadx_managed` + backup=`manual_string_extraction`；动态类 primary=`manual_device_proxy_orchestration_only`） | 阶段-工具策略事实源（`AGENT_MANIFEST.md` 的输入） |
| `tool_strategy.json` → `approval_gated_phases` | 修改：新增 `device_instrumentation`（primary=`manual_frida_or_objection_only_when_approved`，backup_mode=disabled）、`app_hardened_unpack`（primary=`manual_operator_supplied_unpacked_material_only`） | 设备注入与脱壳 = 双钥匙门，默认关闭 |
| `AGENT_MANIFEST.md` | 重生成（`python scripts/gen_agent_manifest.py`，勿手改） | 机器可读工具清单同步 |

### 5.6 导航与台账文档

| 路径 | 修改 |
|---|---|
| `AGENTS.md` | 入口表加 `prompts\配方APP_App流程.md` 行；"深入阅读" skills 列表 `.claude\skills\{wz,xcx,fh}` → `{wz,xcx,app,fh}`；运行时表不动；"施工中"段指向 CONSTRUCTION_STATUS W15+ |
| `README.md`、`docs/PROJECT_STRUCTURE.md` | skills/流程描述加 APP（PROJECT_STRUCTURE 的 Skill 行说明三镜像规则不变） |
| `CONSTRUCTION_STATUS.md` | 新增 W15-W20 工单行（见 §8 批次划分），格式同现有表 |
| `D:\Desktop\PROJECT_OVERVIEW_FOR_NEW_SESSIONS.md`（仓库外桌面导航文件，如仍维护） | 路由表（§11.1）/工作流节加 APP 行 |
| `docs/APP_CONSTRUCTION_ACCEPTANCE.md` | 新建（B1 验收会话创建） | APP 流 B1-B9 验收记录台账：批次/日期/结论(通过·打回)/逐项证据/验收会话；打回后同批次复验追加"复验"记录 |

### 5.7 测试（`tests/`）

| 路径 | 锁定内容 |
|---|---|
| `tests/test_app_phase_status_routing.py` | `phase_status.app.json` 解析、缺失时 fail-closed、绝不回落 wz/xcx 游标 |
| `tests/test_app_init_engagement.py` | 骨架文件齐全、零网络（无网络库调用断言）、resume 输入 hash 校验、33 phase 种子与 substatuses |
| `tests/test_app_audit_engagement.py` | fail-closed：分支未记录/缺 artifact/缺 reason/confirmed 无证据 → 拒绝闭合 |
| `tests/test_app_contract_sync.py` | `contracts/app_*.json` 分支/产物路径 ↔ `src/authorized_assessment/app/*` 常量 ↔ init 种子三处同源 |
| `tests/test_app_triple_stream_isolation.py` | wz/xcx/app 三流在同一共址工作区互不读写对方游标 |

### 5.8 Workspace 运行时布局（init 产物，全部本地 git 忽略）

```text
engagements/<目标名-日期>/
├── engagement.json            # 授权/安全控制/初始化零网络声明（同 xcx 字段）
├── app.json                   # platform/name/package_name/version/signing/operator/identity_status
├── phase_status.app.json      # APP 游标（stream=app，33 phase + substatuses）
├── scope.csv / hosts.csv / endpoints.csv / materials.csv / review_ledger.csv
├── materials/original|working/
├── artifacts/
│   ├── decoding-ledger.csv / package-inventory.csv / source-map.csv
│   ├── app/unpacked/<package_name>/        # apktool+jadx 输出（本地受限）
│   ├── app/package/hardening-review.json
│   ├── app/auth/platform-login-review.json 等 3 件
│   ├── app/reconciliation/static-dynamic-endpoints.csv
│   ├── app/storage|crypto|webview|ipc|cloud/…（各 review 产物/清单 CSV）
├── evidence/raw|redacted/ + evidence/index.csv
├── notes/target-model.md / operator_tasks.md / safety-controls.md / phase-history/
├── logs/  sessions/
└── reports/攻防成果报告_<engagement>_<日期>.docx + final-report.md（工作稿）
```

---

## 6. APP 特有审批门与红线（写入 SKILL/配方/契约 red_lines）

全部继承 ROE 3.2/3.3 与 blocked_actions 全表，另加移动端特有：

1. **设备类（双钥匙）**：root/越狱指定测试设备、安装用户 CA、安装 frida-server、装测试版 APK、修改系统设置。仅观察"设备是否已 root/pinning 是否存在"免批；**任何主动绕过（SSL pinning bypass、反调试 patch、frida 注入、重打包）= 审批门**，且绕过本身是测试技术不是漏洞结论。
2. **加固脱壳**：壳包解包默认 `blocked`；唯一路径是操作者提供已脱壳材料（登记 provenance）或显式批准后在指定设备执行——工具（FRIDA-DEXDump/BlackDex 等）registry 保持 `unavailable` 直到操作者放置。
3. **凭证与设备身份**：运营商一键登录 token、device-id、Android ID/IDFA/IDFV 属凭证纪律范围；不进报告/ledger/交接。
4. **动态流量**：同 xcx 预算（同 host 串行、间隔≥2s、429/5xx 退避 10s、连续 5 错停 host；认证态并发 1、GET/HEAD、每目标≤10 次）；**signature_replay 永不自动重放任何请求**。
5. **数据**：本地数据/抓包只留本地受限目录；3-5 条最小证明例外按 ROE 4 原样执行。
6. **iOS 在 Windows 的边界**：无解密能力 → 加密 ipa 记 `blocked`（原因 `ios_fairplay_encrypted`），不得静默 not_applicable；iTunes 备份/操作者提供材料是后备输入。

---

## 7. 三个脚本的施工规格

### 7.1 标准命令（写入 package-analysis.md 与 static_extraction.py）

```text
# 资源+manifest 解码（java -jar，已实测 3.0.3）
java -jar tools/managed/app/apktool/3.0.3/apktool_3.0.3.jar d -f -o <ws>/artifacts/app/apktool/<pkg> <material.apk>
# dex→java 反编译（已实测 1.5.6，用天狐 Java 11）
tools/managed/app/jadx/1.5.6/bin/jadx.bat -d <ws>/artifacts/app/unpacked/<pkg> --deobf-min 3 --deobf-max 9 <material.apk>
# 白盒 sink（复用现有库）
.venv/Scripts/python.exe whitebox_triage.py --source-dir <ws>/artifacts/app/unpacked/<pkg> --out-dir <ws>/artifacts/whitebox --scan
```

子进程纪律：超时（默认 600s/包）、输出行数上限、stderr 落 `logs/`、失败写 `decoding-ledger.csv`（failed + 原因），不静默。

### 7.2 `init_app_engagement.py`（克隆 xcx init 的 1079 行骨架）

- CLI：`<input>`（APK/IPA/XAPK/包名/市场链接/目录/流量文件/URL）+ `--output` + `--platform auto|android|ios|dual|other` + `--name/--package/--operator/--version` + `--authorization-ref/--window/--rules/--rate` + `--scope-root` + `--resume` + `--allow-parallel`。
- `classify_input()` 按后缀/内容识别 8 类输入；包文件算 sha256。
- 建 §5.8 全部骨架（`write_*_if_missing` 幂等；resume 补种）。
- `phase_status.app.json` 种子：33 phase（附录 B 骨架），authorization=complete；`app.json` identity 字段齐全时 identity/platform_identification=complete；hardening/auth/reconciliation/webview/ipc/cloud 相应 phase 种 substatuses 空串。
- 顶部断言 `network_accessed_by_initializer: false`。

### 7.3 `audit_app_engagement.py`（克隆 xcx audit 的 1167 行检查体系）

- 游标经 `phase_status_routing.py` 解析（fail-closed）。
- 复用 xcx 的检查族：`_review_phase_issues`（12-key review JSON 完整性）、`_recorded_substatus_issues`（六值枚举）、`_csv_artifact_issues/_csv_completion_issues`（tested 需 ≥1 行、not_applicable 需 reason）、`_check_reconciliation_row`（十态行级 + judgment 行必须有 reason）、`webview/ipc` 行校验、`reportable_review_items`（active 候选必须有 disposition）、证据引用存在性、cleanup/report 闭合。
- 输出：文本/`--json`，退出码非 0 = 不可闭合。

### 7.4 `phase_status_routing.py`

克隆 xcx 97 行结构：`APP_PHASE_STATUS_FILENAME="phase_status.app.json"`、`APP_STREAM="app"`、`_APP_PHASE_HINTS`（app 特有阶段名集合）、`resolve_phase_status(root, for_write)` 与 `route_metadata()`；删除 xcx 的 legacy 单流回退逻辑（APP 无历史包袱）。

> **设计已原型验证（2026-09-07，临时目录四用例）**：① 共址 wz+xcx 游标、缺 app 游标 → `APP_PHASE_STATUS_MISSING` 且不返回任何路径；② `for_write=True` 只提议 `phase_status.app.json`；③ app 游标在场 → 解析自身 stream，不读 wz；④ stream 字段缺失时防御性默认 `app`。B2 施工按此实现并由 `tests/test_app_phase_status_routing.py` 锁定。

---

## 8. 施工批次（B1-B9，含验收；B0 已完成）

**批次运行规则**：每批开工＝新会话整段粘贴附录 I 对应施工提示词；完工后＝另开独立会话粘贴附录 J 对应验收提示词；**上一批未验收通过，下一批不得开工**。验收记录统一落 `docs/APP_CONSTRUCTION_ACCEPTANCE.md`（由 B1 验收会话首次创建，表头：批次/日期/结论/逐项证据/验收会话）。B0 已完成并记 W15，无需提示词。

| 批次 | 内容 | 涉及文件 | 验收 | 预估 |
|---|---|---|---|---|
| **B0 前置（✅ 已完成 2026-09-07）** | 工具下载落位+校验+登记+白名单并入 | `tools/managed/app/**`、`tools/tool_registry.json`(+2 active+config_key)、`gov_exercise_config.json` tools(+2)、`tool_strategy.json`(+17 阶段 +2 审批门)、`AGENT_MANIFEST.md` 重生成(66 阶段) | `rebuild_tool_inventory.py --check`=0；`validate_run_contracts.py`=0；`check_doc_drift.py`=0；jadx/apktool `--version` 实测 | 已完成 |
| **B1 Skill 骨架** | SKILL.md（底稿：`docs/APP_SKILL_DRAFT.md`）+ 全部 6 个 references（workflow/test-matrix/data-to-test/package-analysis/artifact-contract/evidence-reporting；附录 F/G 随文件落地）+ 双镜像 | §5.1 全部非脚本 7 件 + 2 个镜像目录（提示词：附录 I-B1，验收：附录 J-B1） | `check_skill_drift.py`=0；底稿差异清单逐项核对；33 阶段名与 MASTG 锚点齐全 | 2.5h |
| **B2 init + 路由** | init_app_engagement.py + phase_status_routing.py + 测试 | §5.1 脚本 2 件 + `tests/test_app_phase_status_routing.py`、`test_app_init_engagement.py`、`test_app_triple_stream_isolation.py` | `pytest tests/test_app_* -q` 全绿；临时目录建区实测 | 2h |
| **B3 audit** | audit_app_engagement.py + 测试 | §5.1 脚本 1 件 + `tests/test_app_audit_engagement.py` | 正例+3 个负例（缺 reason/缺 artifact/缺 disposition）全绿 | 2h |
| **B4 契约** | 6 个 `contracts/app_*.json` + validate_run_contracts 接入 | §5.2 + 校验器修改 | `python scripts/maintenance/validate_run_contracts.py` 退出 0 + 负例 | 1.5h |
| **B5 静态引擎** | app_review_common + hardening/static_extraction/webview/ipc 模块 + 契约同步测试 | §5.3 前 6 件 + `tests/test_app_contract_sync.py` | pytest 全绿；用一个**本地无害样本 APK**（labs/ 或操作者提供）走 init→preflight→package_inventory→unpack→static 演练 | 2.5h |
| **B6 认证/对账/云引擎** | auth 三模块 + reconciliation + local/crypto + cloud 三模块（薄封装） | §5.3 其余 | pytest 全绿；`validate_run_contracts.py` 仍绿 | 2h |
| **B7 配方与导航** | 配方APP（底稿：`docs/APP_SKILL_DRAFT.md` 第二节）+ 配方P/C + copy_prompt + bat 菜单 + CONTEXT_LOADING_MAP + AGENTS/README/PROJECT_STRUCTURE/CONSTRUCTION_STATUS(W15-W20 标注进度) + OVERVIEW | §5.4 + §5.6 + 附录 C/D | `check_doc_drift.py` 退出 0；copy_prompt --list 显示 APP | 1h |
| **B8 端到端离线验收** | 全链演练 | — | `python -m pytest -q` 全绿；`verify_offline.py --json` 无违例；样本 APK 从 init 推进到 static_analysis，audit 通过，游标/交接提示词正确 | 1h |
| **B9 Graph/编排接入（W21）** | `contracts/app_graph_schema.json` + `src/authorized_assessment/orchestration/app_graph.py` + tests/{test_app_graph.py, test_app_graph_integration.py, test_app_graph_phase_status_isolation.py}（克隆 xcx graph 测试模式）+ validate_run_contracts 接入 graph 契约 | contracts + orchestration + tests（提示词：附录 I-B9，验收：附录 J-B9） | 新增 graph 测试全绿（含三流隔离）；全量 pytest 回归；validator=0 | 2h |

合计约 17h（含 B9；B1/B7 已有全文底稿提速）。每批完成后由对应验收提示词记录结论，全部通过即 APP 流程建设闭环。每批次一次会话、一次提交，遵循 W5+ 的"落地即更新 CONSTRUCTION_STATUS"约定。

---

## 9. 本次会话已完成的预置（透明清单）

1. **工具预置**（操作者已授权下载；均为离线分析工具，不接触目标）：
   - `tools/managed/app/jadx/1.5.6/jadx-1.5.6.zip` + 已解包 `bin/ lib/`；sha256 `545ea2be…e8974` 与 GitHub API 官方摘要一致；`--version` → 1.5.6（天狐 Java 11.0.2）。
   - `tools/managed/app/apktool/3.0.3/apktool_3.0.3.jar`；sha256 `dbf930b0…f9423`；`--version` → 3.0.3（同 Java）。
2. **registry 登记**：`tools/tool_registry.json` 追加 `jadx`、`apktool` 两条 active（8 字段 + sha256 + 已验证备注）；`rebuild_tool_inventory.py --check` 通过（"结构完整、status 与盘上路径一致、config 候选表全覆盖、tool_strategy 引用无漂移"），工具总数 32→34。
3. **工具白名单并入（B0 配置编辑完成）**：`gov_exercise_config.json` tools 增 `jadx`/`apktool` 候选路径；`tool_strategy.json` 增 17 个 `app_*` 阶段条目 + `device_instrumentation`/`app_hardened_unpack` 两个审批门（纯追加 +212 行，未动用户既有改动）；逻辑工具名按校验器规则定为 `manual_*` 前缀/根脚本名/`none_by_default`；registry 两条目补 `config_key`；`AGENT_MANIFEST.md` 重新生成。验收全绿：`rebuild_tool_inventory.py --check`=0、`validate_run_contracts.py`=0、`check_doc_drift.py`=0。

---

## 10. 风险与开放问题

| # | 风险/问题 | 处置 |
|---|---|---|
| 1 | 加固壳包无法静态还原 | `blocked` 语义 + 脱壳审批门 + 工具 unavailable 登记（§6.2）；操作者提供脱壳材料是首选路径 |
| 2 | iOS 材料在 Windows 受限 | FairPlay 加密 → blocked(ios_fairplay_encrypted)；备份/操作者材料为后备；不虚报 not_applicable |
| 3 | frida/objection/MobSF 引入的设备与合规风险 | 全部保持 registry `unavailable`；`device_instrumentation` 审批门默认关闭；操作者放置并报备后才可 active |
| 4 | 动态分析需要设备 | `dynamic_setup` 为重量级阶段：无指定测试设备 → 该分支 pending，不阻塞静态流 |
| 5 | 与 miniapp 引擎的常量漂移 | 分支常量以 `contracts/app_*.json` 为唯一事实源，三处（契约/引擎/init 种子）由 `test_app_contract_sync` 锁定 |
| 6 | B9 graph/orchestration 集成牵涉 worker 合同 | 列为可延后独立工单，不阻塞 APP 流的 AI 会话使用 |
| 7 | 当前工作树有大量未提交改动 | 施工各批独立提交，不回滚/覆盖任何现有修改（PROJECT_STRUCTURE 整理约束 3） |

---

## 11. 验收基线（B8 完成定义）

1. `.agents/skills/app/` 十件齐全且三镜像 drift=0；
2. `pytest tests/test_app_* -q` 全绿、全量 `pytest -q` 不回归；
3. `validate_run_contracts.py`、`rebuild_tool_inventory.py --check`、`check_skill_drift.py`、`check_doc_drift.py` 全部退出 0；
4. 样本 APK 端到端演练：init → preflight → package_inventory → package_unpack_decompile → source_reconstruction → static_analysis → host_classification 各留 phase note + target-model 更新，audit 通过，交接提示词可让新会话零上下文续跑；
5. AGENT_MANIFEST/CONSTRUCTION_STATUS/AGENTS.md/配方P 均反映 APP 流存在。

---

## 附录 A：`tool_strategy.json` app 条目草案（B0 施工时逐条并入，`app_` 前缀避免与 xcx 同名条目冲突）

> 通用阶段（authorization/identity/platform_identification/material_acquisition/initial_decoding/preflight/package_inventory/source_reconstruction/endpoint_inventory/host_classification/candidate_validation/reporting/cleanup）不在 phases 表单列条目，随 skill 审计闭合（解包与静态提取分别由 `app_package_unpack`/`app_static_extraction` 覆盖）；下表只登记有工具/引擎映射的阶段。

```json
{
  "phases": {
    "app_package_unpack": {
      "primary": "apktool_jadx_managed",
      "backup": "manual_string_extraction",
      "backup_mode": "sample_or_confirm",
      "notes": "apktool 3.0.3(manifest/资源)+jadx 1.5.6(dex→java)，均为 registry active 管理内工具；壳包解包失败记 blocked，不自动脱壳；子进程超时/输出上限/失败写 decoding-ledger（skills/app/references/package-analysis.md）。"
    },
    "app_static_extraction": {
      "primary": "manual_offline_review_orchestration_only",
      "backup": "whitebox_triage.py_sink_scan",
      "backup_mode": "offline_review_only",
      "notes": "manifest 深解析(权限/exported/intent-filter/allowBackup/networkSecurityConfig)、secrets/SDK/API 路径模式提取；白盒 sink 复用 whitebox_triage.py 62 条库；secret_candidate 红线；duplicate_execution=false。"
    },
    "app_hardening_integrity_review": {
      "primary": "manual_offline_review_orchestration_only",
      "backup": "manual_review",
      "backup_mode": "offline_review_only",
      "notes": "七分支(signing_integrity/hardening_obfuscation_markers/debug_switches/debug_info_exposure/update_endpoint_environment/trusted_update_config/package_version_inventory)；MASVS-RESILIENCE 只观察不绕过；任何 bypass=approval_gated_phases.device_instrumentation。"
    },
    "app_dynamic_setup": {
      "primary": "manual_device_proxy_orchestration_only",
      "backup": "manual_review",
      "backup_mode": "operator_device_prerequisite",
      "notes": "重量级：指定测试设备登记、代理拓扑、用户 CA 信任观察(Android 7+ networkSecurityConfig)；root/越狱/装证书/装 frida-server=审批门；无设备时该阶段 pending，不阻塞静态流。"
    },
    "app_dynamic_mapping": {
      "primary": "manual_device_proxy_orchestration_only",
      "backup": "manual_review",
      "backup_mode": "operator_device_prerequisite",
      "notes": "用户旅程→流量基线，只存 endpoint/method/参数名/状态/结构；pinning/反调试/root 检测=控制观察记录；SSL pinning bypass 与 frida 注入=审批门；429/5xx 退避 10s、连续 5 错停 host。"
    },
    "app_static_dynamic_reconciliation": {
      "primary": "manual_offline_review_orchestration_only",
      "backup": "manual_review",
      "backup_mode": "offline_review_only",
      "notes": "五分支+十态行级枚举，确定性分类与 miniapp Batch12 同构（契约 app_reconciliation_schema）；纯离线对账，永不发新请求验证 unreachable/stale 行；duplicate_execution=false。"
    },
    "app_platform_login_exchange": {
      "primary": "manual_offline_review_orchestration_only",
      "backup": "manual_review",
      "backup_mode": "offline_review_only",
      "notes": "五分支(oauth_code_one_time/oauth_code_expiry/one_click_login_device_binding/access_token_custody/uid_authorization_basis)（契约 app_auth_schema）；只分析操作者提供材料或本地流量；运营商一键登录 token/device-id 属凭证纪律。"
    },
    "app_session_token_lifecycle": {
      "primary": "manual_offline_review_orchestration_only",
      "backup": "manual_review",
      "backup_mode": "offline_review_only",
      "notes": "五分支与 xcx 同名(token_rotation/token_revocation_logout/multi_device_login/stale_token_new_api/device_user_tenant_binding)；不自动登录/签发/吊销；写动作审批门；duplicate_execution=false。"
    },
    "app_signature_replay": {
      "primary": "manual_offline_review_orchestration_only",
      "backup": "manual_review",
      "backup_mode": "offline_review_only",
      "notes": "四分支与 xcx 同名(nonce_timestamp/signature_canonicalization/replay_window/binding_scope)；永不自动重放任何请求(含读)；写与并发验证=审批门；duplicate_execution=false。"
    },
    "app_local_data_exposure": {
      "primary": "manual_offline_review_orchestration_only",
      "backup": "manual_review",
      "backup_mode": "offline_review_only",
      "notes": "五分支与 xcx 同名，行内 platform 列区分 android(shared_prefs/db/allowBackup 提取面)/ios(keychain/plist/快照)；只用操作者授权材料与指定测试设备；敏感值不进任何产物（契约 app_storage_package_schema）。"
    },
    "app_crypto_and_secret_handling": {
      "primary": "manual_offline_review_orchestration_only",
      "backup": "manual_review",
      "backup_mode": "offline_review_only",
      "notes": "四分支与 xcx 同名；secret_candidate 红线：未证实有效性的密钥串只是 signal；不做 key 有效性探测、不发请求（契约 app_storage_package_schema）；duplicate_execution=false。"
    },
    "app_webview_bridge_links": {
      "primary": "manual_offline_review_orchestration_only",
      "backup": "manual_review",
      "backup_mode": "offline_review_only",
      "notes": "三分支 CSV 与 xcx Batch13 同构，路径改 artifacts/app/webview/；七分支一行一分支；不注入/不重放 cookie/token，不从 deeplink 启动外部应用（契约 app_webview_schema）。"
    },
    "app_ipc_component_boundary": {
      "primary": "manual_offline_review_orchestration_only",
      "backup": "manual_review",
      "backup_mode": "offline_review_only",
      "notes": "App 特有七分支(exported_activity/service/receiver/provider/custom_scheme_deeplink/universal_link/ios_extension_boundary)→artifacts/app/ipc/ 两 CSV（契约 app_ipc_schema）；静态清单离线；实际触发写组件的 intent/deeplink=审批门。"
    },
    "app_cloud_function_testing": {
      "primary": "manual_offline_review_orchestration_only",
      "backup": "manual_review",
      "backup_mode": "offline_review_only",
      "notes": "三分支与 xcx 同名（契约 app_cloud_schema）；多数 App=not_applicable(带理由)；最小只读验证，不触发写型函数；duplicate_execution=false。"
    },
    "app_cloud_storage_acl_testing": {
      "primary": "manual_offline_review_orchestration_only",
      "backup": "manual_review",
      "backup_mode": "offline_review_only",
      "notes": "三分支与 xcx 同名；signed_url_binding 不批量读/下载对象内容；duplicate_execution=false。"
    },
    "app_third_party_sdk_platform_boundary": {
      "primary": "manual_offline_review_orchestration_only",
      "backup": "manual_review",
      "backup_mode": "offline_review_only",
      "notes": "两分支与 xcx 同名（推送/统计/地图/支付 SDK 边界 + 平台共享资产归属）；不触发真实支付；boundary CSV 行归属对齐 hosts.csv 分类状态。"
    },
    "app_backend_web_api_testing": {
      "primary": "manual_orchestration_only",
      "backup": "api_endpoint_confirm.py_plus_idor_triage.py",
      "backup_mode": "reuse_wz_modules_same_host_only",
      "notes": "仅确认归属且 in_scope 的自有后端；api_endpoint_confirm 风险词跳过表与 idor_triage 限制(同 host≥2 凭证、GET/HEAD、delay≥3s、每 host≤5 端点、A 凭证 401/302 即停)原样适用；写/导出/支付=审批门。"
    }
  },
  "approval_gated_phases": {
    "device_instrumentation": {
      "primary": "manual_frida_or_objection_only_when_approved",
      "backup": "manual_device_observation",
      "backup_mode": "disabled",
      "notes": "root/越狱、装用户 CA、frida-server、重打包、SSL pinning bypass、反调试 patch：脚本审批门+会话内人工显式确认，双钥匙缺一不可；绕过是测试技术不是漏洞结论；工具未放置前 registry 保持 unavailable。"
    },
    "app_hardened_unpack": {
      "primary": "manual_operator_supplied_unpacked_material_only",
      "backup": "none_by_default",
      "backup_mode": "disabled",
      "notes": "加固壳包默认 blocked；脱壳(FRIDA-DEXDump/BlackDex 等)需指定测试设备+显式批准；工具 registry 登记 unavailable 直到操作者放置并报备。"
    }
  }
}
```

`gov_exercise_config.json` → `tools` 追加（frida/objection/MobSF/FRIDA-DEXDump 不进此表，仅在 `tools/tool_registry.json` 登记 `unavailable`，操作者放置并报备前不接入）：

```json
"jadx": ["{base}/tools/managed/app/jadx/1.5.6/bin/jadx.bat"],
"apktool": ["{base}/tools/managed/app/apktool/3.0.3/apktool_3.0.3.jar"]
```

## 附录 B：`phase_status.app.json` 种子骨架（33 阶段，已验证 JSON 合法）

```json
{
  "schema_version": "1.0",
  "stream": "app",
  "status_file": "phase_status.app.json",
  "current_phase": "authorization",
  "next_phase": "identity",
  "last_completed_phase": "",
  "updated_at": "<created>",
  "phases": [
    {"phase": "authorization", "required": true, "status": "complete", "reason": "<authorization_ref>", "artifacts": ["engagement.json"], "updated_at": "<created>"},
    {"phase": "identity", "required": true, "status": "pending", "reason": "", "artifacts": ["app.json"], "updated_at": ""},
    {"phase": "platform_identification", "required": true, "status": "pending", "reason": "", "artifacts": ["app.json"], "updated_at": ""},
    {"phase": "material_acquisition", "required": true, "status": "pending", "reason": "", "artifacts": [], "updated_at": ""},
    {"phase": "initial_decoding", "required": true, "status": "pending", "reason": "", "artifacts": ["artifacts/decoding-ledger.csv"], "updated_at": ""},
    {"phase": "preflight", "required": true, "status": "pending", "reason": "", "artifacts": [], "updated_at": ""},
    {"phase": "package_inventory", "required": true, "status": "pending", "reason": "", "artifacts": ["artifacts/app/package-inventory.csv"], "updated_at": ""},
    {"phase": "package_unpack_decompile", "required": true, "status": "pending", "reason": "", "artifacts": ["artifacts/app/unpacked"], "updated_at": ""},
    {"phase": "source_reconstruction", "required": true, "status": "pending", "reason": "", "artifacts": ["artifacts/source-map.csv"], "updated_at": ""},
    {"phase": "package_integrity_hardening_review", "required": true, "status": "pending", "reason": "", "artifacts": ["artifacts/app/package/hardening-review.json"], "updated_at": "",
     "substatuses": {"package_version_inventory": "", "signing_integrity": "", "hardening_obfuscation_markers": "", "debug_switches": "", "debug_info_exposure": "", "update_endpoint_environment": "", "trusted_update_config": ""}},
    {"phase": "static_analysis", "required": true, "status": "pending", "reason": "", "artifacts": [], "updated_at": ""},
    {"phase": "endpoint_inventory", "required": true, "status": "pending", "reason": "", "artifacts": ["endpoints.csv"], "updated_at": ""},
    {"phase": "host_classification", "required": true, "status": "pending", "reason": "", "artifacts": ["hosts.csv"], "updated_at": ""},
    {"phase": "dynamic_setup", "required": true, "status": "pending", "reason": "", "artifacts": [], "updated_at": ""},
    {"phase": "dynamic_mapping", "required": true, "status": "pending", "reason": "", "artifacts": [], "updated_at": ""},
    {"phase": "static_dynamic_reconciliation", "required": true, "status": "pending", "reason": "", "artifacts": ["artifacts/app/reconciliation/static-dynamic-endpoints.csv"], "updated_at": "",
     "substatuses": {"static_endpoint_base": "", "dynamic_endpoint_base": "", "match_status_classification": "", "hidden_flow_identification": "", "stale_entry_disposition": ""}},
    {"phase": "platform_login_exchange", "required": true, "status": "pending", "reason": "", "artifacts": ["artifacts/app/auth/platform-login-review.json"], "updated_at": "",
     "substatuses": {"oauth_code_one_time": "", "oauth_code_expiry": "", "one_click_login_device_binding": "", "access_token_custody": "", "uid_authorization_basis": ""}},
    {"phase": "session_token_lifecycle", "required": true, "status": "pending", "reason": "", "artifacts": ["artifacts/app/auth/session-lifecycle-review.json"], "updated_at": "",
     "substatuses": {"token_rotation": "", "token_revocation_logout": "", "multi_device_login": "", "stale_token_new_api": "", "device_user_tenant_binding": ""}},
    {"phase": "signature_replay", "required": true, "status": "pending", "reason": "", "artifacts": ["artifacts/app/auth/signature-replay-review.json"], "updated_at": "",
     "substatuses": {"nonce_timestamp": "", "signature_canonicalization": "", "replay_window": "", "binding_scope": ""}},
    {"phase": "backend_web_api_testing", "required": true, "status": "pending", "reason": "", "artifacts": [], "updated_at": ""},
    {"phase": "access_control_testing", "required": true, "status": "pending", "reason": "", "artifacts": [], "updated_at": ""},
    {"phase": "input_file_testing", "required": true, "status": "pending", "reason": "", "artifacts": [], "updated_at": ""},
    {"phase": "business_logic_testing", "required": true, "status": "pending", "reason": "", "artifacts": [], "updated_at": ""},
    {"phase": "local_data_exposure", "required": true, "status": "pending", "reason": "", "artifacts": ["artifacts/app/storage/local-data-review.json"], "updated_at": "",
     "substatuses": {"token_persistence": "", "logout_cleanup": "", "local_cache_database": "", "logs_clipboard_screenshots": "", "temp_files": ""}},
    {"phase": "crypto_and_secret_handling", "required": true, "status": "pending", "reason": "", "artifacts": ["artifacts/app/crypto/secret-review.json"], "updated_at": "",
     "substatuses": {"hardcoded_secrets": "", "custom_crypto": "", "weak_random_key_derivation": "", "debug_config_env_keys": ""}},
    {"phase": "webview_bridge_links", "required": true, "status": "pending", "reason": "", "artifacts": ["artifacts/app/webview/webview-origin-inventory.csv", "artifacts/app/webview/bridge-method-inventory.csv", "artifacts/app/webview/deep-link-review-queue.csv"], "updated_at": "",
     "substatuses": {"webview_allowed_domains": "", "postmessage_origin": "", "cookie_token_sharing_boundary": "", "bridge_method_exposure": "", "custom_scheme": "", "deep_link_sensitive_params": "", "external_app_browser_jump": ""}},
    {"phase": "ipc_component_boundary", "required": true, "status": "pending", "reason": "", "artifacts": ["artifacts/app/ipc/component-inventory.csv", "artifacts/app/ipc/deeplink-review-queue.csv"], "updated_at": "",
     "substatuses": {"exported_activity": "", "exported_service": "", "exported_receiver": "", "exported_provider": "", "custom_scheme_deeplink": "", "universal_link": "", "ios_extension_boundary": ""}},
    {"phase": "cloud_function_testing", "required": true, "status": "pending", "reason": "", "artifacts": ["artifacts/app/cloud/cloud-function-review.json"], "updated_at": "",
     "substatuses": {"anonymous_invocation": "", "function_parameter_role_validation": "", "cloud_env_id_mixing": ""}},
    {"phase": "cloud_storage_acl_testing", "required": true, "status": "pending", "reason": "", "artifacts": ["artifacts/app/cloud/object-storage-review.json"], "updated_at": "",
     "substatuses": {"cloud_database_rules": "", "object_storage_acl": "", "signed_url_binding": ""}},
    {"phase": "third_party_sdk_platform_boundary", "required": true, "status": "pending", "reason": "", "artifacts": ["artifacts/app/cloud/third-party-boundary.csv"], "updated_at": "",
     "substatuses": {"third_party_service_boundary": "", "platform_shared_asset_attribution": ""}},
    {"phase": "candidate_validation", "required": true, "status": "pending", "reason": "", "artifacts": [], "updated_at": ""},
    {"phase": "reporting", "required": true, "status": "pending", "reason": "", "artifacts": ["reports/final-report.md"], "updated_at": ""},
    {"phase": "cleanup", "required": true, "status": "pending", "reason": "", "artifacts": [], "updated_at": ""}
  ]
}
```

## 附录 C：`prompts/配方P_提示词分发员.md` 修改文本（B7 粘贴）

输入识别节追加一行：

```text
- App 名称/包名、APK/IPA/XAPK 文件、已解包 App 目录、App 抓包流量或已有 APP engagement：路由到 APP；
```

正式配方来源节追加：

```text
- APP：`prompts/配方APP_App流程.md`
```

新增路由规则节（XCX 节之后）：

```markdown
## APP 路由规则

操作员提供 APK/IPA/XAPK、包名、应用市场链接、已解包 App 目录或 App 抓包流量。APP 使用
`phase_status.app.json`（stream=app），不得读写 WZ 的 `phase_status.json` 或 XCX 的
`phase_status.miniapp.json`。静态解包用登记内 jadx/apktool（tools/tool_registry.json active 项）；
壳包默认 blocked，不自动脱壳；root/越狱、装证书、frida/objection 注入、SSL pinning bypass、
重打包全部是审批门（tool_strategy.json approval_gated_phases.device_instrumentation）。
Burp MCP 只读本机 history 的协议与 XCX 相同；包内字符串、密钥候选、静态 sink 只是 signal/candidate。
```

## 附录 D：`docs/CONTEXT_LOADING_MAP.yaml` app 段草案（B7 并入；schema 对齐现有 fh/wz/xcx 与 phases 段）

> CLM 只登记 skill/契约/引擎模块/锁定测试来源；engagement 工作区文件（phase_status.app.json、app.json、
> materials.csv 等）不在 CLM 登记，由 SKILL 会话纪律与 loader 的 symbol 机制处理。

```yaml
workflows:
  app:
    - path: .agents/skills/app/SKILL.md
      purpose: APP 流程主规则
      required: true
    - path: .agents/skills/app/references/workflow.md
      purpose: 阶段定义与游标
      required: true
    - path: .agents/skills/app/references/test-matrix.md
      purpose: 测试矩阵（MASTG 锚点，见施工方案附录 G）
      required: true

phases:
  app_package_analysis:
    - path: .agents/skills/app/references/package-analysis.md
      purpose: "APK/IPA 解包分支与加固识别规则（含加固特征表）；壳包默认 blocked，不自动脱壳"
      required: true
  app_hardening:
    - path: contracts/app_storage_package_schema.json
      purpose: 包完整性/加固/热更新信任契约分支（hardening 七分支）
      required: false
  app_auth:
    - path: contracts/app_auth_schema.json
      purpose: APP 认证态契约（三 phase/分支/产物路径/形状/红线）
      required: false
    - path: src/authorized_assessment/app/platform_login_exchange.py
      purpose: "App 平台登录交换复核域（OAuth/一键登录/设备绑定）；必需性: false"
      required: false
    - path: src/authorized_assessment/app/session_token_lifecycle.py
      purpose: 会话 token 生命周期复核域（复用共享引擎模式）
      required: false
    - path: src/authorized_assessment/app/signature_replay_review.py
      purpose: 签名重放离线复核域（不自动重放任何请求）
      required: false
    - path: tests/test_app_contract_sync.py
      purpose: app 契约↔引擎↔种子三处同源锁定测试
      required: false
  app_storage_package:
    - path: contracts/app_storage_package_schema.json
      purpose: 本地数据/密码学/加固契约
      required: false
    - path: src/authorized_assessment/app/local_data_exposure.py
      purpose: 本地数据暴露复核域（android/ios 平台列）
      required: false
    - path: src/authorized_assessment/app/crypto_secret_review.py
      purpose: 密码学与密钥处理复核域（secret_candidate 红线）
      required: false
  app_reconciliation:
    - path: contracts/app_reconciliation_schema.json
      purpose: 静态/动态端点对账契约（五分支/十值端点状态）
      required: false
    - path: src/authorized_assessment/app/static_dynamic_reconciliation.py
      purpose: 离线对账复核域（不发新请求）
      required: false
  app_webview_ipc:
    - path: contracts/app_webview_schema.json
      purpose: WebView/Bridge/Deep Link 契约（三 CSV）
      required: false
    - path: contracts/app_ipc_schema.json
      purpose: exported 组件/URL Scheme/Universal Link 契约（两 CSV）
      required: false
    - path: src/authorized_assessment/app/webview_bridge_review.py
      purpose: webview 三清单复核域
      required: false
    - path: src/authorized_assessment/app/ipc_component_review.py
      purpose: IPC 组件清单复核域
      required: false
  app_cloud:
    - path: contracts/app_cloud_schema.json
      purpose: 云函数/对象存储/第三方 SDK 边界契约
      required: false
    - path: src/authorized_assessment/app/cloud_function_review.py
      purpose: 云函数复核域（最小读验证）
      required: false
    - path: src/authorized_assessment/app/cloud_storage_review.py
      purpose: 对象存储 ACL 复核域
      required: false
    - path: src/authorized_assessment/app/third_party_boundary_review.py
      purpose: 第三方 SDK/平台边界复核域
      required: false
```

## 附录 E：`CONSTRUCTION_STATUS.md` 工单行（W15 已随 B0 落地并入台账，2026-09-07；W16-W20 待开工时逐行更新）

```markdown
| W15 | APP 流 B0 工具白名单 | 已落地 | tools/managed/app/* + tool_registry(+2 active) + gov_exercise_config.tools + tool_strategy app 条目 | jadx 1.5.6/apktool 3.0.3 实测+sha256 核对；frida 系登记 unavailable |
| W16 | APP 流 B1 Skill 骨架 | 待开工 | .agents/skills/app/SKILL.md + 6 references + 双镜像（底稿 docs/APP_SKILL_DRAFT.md；提示词附录 I-B1/J-B1） | check_skill_drift=0；33 阶段+MASTG 锚点 |
| W17 | APP 流 B2 init+routing | 待开工 | init_app_engagement.py + phase_status_routing.py + 3 测试 | pytest test_app_* 全绿；三流隔离 |
| W18 | APP 流 B3 audit | 待开工 | audit_app_engagement.py + 测试 | fail-closed 负例全绿 |
| W19 | APP 流 B4-B6 契约+引擎 | 待开工 | contracts/app_*.json + src/authorized_assessment/app/* + 同步测试 | validate_run_contracts=0 |
| W20 | APP 流 B7-B8 配方/导航/验收 | 待开工 | 配方APP + 配方P/C + copy_prompt + 导航文档 | 全量 pytest/verify_offline 绿 + 样本 APK 演练 |
```

| W21 | APP 流 B9 Graph/编排接入 | 待开工 | contracts/app_graph_schema.json + orchestration/app_graph.py + graph 测试三件 | graph 测试全绿+全量回归 |

> B9=W21 正式批次；W16-W21 全部通过验收即 APP 流程建设闭环（验收记录：docs/APP_CONSTRUCTION_ACCEPTANCE.md；施工/验收提示词：附录 I/J）。

## 附录 F：Android 加固壳特征识别表（package_inventory / package_unpack_decompile 用）

识别方式：解包后遍历 `lib/<abi>/`（armeabi-v7a、arm64-v8a 等）与 assets，按**文件名前缀**匹配（带版本号的如 `libshella-2.10.3.1.so` 必须用 contains/前缀，不能全名等值）。命中只记 `signal`（加固厂商候选），新版壳可能改名或 VMP 化导致 so 特征失效，需以 DEX 结构特征复核；任何脱壳动作见 §6.2 审批门。

| 厂商 | 特征文件（lib/ 与 assets） |
|---|---|
| 360 加固 | `libjiagu.so` / `libjiagu_art.so` / `libjiagu_x86.so` / `libjiagu_64.so` |
| 梆梆加固 | `libDexHelper.so` / `libDexHelper-x86.so` / `libsecexe.so` / `libsecmain.so`；assets 可见 `secData0.jar`、`mock.dex` |
| 爱加密 | `libexecmain.so` / `libexec.so` / `ijiami.dat` / `ijiami.ajm` |
| 腾讯乐固 | `libshella-*.so`（前缀）/ `libtup.so` / `liblegudb.so` / `libtosprotection.so` / `libmix.so` / `mix.dex` |
| 娜迦加固 | `libchaosvmp.so` / `libddog.so` / `libfdog.so`；企业版 `libedog.so` |
| 百度加固 | `libbaiduprotect.so` |
| 网秦 | `libnqshield.so` |
| 启明星辰 | `libvenustech.so` |

来源：看雪论坛《Android 加固厂商特征》帖（bbs.kanxue.com/thread-223248）、CSDN「Android加固特征」（blog.csdn.net/u010671061/article/details/132634085）、掘金同文（juejin.cn/post/7273685263842820152）、安全客《App加固的种类甄别与侦查》（anquanke.com/post/id/272843）、AndroidSecNotes 常见加固厂商脱壳方法（github.com/JnuSimba/AndroidSecNotes）。iOS：Mach-O `LC_ENCRYPTION_INFO` cryptid=1 即 FairPlay 加密 → 该材料记 `blocked(ios_fairplay_encrypted)`；Windows 侧可用 python-lief 读 cryptid，或直接采用操作者提供的已解密 ipa。

## 附录 G：APP 阶段 ↔ MASTG 测试映射（test-matrix.md 的权威锚点，2026-09 取自 mas.owasp.org/MASTG/tests/）

| APP 阶段 | MASVS 域 | 代表 MASTG 测试（Android / iOS） |
|---|---|---|
| local_data_exposure | STORAGE | MASTG-TEST-0001 本地存储敏感数据、MASTG-TEST-0200 外部存储写入 / MASTG-TEST-0052 本地数据存储、MASTG-TEST-0058 备份敏感数据 |
| crypto_and_secret_handling | CRYPTO | MASTG-TEST-0013 对称加密、MASTG-TEST-0208 密钥长度不足 / MASTG-TEST-0061 算法配置、MASTG-TEST-0063 随机数 |
| platform_login_exchange / session_token_lifecycle / signature_replay | AUTH | MASTG-TEST-0017 Confirm Credentials、MASTG-TEST-0018 生物识别 / MASTG-TEST-0064 生物识别 |
| backend_web_api_testing + dynamic_mapping（传输观察） | NETWORK | MASTG-TEST-0019 网络数据加密、MASTG-TEST-0242 NSC 缺少证书绑定 / MASTG-TEST-0065 网络加密、MASTG-TEST-0068 自定义证书与 pinning |
| ipc_component_boundary / webview_bridge_links | PLATFORM | MASTG-TEST-0028 Deep Links、MASTG-TEST-0031 WebView JS 执行 / MASTG-TEST-0075 自定义 URL Scheme、MASTG-TEST-0076 iOS WebViews |
| static_analysis / source_reconstruction | CODE | MASTG-TEST-0025 注入缺陷、MASTG-TEST-0042 三方库弱点 / MASTG-TEST-0079 对象持久化、MASTG-TEST-0086 内存破坏 |
| package_integrity_hardening_review | RESILIENCE | MASTG-TEST-0045 root 检测、MASTG-TEST-0051 混淆 / MASTG-TEST-0088 越狱检测、MASTG-TEST-0093 混淆 |
| third_party_sdk_platform_boundary | PRIVACY | MASTG-TEST-0206 流量中未声明 PII、MASTG-TEST-0254 危险权限 / MASTG-TEST-0281 未声明跟踪域名 |

> 施工 B1 写 `references/test-matrix.md` 时按本表把每个阶段锚定到具体 MASTG-TEST 页（路径形态 `<platform>/MASVS-<域>/MASTG-TEST-XXXX/`），测试 ID 以当日目录为准再核对一次。

## 附录 H：审批门工具 registry `unavailable` 登记草案（操作者放置并 rebuild 后才可 active）

版本为 2026-09-07 GitHub Releases 最新值查询；`path` 为约定落位（`tools/managed/app/…`），放置前 status 保持 `unavailable`，不得被 tool_strategy 精确引用（校验器强制）。

| tool_id | 版本 | 计划落位 | runtime | dependencies | known_limitations 要点 |
|---|---|---|---|---|---|
| frida | 17.17.0 | tools/managed/app/frida/ | native | 指定测试设备 frida-server（版本须与宿主一致）、USB/ADB | 注入=审批门；hook 脚本仅用于观察与最小证明；输出不得含凭证值 |
| objection | 1.12.5 | tools/managed/app/objection/ | python | frida、root/越狱设备 | pinning bypass/反调试 patch=审批门；bypass 是测试技术不是漏洞结论 |
| Mobile-Security-Framework-MobSF | v4.5.2 | tools/managed/app/mobsf/ | python | 独立 python 环境/Docker；动态分析需模拟器 | 静态扫描结果全为候选；动态分析容器联网行为须按本流程限速与授权约束另行审批 |
| FRIDA-DEXDump | v2.0.1 | tools/managed/app/frida-dexdump/ | python | frida + 已 root 指定测试设备 | 仅服务 app_hardened_unpack 审批门；壳识别仍是 signal；产物按操作者材料登记 provenance |
| BlackDex | v3.2 | tools/managed/app/blackdex/ | android-app | 指定测试设备安装 | 同上；设备安装/运行属 device_instrumentation 审批门 |

登记流程按 `tools/README_tool_registry.md`：人工补齐 8 字段 → `rebuild_tool_inventory.py --check` → 需要 AI 选用时重跑 `gen_agent_manifest.py`。

---

## 附录 I：B1–B9 施工提示词（每批一个新会话，整段粘贴）

使用规则：① 严格按 B1→B9 顺序，上一批未验收通过不得开工；② 每个提示词自包含，新会话直接粘贴；③ 施工会话完成后，另开独立会话粘贴附录 J 对应验收提示词；④ 全部提示词共享同一纪律：零网络（本地文件与本地测试除外）、stream 固定为 `app`、不回滚/覆盖工作树中用户既有改动、审批门语义不得放松。

### I-B1 施工提示词（W16 · Skill 骨架）

```text
你是 APP 流程施工会话，只执行批次 B1（Skill 骨架，工单 W16），完成即停，不得越界到后续批次。
项目根目录：D:\PythonSource\PythonProjects\PythonProject4（下文相对路径均以此为基准）。

【开工必读，按序】
1. AGENTS.md、ROE.md、docs/RULE_PRECEDENCE.md（安全边界/凭证纪律/规则优先级）。
2. docs/APP_WORKFLOW_CONSTRUCTION_PLAN.md：§3（命名与三流隔离，stream 固定为 app）、§4（33 阶段表）、§5.1（本批文件清单）、附录 F（加固特征表）、附录 G（MASTG 锚点）。
3. docs/APP_SKILL_DRAFT.md：SKILL.md 全文底稿与"差异清单"。
4. docs/APP_CONSTRUCTION_ACCEPTANCE.md（如存在）：确认无未闭环的打回项；B0 已记 W15，无需处理。

【本批只做以下文件，不越界】
新建（canonical，位于 .agents/skills/app/）：
1. SKILL.md——以底稿第一节落盘：frontmatter name: app；顶部硬约束 0-9 与 AI 结论模板/四问否决/成立最小链条与 .agents/skills/xcx/SKILL.md 逐字一致；差异仅限底稿"差异清单"所列（游标文件、dynamic_setup/app_hardened_unpack 审批门、设备纪律等）。
2. references/workflow.md——把方案 §4 的 33 个阶段逐段展开（每阶段：目的/输入/步骤/分支/工件路径/红线/MASTG 锚点），章节结构对齐 .agents/skills/xcx/references/workflow.md 的 7 节。
3. references/test-matrix.md——克隆 .agents/skills/xcx/references/test-matrix.md 结构，扩为 MASVS 八域 × Android/iOS 矩阵，新增 ipc_component_boundary 与 package_integrity_hardening_review 两节，按附录 G 标注 MASTG-TEST ID。
4. references/data-to-test-playbook.md——克隆 wz/xcx 同名文件的选型规则，改写为 manifest 字段/恢复源码/流量/设备观察 → 具体测试（payload 按参数类型/角色/状态选择，配对正负控，canary 纪律）。
5. references/package-analysis.md——包分支手册：apktool/jadx 标准命令（方案 §7.1 实测参数 + 子进程超时/输出上限/失败写 decoding-ledger）、split/xapk/apks 处理、附录 F 加固特征表全文、iOS FairPlay cryptid 检查、解包失败→blocked 记录格式、壳包不自动脱壳红线。
6. references/artifact-contract.md——克隆 .agents/skills/xcx/references/artifact-contract.md，报告 DOCX 固定结构与生成器禁写清单原样保留，小程序措辞换成 App（client/backend/platform/third-party 分节）。
7. references/evidence-reporting.md——克隆 xcx 同名文件改写；保留 ROE 3–5 条最小证明例外引用与脱敏/cleanup 要求。
镜像：以上 7 件原样复制到 .claude/skills/app/ 与 .opencode/skills/app/（三处逐字节一致）。

【明确不做】不创建 scripts/（B2/B3）；不改 contracts/、tool_strategy.json、gov_exercise_config.json（B4）；不写 src/（B5/B6）；不改 prompts/ 与导航文档（B7）；不回滚或覆盖工作树中任何用户既有改动。

【硬约束】本批零网络（读项目文件与跑本地校验脚本除外）；命名纪律：流程名小写 app、游标 phase_status.app.json、stream 值 app，禁止出现 app_mobile 等旧名。

【自验命令（全部通过才算完成）】
python scripts/check_skill_drift.py   # 退出码 0
python scripts/check_doc_drift.py     # 退出码 0
grep -n "name: app" .agents/skills/app/SKILL.md
grep -n "phase_status.app.json" .agents/skills/app/SKILL.md
grep -n "MASTG-TEST-0001" .agents/skills/app/references/test-matrix.md
grep -n "libjiagu" .agents/skills/app/references/package-analysis.md
grep -n "apktool_3.0.3" .agents/skills/app/references/package-analysis.md

【收尾动作】
1. CONSTRUCTION_STATUS.md：W16 行状态改"已落地(待验收)"，备注追加产物清单与自验结果。
2. 向操作者报告：改动文件清单、自验输出摘要、建议提交信息（提交由操作者执行）。
3. 提醒：下一步用附录 J-B1 验收提示词开独立验收会话。
```

### I-B2 施工提示词（W17 · init + 三流路由）

```text
你是 APP 流程施工会话，只执行批次 B2（init + 路由，工单 W17），完成即停。
前置确认：docs/APP_CONSTRUCTION_ACCEPTANCE.md 中 B1 验收为"通过"，否则停止并报告。
项目根目录：D:\PythonSource\PythonProjects\PythonProject4。

【开工必读】AGENTS.md、ROE.md、docs/RULE_PRECEDENCE.md；方案 §3（三流隔离）、§5.8（workspace 布局）、§7.2（init 规格）、§7.4（路由规格，含已验证的四用例行为）、附录 B（33 阶段种子骨架，stream=app）；参照实现 .agents/skills/xcx/scripts/init_miniapp_engagement.py 与 .agents/skills/xcx/scripts/phase_status_routing.py。

【本批只做以下文件】
1. 新建 .agents/skills/app/scripts/phase_status_routing.py——按 §7.4：APP_PHASE_STATUS_FILENAME="phase_status.app.json"、APP_STREAM="app"、resolve_phase_status(root, for_write) fail-closed（缺 app 游标时报 APP_PHASE_STATUS_MISSING，绝不回落 wz/xcx 游标）、route_metadata()；不保留 xcx 的 legacy 单流回退。
2. 新建 .agents/skills/app/scripts/init_app_engagement.py——按 §7.2：CLI（<input> + --output + --platform auto|android|ios|dual|other + --name/--package/--operator/--version + --authorization-ref/--window/--rules/--rate + --scope-root + --resume + --allow-parallel）；classify_input 识别 8 类输入并对包文件算 sha256；零网络断言 network_accessed_by_initializer: false；按 §5.8 建全部骨架（write_*_if_missing 幂等、resume 补种）；phase_status.app.json 种子＝附录 B 骨架（33 phase + 12 组 substatuses，authorization=complete，identity/platform_identification 按输入字段自动 complete）；--resume 校验输入 hash 一致。
3. 新建 tests/test_app_phase_status_routing.py——锁定 §7.4 四用例（fail-closed/只提议 app 游标/解析自身 stream/stream 缺省 app）。
4. 新建 tests/test_app_init_engagement.py——骨架齐全、零网络断言、resume hash 不匹配报错、33 phase 种子与 substatuses 与附录 B 一致。
5. 新建 tests/test_app_triple_stream_isolation.py——共址工作区三流互不读写对方游标。
6. 镜像：两个脚本同步复制到 .claude/skills/app/scripts/ 与 .opencode/skills/app/scripts/。

【明确不做】不写 audit（B3）；不改 contracts（B4）；不写 src/（B5/B6）。

【硬约束】零网络；init 不发任何请求、不读 runs/、不读 auth_sessions.local.json；不动用户既有改动。

【自验命令】
.venv/Scripts/python.exe -m pytest tests/test_app_phase_status_routing.py tests/test_app_init_engagement.py tests/test_app_triple_stream_isolation.py -q
.venv/Scripts/python.exe .agents/skills/app/scripts/init_app_engagement.py com.example.smoke --output "$TEMP/app_ws_smoke" --platform android --name Smoke --operator Test
# 核对输出 workspace/phase_status_file=phase_status.app.json/stream=app，并按 §5.8 抽查骨架文件存在；结束后删除临时目录
python scripts/check_skill_drift.py

【收尾动作】CONSTRUCTION_STATUS.md：W17 行改"已落地(待验收)"＋产物清单；报告改动与建议提交信息；提醒用附录 J-B2 验收。
```

### I-B3 施工提示词（W18 · audit 审计器）

```text
你是 APP 流程施工会话，只执行批次 B3（audit，工单 W18），完成即停。
前置确认：B2 验收"通过"。
项目根目录：D:\PythonSource\PythonProjects\PythonProject4。

【开工必读】AGENTS.md、ROE.md、docs/RULE_PRECEDENCE.md；方案 §7.3（audit 规格）、§4（状态枚举与分支红线）；参照实现 .agents/skills/xcx/scripts/audit_miniapp_engagement.py（检查族命名与语义保持同构）。

【本批只做以下文件】
1. 新建 .agents/skills/app/scripts/audit_app_engagement.py——游标经 phase_status_routing 解析（fail-closed）；实现检查族：12-key review JSON 完整性（与 xcx _review_phase_issues 同构）、coverage_substatus 六值枚举（tested/not_applicable/blocked/approval_required/needs_manual_validation/inconclusive）、CSV 工件行契约（tested 需≥1 行、not_applicable 需 phase reason）、对账十态行级校验（judgment 行必须有 reason）、webview/ipc 清单行校验、reportable_review_items（active 候选必须有 disposition）、证据引用存在性、cleanup/report 闭合；--json 与文本输出；退出码非 0＝不可闭合。
2. 新建 tests/test_app_audit_engagement.py——正例（最小可闭合工作区）+ 至少 3 个负例（分支未记录/缺 artifact/confirmed 缺证据/候选无 disposition）。
3. 镜像同步 audit 脚本到 .claude/ 与 .opencode/。

【明确不做】不改 init/routing（除非测试暴露 B2 缺陷，需在报告中单列）；不改契约（B4）。

【硬约束】audit 只读：不改任何工作区文件；零网络。

【自验命令】
.venv/Scripts/python.exe -m pytest tests/test_app_audit_engagement.py -q
.venv/Scripts/python.exe .agents/skills/app/scripts/audit_app_engagement.py <临时工作区> --json
# 期望：结构化输出全部未闭合问题、无 traceback（退出码可为 1）；结束后删临时目录
python scripts/check_skill_drift.py

【收尾动作】W18 行改"已落地(待验收)"；报告＋建议提交信息；提醒附录 J-B3 验收。
```

### I-B4 施工提示词（W19 上 · 六个 app 契约）

```text
你是 APP 流程施工会话，只执行批次 B4（契约，工单 W19 上半），完成即停。
前置确认：B3 验收"通过"。
项目根目录：D:\PythonSource\PythonProjects\PythonProject4。

【开工必读】AGENTS.md、ROE.md、docs/RULE_PRECEDENCE.md；方案 §5.2（契约清单与克隆源）、附录 B（分支与产物路径的唯一事实源）；参照 contracts/miniapp_auth_schema.json、miniapp_storage_package_schema.json、miniapp_reconciliation_schema.json、miniapp_webview_schema.json、miniapp_cloud_schema.json 的 12-key 形状。

【本批只做以下文件】
1. 新建 contracts/app_auth_schema.json——三 phase：platform_login_exchange 五分支（oauth_code_one_time/oauth_code_expiry/one_click_login_device_binding/access_token_custody/uid_authorization_basis）；session_token_lifecycle 五分支与 xcx 同名；signature_replay 四分支与 xcx 同名。含 coverage_substatus 六值、artifact_fields、authorization_basis_values、red_lines（永不自动重放/凭证纪律）、invariants；分支与产物路径必须与附录 B 种子逐一一致。
2. 新建 contracts/app_storage_package_schema.json——package_integrity_hardening_review 七分支（package_version_inventory/signing_integrity/hardening_obfuscation_markers/debug_switches/debug_info_exposure/update_endpoint_environment/trusted_update_config）＋local_data_exposure 五分支＋crypto_and_secret_handling 四分支；secret_candidate 红线与 APP_NO_REPACKING_RULE。
3. 新建 contracts/app_reconciliation_schema.json——五分支＋十个行级 endpoint 状态枚举（与 xcx 同名）。
4. 新建 contracts/app_webview_schema.json——三 CSV 字段（路径改 artifacts/app/webview/）。
5. 新建 contracts/app_ipc_schema.json——七分支（exported_activity/exported_service/exported_receiver/exported_provider/custom_scheme_deeplink/universal_link/ios_extension_boundary）＋component-inventory.csv/deeplink-review-queue.csv 字段。
6. 新建 contracts/app_cloud_schema.json——cloud 三 phase 分支与产物。
7. 修改 scripts/maintenance/validate_run_contracts.py——REQUIRED 契约清单追加全部 app_*.json；新增"契约分支/产物路径 ↔ .agents/skills/app/scripts/init_app_engagement.py 种子常量"一致性校验（引擎侧同步项留待 B5/B6 补）。

【明确不做】不写 src/authorized_assessment/app/（B5/B6）；不动 tool_strategy（B0 已完成）。

【硬约束】零网络；契约是分支唯一事实源，与附录 B 冲突时以附录 B 为准并先修契约。

【自验命令】
python scripts/maintenance/validate_run_contracts.py            # 退出码 0
# 负例：用 --root 指向临时副本目录，把任一 app 契约的一个分支名改坏，validator 必须退出 1
.venv/Scripts/python.exe -m pytest tests/test_app_init_engagement.py -q   # 种子不受影响

【收尾动作】W19 行备注追加"B4 契约完成（引擎同步待 B5/B6）"；报告＋建议提交信息；提醒附录 J-B4 验收。
```

### I-B5 施工提示词（W19 中 · 静态引擎）

```text
你是 APP 流程施工会话，只执行批次 B5（静态引擎，工单 W19 中段），完成即停。
前置确认：B4 验收"通过"。
项目根目录：D:\PythonSource\PythonProjects\PythonProject4。

【开工必读】AGENTS.md、ROE.md、docs/RULE_PRECEDENCE.md；方案 §5.3（引擎清单与复用边界）、§7.1（标准命令与子进程纪律）、附录 F；参照 src/authorized_assessment/miniapp/package_integrity_update.py 的共享引擎模式与 .agents/skills/app/references/package-analysis.md。

【本批只做以下文件】
1. 新建 src/authorized_assessment/app/__init__.py 与 README.md（模块地图＋复用边界说明）。
2. 新建 src/authorized_assessment/app/app_review_common.py——共享引擎（12-key review JSON 骨架、coverage_substatus 六值、observation→evidence kind 判定、confirm 升级门、duplicate_execution=false 常量）。
3. 新建 src/authorized_assessment/app/hardening_integrity_review.py——hardening 七分支，分支常量取自 contracts/app_storage_package_schema.json；只观察不绕过红线写入 docstring 与 invariants。
4. 新建 src/authorized_assessment/app/static_extraction.py——apktool/jadx 子进程封装（仅允许 registry active 路径 tools/managed/app/...，超时 600s/包、输出上限、stderr 落 logs/、失败写 decoding-ledger）、AndroidManifest 深解析（权限/exported/intent-filter/allowBackup/debuggable/networkSecurityConfig/cleartext）、secrets/SDK/API 路径模式提取、whitebox_triage.py --scan 薄包装。
5. 新建 src/authorized_assessment/app/webview_bridge_review.py 与 ipc_component_review.py——三 CSV/两 CSV 清单引擎（克隆 xcx webview 模式，契约 app_webview_schema/app_ipc_schema）。
6. 新建 tests/test_app_contract_sync.py（契约↔引擎↔种子三处同源）与 tests/test_app_static_engine.py（临时目录假 dex/资源文件、子进程 mock、失败→ledger）。
7. 修改 scripts/maintenance/validate_run_contracts.py——补 B5 覆盖模块的契约↔引擎同步校验。

【明确不做】auth/reconciliation/local/crypto/cloud 模块（B6）；任何真实 APK 下载或联网获取样本。

【硬约束】引擎全部离线；不硬编码工具绝对路径（从 registry/config 解析）；敏感值不进日志。

【自验命令】
.venv/Scripts/python.exe -m pytest tests/test_app_contract_sync.py tests/test_app_static_engine.py -q
python scripts/maintenance/validate_run_contracts.py
.venv/Scripts/python.exe -m pytest -q 2>&1 | tail -1   # 全量不回归

【收尾动作】W19 行备注追加"B5 静态引擎完成"；报告＋建议提交信息；提醒附录 J-B5 验收。
```

### I-B6 施工提示词（W19 下 · 认证/对账/云引擎）

```text
你是 APP 流程施工会话，只执行批次 B6（评审引擎下半，工单 W19 收尾），完成即停。
前置确认：B5 验收"通过"。
项目根目录：D:\PythonSource\PythonProjects\PythonProject4。

【开工必读】AGENTS.md、ROE.md、docs/RULE_PRECEDENCE.md；方案 §5.3 其余行、§4 阶段 16-19/24-30 的分支红线；参照 src/authorized_assessment/miniapp/ 下同名评审模块的引擎模式。

【本批只做以下文件】
1. 新建 src/authorized_assessment/app/platform_login_exchange.py（五分支 app 语境）、session_token_lifecycle.py（五分支）、signature_replay_review.py（四分支；invariants 写明永不自动重放任何请求）。
2. 新建 src/authorized_assessment/app/local_data_exposure.py 与 crypto_secret_review.py（分支与 xcx 同名，行内 platform 列 android/ios；secret_candidate 红线）。
3. 新建 src/authorized_assessment/app/static_dynamic_reconciliation.py（五分支十态确定性分类，永不发新请求）。
4. 新建 src/authorized_assessment/app/cloud_function_review.py、cloud_storage_review.py、third_party_boundary_review.py（薄封装共享引擎）。
5. 新建 tests/test_app_review_engines.py——各引擎分支常量↔契约、confirm 升级门、红线 invariants 行为锁定。
6. 修改 scripts/maintenance/validate_run_contracts.py——补齐剩余模块同步校验；至此全部 app_* 契约↔引擎↔种子三处同源。

【明确不做】不动配方与导航文档（B7）；不做 graph（B9）。

【硬约束】零网络；签名重放引擎不得包含任何发请求代码路径；敏感值不进日志。

【自验命令】
.venv/Scripts/python.exe -m pytest tests/test_app_review_engines.py -q
python scripts/maintenance/validate_run_contracts.py
.venv/Scripts/python.exe -m pytest -q 2>&1 | tail -1   # 全量不回归

【收尾动作】W19 行状态改"已落地(待验收)"（B4-B6 三段齐）；报告＋建议提交信息；提醒附录 J-B6 验收。
```

### I-B7 施工提示词（W20 上 · 配方与导航）

```text
你是 APP 流程施工会话，只执行批次 B7（配方与导航，工单 W20 上半），完成即停。
前置确认：B6 验收"通过"。
项目根目录：D:\PythonSource\PythonProjects\PythonProject4。

【开工必读】AGENTS.md、ROE.md、docs/RULE_PRECEDENCE.md；方案 §5.4、§5.6、附录 C（配方P 修改文本）、附录 D（CONTEXT_LOADING_MAP 草案）；底稿 docs/APP_SKILL_DRAFT.md 第二节（配方APP 全文）。

【本批只做以下文件】
1. 新建 prompts/配方APP_App流程.md——以底稿第二节落盘。
2. 修改 prompts/配方P_提示词分发员.md——按附录 C 三处（输入识别行/配方来源/APP 路由规则节）。
3. 修改 prompts/配方C_单目标深挖.md——规则 1 与规则 6 游标清单增补"APP 使用 phase_status.app.json（stream=app）"。
4. 修改 tools/copy_prompt.py——RECIPES 加 "APP": "配方APP_App流程.md"，ALIASES 加 "12": "APP"。
5. 修改 D:\Desktop\AI配方_一键复制.bat（操作者桌面文件，仓库外）——echo 菜单文案 1-10 → 1-12，加 "12 = APP流程"；只追加不动其他行，修改前先读原文并在报告中给前后差异。
6. 修改 docs/CONTEXT_LOADING_MAP.yaml——按附录 D 并入 workflows.app 段与 phases.app_* 域。
7. 修改 AGENTS.md——入口表加配方APP 行；"深入阅读" skills 列表 {wz,xcx,fh} → {wz,xcx,app,fh}；"施工中"段指向 CONSTRUCTION_STATUS W16-W21。
8. 修改 README.md 与 docs/PROJECT_STRUCTURE.md——流程描述加 APP（三镜像规则文字不变）。
9. 修改 D:\Desktop\PROJECT_OVERVIEW_FOR_NEW_SESSIONS.md（仓库外）——路由表加 APP 行、权威文件表加配方APP。
10. 修改 CONSTRUCTION_STATUS.md——W20 行备注追加"B7 配方/导航完成"。

【明确不做】不做端到端演练（B8）；不做 graph（B9）；两个桌面文件只做最小追加修改。

【硬约束】零网络；不把任何真实目标信息写进配方。

【自验命令】
python tools/copy_prompt.py --list | grep APP
python scripts/check_doc_drift.py
python scripts/check_skill_drift.py
.venv/Scripts/python.exe -c "import yaml;d=yaml.safe_load(open('docs/CONTEXT_LOADING_MAP.yaml',encoding='utf-8'));print('app' in d.get('workflows',{}))"
grep -n "路由到 APP" prompts/配方P_提示词分发员.md
grep -n "phase_status.app.json" prompts/配方C_单目标深挖.md

【收尾动作】报告全部前后差异（尤其两个桌面文件）＋建议提交信息；提醒附录 J-B7 验收。
```

### I-B8 施工提示词（W20 下 · 端到端离线验收执行）

```text
你是 APP 流程施工会话，执行批次 B8（端到端离线验收，工单 W20 收尾）。本批不写生产代码，产出是验收执行记录。
前置确认：B7 验收"通过"。
项目根目录：D:\PythonSource\PythonProjects\PythonProject4。

【开工必读】AGENTS.md、ROE.md；方案 §8 B8 行、§11（验收基线）。

【本批只做】
1. 全量回归：.venv/Scripts/python.exe -m pytest -q（记录用例数与结果）。
2. 离线验收四件套并记录退出码：.venv/Scripts/python.exe scripts/verify_offline.py --json；python scripts/maintenance/rebuild_tool_inventory.py --check；python scripts/maintenance/validate_run_contracts.py；python scripts/check_skill_drift.py；python scripts/check_doc_drift.py。
3. 端到端演练（关键路径）：临时目录 init_app_engagement.py 建工作区 → 依次推进 preflight → package_inventory → package_unpack_decompile → source_reconstruction → static_analysis → host_classification。样本材料二选一：a. 操作者当场提供无害样本 APK/IPA（只做静态解包与提取，不发任何请求，哈希登记进 materials.csv）；b. 无样本时构造最小伪 APK 目录走 classify_input/骨架/ledger 路径，并把"真实样本演练"记为待操作者提供。每阶段写 phase note + 更新 phase_status.app.json + notes/target-model.md。
4. 演练后跑 .agents/skills/app/scripts/audit_app_engagement.py <工作区> --json，确认审计发现与推进状态一致；随后删除临时工作区。
5. 把全部结果写入 docs/APP_CONSTRUCTION_ACCEPTANCE.md 新小节 "B8 端到端验收执行记录"（命令、退出码、用例数、演练路径、发现的问题）；CONSTRUCTION_STATUS.md W20 行备注追加"B8 执行记录完成"。

【明确不做】不修复发现的缺陷（记录后交回对应批次返工）；不对任何真实目标发包；不下载样本。

【硬约束】全程零外部网络。

【收尾动作】向操作者报告闭环状态与遗留项；提醒附录 J-B8 验收。
```

### I-B9 施工提示词（W21 · Graph/编排接入）

```text
你是 APP 流程施工会话，只执行批次 B9（Graph/编排接入，工单 W21），完成即停。
前置确认：B8 验收"通过"。
项目根目录：D:\PythonSource\PythonProjects\PythonProject4。

【开工必读】AGENTS.md、ROE.md、docs/RULE_PRECEDENCE.md；方案 §8 B9 行；参照 contracts/xcx_graph_schema.json、src/authorized_assessment/orchestration/xcx_graph.py、tests/test_xcx_graph*.py 的既有模式。

【本批只做以下文件】
1. 新建 contracts/app_graph_schema.json——克隆 xcx_graph_schema.json 适配：33 个 app 阶段节点/依赖、stream=app、审批门节点（device_instrumentation/app_hardened_unpack）不可自动推进。
2. 新建 src/authorized_assessment/orchestration/app_graph.py——克隆 xcx_graph.py 适配：只读写 phase_status.app.json；节点推进边界与审批门语义与 SKILL 一致。
3. 新建 tests/test_app_graph.py、tests/test_app_graph_integration.py、tests/test_app_graph_phase_status_isolation.py——克隆 xcx graph 测试模式；隔离测试必须证明 app graph 在共址工作区绝不读写 wz/xcx 游标。
4. 修改 scripts/maintenance/validate_run_contracts.py——REQUIRED 增加 app_graph_schema.json 并做结构校验。

【明确不做】不改 worker 合同之外的既有编排行为；不动 wz/xcx graph。

【硬约束】零网络；graph 只是编排声明，不含任何探测执行。

【自验命令】
.venv/Scripts/python.exe -m pytest tests/test_app_graph.py tests/test_app_graph_integration.py tests/test_app_graph_phase_status_isolation.py -q
python scripts/maintenance/validate_run_contracts.py
.venv/Scripts/python.exe -m pytest -q 2>&1 | tail -1

【收尾动作】CONSTRUCTION_STATUS.md W21 行改"已落地(待验收)"；报告＋建议提交信息；提醒附录 J-B9 验收。全部批次通过验收后，在 CONSTRUCTION_STATUS.md 标注"APP 流程建设闭环"。
```

---

## 附录 J：B1–B9 验收提示词（每批一个独立新会话，整段粘贴）

使用规则：① 验收会话必须独立于施工会话（不允许施工会话自己验收自己）；② 除 `docs/APP_CONSTRUCTION_ACCEPTANCE.md`（验收台账）与 `CONSTRUCTION_STATUS.md` 对应 W 行的状态/备注外，验收会话**只读**——不修复、不返工、不改任何交付文件；③ 结论只有两种：通过 / 打回；打回必须列出失败项与证据（path:line 或命令输出），由下一轮施工会话返工后重新走本验收提示词（台账同一批次追加"复验"记录）；④ 验收通用范围检查：`git status --porcelain` 中本批改动必须落在该批"允许路径集"内，越界即打回。

### J-B1 验收提示词（W16 · Skill 骨架）

```text
你是独立验收会话，只验收 APP 流程批次 B1（Skill 骨架，W16）是否完成；除验收台账与 W 行状态外只读。
项目根目录：D:\PythonSource\PythonProjects\PythonProject4。

【开工必读】docs/APP_WORKFLOW_CONSTRUCTION_PLAN.md §5.1、§8 B1 行、附录 F/G；docs/APP_SKILL_DRAFT.md 差异清单。

【逐项验收（每项给 PASS/FAIL + 证据）】
1. 文件存在：.agents/skills/app/SKILL.md 与 references/{workflow,test-matrix,data-to-test-playbook,package-analysis,artifact-contract,evidence-reporting}.md 共 7 件；.claude/skills/app/ 与 .opencode/skills/app/ 镜像齐全。
2. 内容锚点：SKILL.md 含 name: app、phase_status.app.json、device_instrumentation、app_hardened_unpack、user_supplied_initial_target、拒绝一次性执行条款；硬约束 0-9 与 AI 结论模板同 xcx（并排 diff 抽查两段）。
3. workflow.md：与附录 B 的 33 个 phase 名逐一对应（脚本比对，输出缺失清单）。
4. test-matrix.md：含 MASTG-TEST-0001 与 MASTG-TEST-0281；含 ipc_component_boundary 与 package_integrity_hardening_review 节。
5. package-analysis.md：含 libjiagu/libDexHelper/libexecmain/libshella 特征表、apktool_3.0.3 与 jadx.bat 实测命令、"壳包不自动脱壳"红线。
6. 镜像一致：python scripts/check_skill_drift.py 退出码 0。
7. 文档引用：python scripts/check_doc_drift.py 退出码 0。
8. 范围纪律：本批改动路径集 ⊆ {.agents/skills/app/**, .claude/skills/app/**, .opencode/skills/app/**}。
9. 台账：CONSTRUCTION_STATUS.md W16 行为"已落地(待验收)"。

【判定与记录】全部 PASS → docs/APP_CONSTRUCTION_ACCEPTANCE.md 追加 "B1 验收 · 通过（<日期>，逐项证据摘要）"，W16 备注追加 "已验收 <日期>"；任一 FAIL → 记 "B1 验收 · 打回（失败项+证据）"，W16 状态改回 "待返工"。最终输出逐项 PASS/FAIL 表。
```

### J-B2 验收提示词（W17 · init + 路由）

```text
你是独立验收会话，只验收批次 B2（init + 三流路由，W17）；除验收台账与 W 行状态外只读。
项目根目录：D:\PythonSource\PythonProjects\PythonProject4。

【逐项验收】
1. 文件存在：.agents/skills/app/scripts/{init_app_engagement.py, phase_status_routing.py}、tests/{test_app_phase_status_routing.py, test_app_init_engagement.py, test_app_triple_stream_isolation.py}、两处脚本镜像。
2. 行为重放（方案 §7.4 四用例）：缺 app 游标 → APP_PHASE_STATUS_MISSING 且不返回路径；for_write=True 只提议 phase_status.app.json；app 游标在场解析 stream=app；stream 缺省 app。可用测试或临时目录脚本重放。
3. 种子核对：临时目录跑 init 后，phase_status.app.json 的 phases 数=33、substatuses 组与附录 B 一致、stream=app、engagement.json 含 network_accessed_by_initializer: false；--resume 传入不同输入必须报错。结束后删除临时目录。
4. 测试：.venv/Scripts/python.exe -m pytest tests/test_app_phase_status_routing.py tests/test_app_init_engagement.py tests/test_app_triple_stream_isolation.py -q 全绿。
5. 镜像一致与范围纪律、W17 台账状态（同 J-B1 通用规则）。

【判定与记录】同附录 J 通用规则：通过/打回写入验收台账与 W17 行。
```

### J-B3 验收提示词（W18 · audit）

```text
你是独立验收会话，只验收批次 B3（audit，W18）；除验收台账与 W 行状态外只读。
项目根目录：D:\PythonSource\PythonProjects\PythonProject4。

【逐项验收】
1. 文件存在：.agents/skills/app/scripts/audit_app_engagement.py + 镜像、tests/test_app_audit_engagement.py。
2. 测试全绿：.venv/Scripts/python.exe -m pytest tests/test_app_audit_engagement.py -q；负例至少覆盖：分支未记录/缺 artifact/confirmed 缺证据/候选无 disposition。
3. 实测：临时目录 init 建新工作区 → 跑 audit --json：必须输出结构化未闭合清单、无 traceback（退出码可为 1）；结束后删临时目录。
4. 只读性核验：audit 运行前后工作区文件 hash 不变（抽 3 个文件比对）。
5. 镜像一致（check_skill_drift=0）、范围纪律、W18 台账状态。

【判定与记录】同通用规则。
```

### J-B4 验收提示词（W19 上 · 契约）

```text
你是独立验收会话，只验收批次 B4（六个 app 契约 + validator 接入，W19 上半）；除验收台账与 W 行状态外只读。
项目根目录：D:\PythonSource\PythonProjects\PythonProject4。

【逐项验收】
1. 文件存在：contracts/{app_auth_schema, app_storage_package_schema, app_reconciliation_schema, app_webview_schema, app_ipc_schema, app_cloud_schema}.json。
2. 与附录 B 一致：脚本比对每个契约的 phases/分支/产物路径 == 附录 B 种子（允许字段名大小写差异，分支名必须精确相等）。
3. validator：python scripts/maintenance/validate_run_contracts.py 退出码 0；负例：--root 指向改坏分支名的临时副本必须退出 1（验收会话自行构造临时副本，结束删除）。
4. 契约红线在场：app_auth 含"永不自动重放"，app_storage_package 含 secret_candidate 与 APP_NO_REPACKING_RULE。
5. 范围纪律（本批允许路径集：contracts/app_*.json + scripts/maintenance/validate_run_contracts.py）、W19 台账备注含"B4 契约完成"。

【判定与记录】同通用规则。
```

### J-B5 验收提示词（W19 中 · 静态引擎）

```text
你是独立验收会话，只验收批次 B5（静态引擎，W19 中段）；除验收台账与 W 行状态外只读。
项目根目录：D:\PythonSource\PythonProjects\PythonProject4。

【逐项验收】
1. 文件存在：src/authorized_assessment/app/{__init__.py, README.md, app_review_common.py, hardening_integrity_review.py, static_extraction.py, webview_bridge_review.py, ipc_component_review.py}、tests/{test_app_contract_sync.py, test_app_static_engine.py}。
2. 三处同源：脚本比对 hardening 七分支在 contracts/app_storage_package_schema.json ↔ hardening_integrity_review.py ↔ 附录 B 种子一致；webview 七分支、ipc 七分支同理。
3. 子进程纪律锚点：static_extraction.py 含超时（600s）、输出上限、失败写 decoding-ledger、工具路径从 registry/config 解析（grep 无硬编码绝对路径）；docstring/invariants 含"只观察不绕过"。
4. 测试全绿：pytest 两个新测试文件；validator=0；全量 pytest 无回归（记录用例数）。
5. 范围纪律、W19 备注含"B5 静态引擎完成"。

【判定与记录】同通用规则。
```

### J-B6 验收提示词（W19 下 · 认证/对账/云引擎）

```text
你是独立验收会话，只验收批次 B6（评审引擎下半，W19 收尾）；除验收台账与 W 行状态外只读。
项目根目录：D:\PythonSource\PythonProjects\PythonProject4。

【逐项验收】
1. 文件存在：src/authorized_assessment/app/{platform_login_exchange, session_token_lifecycle, signature_replay_review, local_data_exposure, crypto_secret_review, static_dynamic_reconciliation, cloud_function_review, cloud_storage_review, third_party_boundary_review}.py、tests/test_app_review_engines.py。
2. 分支同源：auth 三 phase（5/5/4 分支）、reconciliation 五分支、cloud 三 phase（3/3/2 分支）、local 五分支、crypto 四分支——脚本比对契约↔引擎↔附录 B。
3. 红线锚点：signature_replay_review.py 无任何网络/请求代码路径（grep requests/httpx/urllib/socket 应为空或仅注释）且含"永不自动重放"；local/crypto 含凭证纪律与 secret_candidate 红线；reconciliation 含"不发新请求"。
4. 测试全绿 + validator=0 + 全量 pytest 无回归。
5. 范围纪律、W19 行状态"已落地(待验收)"。

【判定与记录】同通用规则。
```

### J-B7 验收提示词（W20 上 · 配方与导航）

```text
你是独立验收会话，只验收批次 B7（配方与导航，W20 上半）；除验收台账与 W 行状态外只读。
项目根目录：D:\PythonSource\PythonProjects\PythonProject4。

【逐项验收】
1. 文件存在/修改：prompts/配方APP_App流程.md 新建；配方P 含"路由到 APP"与配方来源行与"APP 路由规则"节；配方C 规则 1/6 含 phase_status.app.json；tools/copy_prompt.py RECIPES/ALIASES 含 APP/12；docs/CONTEXT_LOADING_MAP.yaml 含 workflows.app 与 phases.app_*；AGENTS.md 入口表与 skills 列表含 app；README 与 PROJECT_STRUCTURE 描述更新。
2. 桌面文件（仓库外，追加式）：D:\Desktop\AI配方_一键复制.bat 菜单含 "12 = APP流程" 且其余行未变（对照施工会话报告的差异清单抽查）；D:\Desktop\PROJECT_OVERVIEW_FOR_NEW_SESSIONS.md 路由表含 APP 行。
3. 命令核验：python tools/copy_prompt.py --list 显示 APP；check_doc_drift=0；check_skill_drift=0；CLM yaml 解析成功且 workflows 含 app。
4. 内容红线：配方APP 与配方P 的 APP 节含审批门（设备/注入/脱壳）与"不自动脱壳"表述；无任何真实目标/凭证信息。
5. 范围纪律、W20 备注含"B7 配方/导航完成"。

【判定与记录】同通用规则。
```

### J-B8 验收提示词（W20 下 · 端到端验收记录）

```text
你是独立验收会话，只验收批次 B8（端到端离线验收执行，W20 收尾）；除验收台账与 W 行状态外只读——本批验收对象是"执行记录"而非代码。
项目根目录：D:\PythonSource\PythonProjects\PythonProject4。

【逐项验收】
1. 台账核对：docs/APP_CONSTRUCTION_ACCEPTANCE.md 存在 "B8 端到端验收执行记录" 小节，含：全量 pytest 用例数与结果；verify_offline/rebuild_tool_inventory/validate_run_contracts/check_skill_drift/check_doc_drift 五项退出码；演练路径与每阶段产物说明。
2. 抽查复跑（只读重放）：任选记录中三项命令重跑，结果与记录一致。
3. 演练闭环判定：真实样本演练已完成（证据：materials.csv 哈希/阶段产物路径在记录中）或明确标注"待操作者提供样本"且伪 APK 路径已覆盖 classify_input/骨架/ledger；audit --json 输出与推进状态一致的证据在场。
4. 无越界：B8 未修改生产代码（git diff 抽查）。
5. W20 备注含"B8 执行记录完成"。

【判定与记录】同通用规则；若"真实样本演练"为待提供且其余全过，结论记"通过（带待办：样本演练）"，待办进入 operator 跟踪。
```

### J-B9 验收提示词（W21 · Graph/编排接入）

```text
你是独立验收会话，只验收批次 B9（Graph/编排接入，W21）；除验收台账与 W 行状态外只读。
项目根目录：D:\PythonSource\PythonProjects\PythonProject4。

【逐项验收】
1. 文件存在：contracts/app_graph_schema.json、src/authorized_assessment/orchestration/app_graph.py、tests/{test_app_graph.py, test_app_graph_integration.py, test_app_graph_phase_status_isolation.py}。
2. 契约锚点：graph 节点覆盖 33 阶段、stream=app、审批门节点不可自动推进（schema/代码双重体现）。
3. 隔离证明：隔离测试通过，且测试内容确实验证了"共址工作区不读写 wz/xcx 游标"（读测试源码确认断言有效，非空测试）。
4. 测试全绿：三个 graph 测试文件 + validator=0 + 全量 pytest 无回归（记录用例数）。
5. 范围纪律：改动 ⊆ {contracts/app_graph_schema.json, src/authorized_assessment/orchestration/app_graph.py, tests/test_app_graph*.py, scripts/maintenance/validate_run_contracts.py}；W21 行状态"已落地(待验收)"。

【判定与记录】通过 → W21 备注"已验收 <日期>"并在 CONSTRUCTION_STATUS.md 标注"APP 流程建设闭环（B0-B9 全部验收通过）"；打回 → 同通用规则。
```
