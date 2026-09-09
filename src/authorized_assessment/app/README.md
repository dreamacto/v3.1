# app/ —— APP 流离线评审引擎（B5/B6 施工批次）

APP 流（Android APK/XAPK、iOS IPA）的离线评审引擎宿主。施工方案：
`docs/APP_WORKFLOW_CONSTRUCTION_PLAN.md` §5.3；批次划分见 §8（B5=静态引擎，B6=认证/
对账/云引擎）。全部模块**纯离线**：只消费操作员提供的本地材料与既有只读证据做候选层
筛选/清单构建，永不发请求、永不重复执行探测（`duplicate_execution=false`）。

## 模块地图

| 模块 | 批次 | 服务的 phase（契约） | 产物 |
|---|---|---|---|
| `app_review_common.py` | B5 | 共享引擎（app 契约族 12-key review JSON 骨架 / coverage 六值 / observation→evidence 映射 / confirm 升级门） | —（被各域复用） |
| `hardening_integrity_review.py` | B5 | `package_integrity_hardening_review`（`app_storage_package_schema`，七分支） | `artifacts/app/package/hardening-review.json` |
| `static_extraction.py` | B5 | `package_inventory` / `package_unpack_decompile` / `source_reconstruction` / `static_analysis` 的编排原语 | 解包输出 + `artifacts/decoding-ledger.csv` 记账 + manifest/secrets/SDK 索引 |
| `webview_bridge_review.py` | B5 | `webview_bridge_links`（`app_webview_schema`，七分支） | `artifacts/app/webview/` 三 CSV |
| `ipc_component_review.py` | B5 | `ipc_component_boundary`（`app_ipc_schema`，七分支，App 特有） | `artifacts/app/ipc/` 两 CSV |
| `platform_login_exchange.py` / `session_token_lifecycle.py` / `signature_replay_review.py` | B6 | `app_auth_schema` 三 phase | `artifacts/app/auth/` 三 JSON |
| `local_data_exposure.py` / `crypto_secret_review.py` | B6 | `app_storage_package_schema` 两 phase（行内 platform 列 android/ios） | `artifacts/app/storage|crypto/` JSON |
| `static_dynamic_reconciliation.py` | B6 | `app_reconciliation_schema`（五分支，十态行级） | `artifacts/app/reconciliation/static-dynamic-endpoints.csv` |
| `cloud_function_review.py` / `cloud_storage_review.py` / `third_party_boundary_review.py` | B6 | `app_cloud_schema` 三 phase | `artifacts/app/cloud/` 产物 |

## 复用边界（方案 §5.3，重要）

- **分支常量不同的引擎复用"代码模式"，不 import miniapp 常量**：APP 的 hardening 七分支
  （新增 `signing_integrity`/`hardening_obfuscation_markers`/`debug_info_exposure`）与
  App 语境 auth 分支均与 xcx 不同名，因此 app 包内自包含定义分支/证据形态/映射/升级
  规则常量；共享实现的单一来源是本包 `app_review_common.py`（克隆
  `miniapp/platform_login_exchange.py` 的引擎模式）。
- **底层 triage 引擎照常复用**：`authorized_assessment.triage.injection_candidates`
  （`rule_satisfied`/`aggregate_category_status`/`validate_category_summary`/状态枚举）
  是全仓单一实现，app 引擎直接 import，不复制。
- **CSV 助手单一实现**：`read_inventory_csv`/`write_inventory_csv`/`assign_row_ids`
  定义于 `webview_bridge_review.py`，`ipc_component_review.py` 复用；deeplink 队列
  `scheme_type`/`jump_target` 枚举与 webview 深链队列同源（同一常量再导出）。
- **skill 脚本自包含**：`.agents/skills/app/scripts/{init,audit}_app_engagement.py`
  不 import 本包（可独立运行）；契约↔引擎↔init 种子三方一致性由
  `tests/test_app_contract_sync.py` 与 `scripts/maintenance/validate_run_contracts.py`
  锁定。

## 红线（写入各模块 docstring 与常量）

- **只观察不绕过**：不做重打包、篡改、脱壳、绕过 pinning、设备攻击；加固/壳特征
  （附录 F）只记 signal 永不升级；任何绕过动作 = `device_instrumentation`/
  `app_hardened_unpack` 审批门（双钥匙）。
- **工具路径不硬编码**：`static_extraction` 只执行 `tools/tool_registry.json` 中
  status=active 且位于 `tools/managed/app/` 下的登记路径（与 gov_exercise_config
  tools 白名单交叉核对），其余 fail-closed；审批门工具（frida/objection/
  FRIDA-DEXDump/BlackDex）在 registry 为 unavailable，天然被拒。
- **子进程纪律**：超时 600s/包、输出截断、stderr 落 `<ws>/logs/`、失败（含入口文件
  核验失败）写 `decoding-ledger.csv`，成功也记账（一行一次尝试）。
- **敏感值不进输出**：secrets 扫描只记 `pattern_id + file:line`，匹配值不进任何
  返回值/日志/CSV；发现密钥字符串但无法证明有效性时只能是 secret_candidate。

## 测试与校验

- `tests/test_app_contract_sync.py`：契约 ↔ 引擎 ↔ init 种子三处同源（分支/产物路径/
  CSV 表头/行级枚举/12-key 骨架/decoding-ledger 字段）。
- `tests/test_app_static_engine.py`：临时目录假 manifest/资源文件、子进程 mock、
  失败→ledger 记账、registry fail-closed、离线性（AST 无网络 import）。
- `python scripts/maintenance/validate_run_contracts.py`：在线校验 B5 覆盖模块的
  契约↔引擎同步（B6 模块落地后扩展）。
