# APP 流程施工验收台账

> 依据：docs/APP_WORKFLOW_CONSTRUCTION_PLAN.md §8（批次运行规则）与附录 J（验收提示词）。
> 规则：每批完工后由独立验收会话按附录 J 对应提示词逐项验收；结论只有通过/打回两种，打回须列失败项与证据，返工后同批次追加"复验"记录。

| 批次 | 日期 | 结论 | 逐项证据 | 验收会话 |
|---|---|---|---|---|
| B1（Skill 骨架，W16） | 2026-09-09 | **B1 验收 · 通过** | 九项全 PASS，逐项证据摘要如下 | 独立验收会话（ZCode，2026-09-09） |
| B2（init + 三流路由，W17） | 2026-09-09 | **B2 验收 · 通过** | 五项全 PASS，逐项证据摘要如下 | 独立验收会话（ZCode，2026-09-09） |
| B3（audit，W18） | 2026-09-09 | **B3 验收 · 通过** | 五项全 PASS，逐项证据摘要如下 | 独立验收会话（ZCode，2026-09-09） |
| B4（契约，W19 上半） | 2026-09-09 | **B4 验收 · 通过** | 五项全 PASS，逐项证据摘要如下 | 独立验收会话（ZCode，2026-09-09） |
| B5（静态引擎，W19 中段） | 2026-09-09 | **B5 验收 · 通过** | 五项全 PASS，逐项证据摘要如下 | 独立验收会话（ZCode，2026-09-09） |
| B6（认证/对账/云引擎，W19 收尾） | 2026-09-09 | **B6 验收 · 通过** | 五项全 PASS，逐项证据摘要如下 | 独立验收会话（ZCode，2026-09-09） |
| B7（配方与导航，W20 上半） | 2026-09-09 | **B7 验收 · 通过** | 五项全 PASS，逐项证据摘要如下 | 独立验收会话（ZCode，2026-09-09） |

## B1 验收 · 通过（2026-09-09，逐项证据摘要）

1. **文件存在 — PASS**：`.agents/skills/app/`、`.claude/skills/app/`、`.opencode/skills/app/` 三处均为同一 7 件（SKILL.md + references/{workflow,test-matrix,data-to-test-playbook,package-analysis,artifact-contract,evidence-reporting}.md），`find` 各列 7 个文件，无多余（无 scripts/，未越界到 B2/B3）。
2. **内容锚点 — PASS**：SKILL.md `name: app`（:2）、`phase_status.app.json`（:14,115,140,142,145,162）、`device_instrumentation`/`app_hardened_unpack`（:12 审批门列举）、`user_supplied_initial_target`（:81）、拒绝一次性执行条款=约束 9 "Refuse end-to-end requests"（:20）。与 xcx 并排 diff 抽查两段：约束 1 差异仅为硬停清单换 device_instrumentation/app_hardened_unpack + 重量级换 dynamic_setup/dynamic_mapping/reporting；细微发现处置换移动端信号清单（壳特征/manifest 权限/exported 组件/allowBackup/调试开关/root 检测）——均在底稿差异清单内；约束 0/4-8、AI 结论模板、四问否决、成立最小链条与 xcx 逐字一致（diff 无其他差异）。
3. **workflow.md 33 phase — PASS**：脚本解析方案附录 B 种子（33 phase）逐一比对 `.agents/skills/app/references/workflow.md`：缺失清单为空（33/33 命中），`###` 标题 33 个且顺序与附录 B 一致（dynamic_setup/dynamic_mapping 两标题带"（重量级）"后缀，与方案 §4 表格自身标注一致，非缺失）；7 节结构与 xcx workflow.md 同构（Intake routing→Initial decoding→Static→Dynamic→Backend/business→Validation/closure→Resume logic）。
4. **test-matrix.md — PASS**：MASTG-TEST-0001（:12 STORAGE 行）、MASTG-TEST-0281（:19 PRIVACY 行）在场；`## package_integrity_hardening_review`（:84，含七分支+MASTG-TEST-0045/0051/0088/0093）与 `## ipc_component_boundary`（:106，含七分支+MASTG-TEST-0028/0075）两节齐全。
5. **package-analysis.md — PASS**：加固特征表含 libjiagu（:69 360 加固）、libDexHelper（:70 梆梆）、libexecmain（:71 爱加密）、libshella（:72 腾讯乐固，前缀匹配规则注明）；apktool_3.0.3 实测命令（:34，`d -f -o`）与 jadx.bat 实测命令（:35，1.5.6 `--deobf-min 3 --deobf-max 9`）与方案 §7.1 一致；红线节 `## 7. 红线：壳包不自动脱壳（审批门 app_hardened_unpack）`（:106-108，"壳包解包默认 blocked；本项目对加固壳包不自动脱壳"）。
6. **镜像一致 — PASS**：`python scripts/check_skill_drift.py` 退出码 0（canonical=.agents/skills，39 文件，.claude/.opencode 两镜像 missing/extra/changed 均为空）。
7. **文档引用 — PASS**：`python scripts/check_doc_drift.py` 退出码 0（"无文档漂移：所有被引用路径均存在"）。
8. **范围纪律 — PASS**：B1 时间窗（2026-09-09 13:42-13:47，21 件 mtime 聚类）内，剪枝扫描（排除 runs/engagements/.git/.venv/.zcode/tools 等运行时目录）确认改动仅为三处 `skills/app/` 21 件 + `CONSTRUCTION_STATUS.md`（施工提示词 I-B1 收尾动作明确要求的 W16 行更新，属验收项 9 的前置动作，非越界）；app skill 目录内无 scripts/ 等越界产物。
9. **台账 — PASS**：CONSTRUCTION_STATUS.md:25 W16 行状态 = "已落地(待验收)"，备注含自验结果摘要（check_skill_drift=0、33/33 阶段比对等）。

**判定**：全部 PASS → B1 验收通过；W16 备注追加"已验收 2026-09-09"。下一批次 B2（init+路由，W17）可开工。

## B2 验收 · 通过（2026-09-09，逐项证据摘要）

1. **文件存在 — PASS**：`.agents/skills/app/scripts/init_app_engagement.py`（41,082B）与 `phase_status_routing.py`（3,870B）在位；`tests/{test_app_phase_status_routing,test_app_init_engagement,test_app_triple_stream_isolation}.py` 三件齐全；`.claude/skills/app/scripts/` 与 `.opencode/skills/app/scripts/` 双镜像在位。
2. **行为重放（§7.4 四用例）— PASS**：独立验收会话以临时目录脚本直载 canonical 路由模块重放，四用例全过：① 共址 wz+xcx 游标、缺 app 游标 → `APP_PHASE_STATUS_MISSING` 且 path=None；② `for_write=True` 仅提议 `phase_status.app.json`（stream=app，不落盘）；③ app 游标在场 → 解析 stream=app（wz 游标故意写坏 JSON 仍解析成功，证明不读 wz）；④ stream 字段缺失 → 防御性默认 app。另加验 3 项：外流游标误复制为 phase_status.app.json（无 stream、含 xcx 阶段名）→ `APP_PHASE_STATUS_INVALID` 拒绝；stream=miniapp_xcx → `APP_PHASE_STATUS_STREAM_MISMATCH`；route_metadata 形状正确。注：首轮重放脚本的 AttributeError 系验收脚本自身 importlib 未注册 sys.modules（Python 3.14 dataclass 注解处理）所致，修正验收脚本后复跑全过，非交付缺陷。
3. **种子核对 — PASS**：临时目录跑 `init_app_engagement.py com.example.smoke --output <tmp> --platform android --name Smoke --operator Test`：phases 数=33 且名称/顺序/required/artifacts 与附录 B 逐一一致；substatuses 12 组键与附录 B 精确相等且值全空（hardening 7/reconciliation 5/platform_login 5/session 5/signature 4/local 5/crypto 4/webview 7/ipc 7/cloud_fn 3/cloud_storage 3/third_party 2）；stream=app、status_file=phase_status.app.json、authorization=complete（identity/platform_identification 因提供字段自动 complete，符合 §7.2 语义）；engagement.json 含 `network_accessed_by_initializer: false`；§5.8 骨架抽查（app.json/scope/hosts/endpoints/materials/review_ledger.csv、materials/original|working、artifacts/evidence/notes/logs/sessions/reports）无缺失；`--resume` 换不同输入 → 退出码 3 "ERROR: Resume input does not match the existing engagement."（hash 校验在 init_app_engagement.py:742-748），同输入 resume 正例退出码 0；临时目录已删除。注：验收脚本首轮把该报错文案误判 FAIL（关键词表未含 "does not match"），核对代码后撤销，行为符合"--resume 传入不同输入必须报错"。
4. **测试 — PASS**：`.venv/Scripts/python.exe -m pytest tests/test_app_phase_status_routing.py tests/test_app_init_engagement.py tests/test_app_triple_stream_isolation.py -q` → **28 passed**（7+15+6），覆盖四用例锁定、附录 B 种子锁定、8 类输入分类、零网络断言、resume hash 正负例、共址三流隔离（resume 后 wz/xcx 游标字节级不变、无 resume 拒绝且不写盘）。唯一 warning 为 `PytestCacheWarning`（本机 `.pytest_cache` 目录权限异常致 pytest 无法写缓存），系环境噪音，与交付无关。
5. **镜像一致 / 范围纪律 / W17 台账 — PASS**：两脚本 × 两镜像共 4 组 `cmp` 逐字节一致；`python scripts/check_skill_drift.py` 退出码 0（41 文件，missing/extra/changed 均空）；范围纪律：B2 施工窗（2026-09-09 15:18-15:30）内新增文件全部落在允许路径集（三处 `skills/app/scripts/` + `tests/test_app_*.py`×3），90 个已跟踪改动文件的 mtime 除 `CONSTRUCTION_STATUS.md`（15:30，I-B2 收尾动作明确要求的 W17 行更新，同 B1/W16 先例）外全部 ≤2026-09-08，无越界；CONSTRUCTION_STATUS.md W17 行状态 = "已落地(待验收)"，备注含自验摘要。

**判定**：全部 PASS → B2 验收通过；W17 状态改"已落地(已验收)"、备注追加"已验收 2026-09-09"。下一批次 B3（audit，W18）可开工。

## B3 验收 · 通过（2026-09-09，逐项证据摘要）

1. **文件存在 — PASS**：`.agents/skills/app/scripts/audit_app_engagement.py`（64,502B）在位；`.claude/skills/app/scripts/` 与 `.opencode/skills/app/scripts/` 双镜像在位且与 canonical `cmp` 逐字节一致；`tests/test_app_audit_engagement.py`（26,654B）在位。
2. **测试全绿 + 负例覆盖 — PASS**：`.venv/Scripts/python.exe -m pytest tests/test_app_audit_engagement.py -q` → **26 passed, 1 warning**（PytestCacheWarning 环境噪音，同 B2 先例）。四项必需负例均有专测锁定：分支未记录 `test_unrecorded_branch_blocks_closure`（:270）、缺 artifact `test_missing_review_artifact_blocks_closure`（:299）、confirmed 缺证据 `test_confirmed_ledger_item_without_evidence_blocks_closure` → state=EVIDENCE_PENDING（:322-330）、候选无 disposition `test_active_candidate_without_disposition_blocks_closure` → state=REVIEW_PENDING（:353-361）；另有加验负例：分支值未证实、tested CSV 无行、非法 substatus/未知分支、对账判定行缺 reason、ipc/webview 行枚举校验、not_applicable 缺 reason、缺 app 游标 fail-closed、放宽 device gate 拒绝；正例含最小可闭合工作区（CLOSED+exit 0）与 CLI exit 0+JSON。源码级零网络断言（无 socket/requests/urllib/http.client/subprocess，验收 grep 复核一致）。
3. **实测（临时目录建区→audit --json）— PASS**：临时目录 `init_app_engagement.py com.example.b3accept --output <tmp>/ws`（exit 0，§5.8 骨架齐全）→ `audit_app_engagement.py <ws> --json`：**exit=1**（新工作区不可闭合，符合"退出码可为 1"预期）、stderr 空、无 traceback；JSON 结构化未闭合清单字段齐全：state=AUTHORIZATION_PENDING、stream=app、issues 列表（"active testing authorization is not explicitly confirmed"）、incomplete_core_phases 27 项、phase_counts{complete:3,pending:30}、open_review_items/missing_evidence_items/unresolved_hosts 等。附加实弹负例重放：临时工作区强制 `package_integrity_hardening_review` status=complete 而 7 分支 substatus 留空 → audit exit=1、无 traceback、issues 出现 "package_integrity_hardening_review: phase complete but branch package_version_inventory has no recorded substatus"。两处临时目录均已删除。
4. **只读性 — PASS**：抽样 4 文件（phase_status.app.json / engagement.json / app.json / hosts.csv）audit 前后 sha256 逐字节一致；加强核验：全工作区 32 文件全树 sha256 在一次完整 audit 运行（exit 1）前后 diff 为空；测试套件另有 `test_audit_is_read_only` 锁定。
5. **镜像一致 / 范围纪律 / W18 台账 — PASS**：`python scripts/check_skill_drift.py` 退出码 0（42 文件三处一致，missing/extra/changed 均空）；范围纪律：B3 时间窗（2026-09-09 15:35 后）跟踪文件仅 `CONSTRUCTION_STATUS.md`（16:18，I-B3 收尾动作明确要求的 W18 行更新，同 B1/B2 先例），新增/改动文件仅 audit 三处（16:14:08 canonical + 16:14:20 双镜像）+ 测试（16:14:40）；B4+ 范围（contracts/app_*.json、src/authorized_assessment/app/、prompts/配方APP）未创建未触碰；`skills/app/scripts/__pycache__/` 为 pytest importlib 运行缓存（.gitignore:17 已忽略，非交付物）；CONSTRUCTION_STATUS.md:27 W18 行状态 = "已落地(待验收)"，备注含 26 用例自验摘要与检查族说明。

**判定**：全部 PASS → B3 验收通过；W18 状态改"已落地(已验收)"、备注追加"已验收 2026-09-09"。下一批次 B4（契约，W19）可开工。

## B4 验收 · 通过（2026-09-09，逐项证据摘要）

1. **文件存在 — PASS**：contracts/ 下六件 app_*.json 全部在场：app_auth_schema（5,987B）、app_storage_package_schema（7,218B）、app_reconciliation_schema（5,183B）、app_webview_schema（7,610B）、app_ipc_schema（6,895B）、app_cloud_schema（7,463B），mtime 2026-09-09 16:56-16:57 聚类；git status 均为新增未跟踪文件（本批交付物，与 miniapp_* 契约并列）。
2. **附录 B 一致（脚本比对）— PASS**：验收会话临时脚本解析 docs/APP_WORKFLOW_CONSTRUCTION_PLAN.md 附录 B JSON 种子（33 phase，stream=app，status_file=phase_status.app.json；先 diff 确认项目内与桌面副本逐字节一致后以项目内为准）逐契约比对：12 个契约 phase 的分支集合与产物路径全部一致，分支名精确相等（连顺序都无差，脚本对顺序差单独报告但为零命中）；覆盖完整性核对：附录 B 全部 12 组带 substatuses 的 phase 与六契约分派集合双向相等（无遗漏 phase、无多余 phase）。单产物（artifact 键）与多产物（artifacts[].artifact：webview 三 CSV / ipc 两 CSV）两种形状均覆盖。比对脚本与中间产物置于系统临时目录，验收后已删除。
3. **validator 正例 + 负例 — PASS**：正例 `.venv/Scripts/python.exe scripts/maintenance/validate_run_contracts.py` → "run 契约校验通过"、退出码 0。接入核实：REQUIRED_APP_CONTRACTS 六件清单（validate_run_contracts.py:114-121）+ main :2202 调用 check_app_contracts（:1590-1945，契约 ↔ init PHASE_BRANCHES/PHASE_ARTIFACTS/REVIEW_CSV_ARTIFACTS/RECONCILIATION_ENDPOINT_STATES 与 audit 行级枚举/判定子集/authorization_basis 交叉校验；实现常量从仓库真实代码加载、契约数据从 --root 读取，篡改负例有效）。负例：临时目录复制 contracts/ 全目录 → 未篡改对照运行退出 1（系临时根缺仓库其他受检文件所致）但 app_ 违例=0，证明六契约对真实 init/audit 种子校验干净；再篡改 app_auth_schema.json signature_replay 分支 nonce_timestamp→nonce_timestamp_TAMPERED → 退出码 1，违例精确命中 "app_auth_schema.phases.signature_replay.branches drift against init seed"。临时目录与中间产物已全部删除。
4. **红线在场 — PASS**：app_auth_schema.json red_lines 含 "signature_replay 永不自动重放任何请求（含只读）；写操作/并发验证仍归审批门"（:87，description :4/:31 同步在场）；app_storage_package_schema.json red_lines 含 "APP_NO_REPACKING_RULE：不做重打包、篡改、脱壳、绕过 pinning 或设备攻击…"（:87）与 "…只能是 secret_candidate（未证实线索，8 状态模型记 signal）…不做 key 有效性探测、不发请求"（:88）。三项均在 red_lines 数组内（非仅 description 提及），validator 红线专项检查（:1635、:1659、:1663）通过佐证。
5. **范围纪律 + W19 台账 — PASS**：B4 时间窗（2026-09-09 16:40-17:15）定向 mtime 扫描（contracts/scripts/src/tests/tools/docs/prompts/三镜像 skills/app + 根目录）：B4 内容严格落在允许路径集——contracts/app_*.json 六件（16:56-16:57）+ scripts/maintenance/validate_run_contracts.py（16:59:35）+ 台账/状态文件（docs/APP_CONSTRUCTION_ACCEPTANCE.md 16:46、CONSTRUCTION_STATUS.md 17:01 W19 行更新，批次规则允许，同 W16-W18 先例）；窗口内其余触碰（scripts/maintenance/postcheck.py、report_docx.py、evidence_builder.py、tests/test_report_docx_structure.py、oob_hits.jsonl）经内容核查与 app 契约零关联（grep 六契约名/REQUIRED_APP_CONTRACTS 均 0 命中），定性为同一工作树中用户并行报告域工作，非 B4 越界；app references 两镜像 mtime 触碰（16:55-16:56）无内容变化，check_skill_drift.py 退出码 0（42 文件三处逐字节一致）。CONSTRUCTION_STATUS.md W19 行状态="施工中(B4 已落地待验收)"，备注含"B4 契约完成"及自验摘要。

**判定**：全部 PASS → B4 验收通过；W19 行状态更新为"施工中(B4 已验收，B5/B6 待开工)"、备注追加"已验收 2026-09-09"。下一批次 B5（静态引擎，W19 中半）可开工。

## B5 验收 · 通过（2026-09-09，逐项证据摘要）

1. **文件存在 — PASS**：src/authorized_assessment/app/ 恰 7 件（__init__.py 97B、README.md 5,018B、app_review_common.py 19,696B、hardening_integrity_review.py 14,015B、static_extraction.py 36,405B、webview_bridge_review.py 14,011B、ipc_component_review.py 10,651B，mtime 2026-09-09 18:04-18:26 聚类）＋ tests/{test_app_contract_sync.py 22,442B、test_app_static_engine.py 22,374B}，九件全在；git status 均为新增未跟踪文件（本批交付物）；app/ 目录内无多余交付文件（__pycache__ 为 pytest 运行缓存，同 B3 先例）。
2. **三处同源（脚本比对）— PASS**：验收会话临时脚本（系统临时目录，验收后删除）解析 docs/APP_WORKFLOW_CONSTRUCTION_PLAN.md 附录 B JSON 种子，与契约、引擎常量三方比对：package_integrity_hardening_review 七分支在 app_storage_package_schema.json ↔ hardening_integrity_review.HARDENING_REVIEW_BRANCHES ↔ 附录 B 种子全等（含顺序），产物路径 artifacts/app/package/hardening-review.json 三方一致（引擎为单产物常量 HARDENING_REVIEW_ARTIFACT）；webview_bridge_links 七分支三方全等（含顺序），三 CSV 产物路径一致且 WEBVIEW_BRANCH_ARTIFACTS 键序=分支序；ipc_component_boundary 七分支三方全等（含顺序），两 CSV 产物路径一致，IPC_BRANCH_ARTIFACTS 键集=分支集（dict 插入序按产物分组：5 组件分支→component-inventory.csv、2 深链分支→deeplink-review-queue.csv，语义合理非漂移）。
3. **子进程纪律锚点 — PASS**：static_extraction.py docstring"只观察不绕过"（:4）且逐条落实现：DEFAULT_TIMEOUT_SECONDS=600（:43）传入 subprocess.run(timeout=…)（:305），TimeoutExpired→reason="timeout after Ns" 并记账；输出上限 MAX_CAPTURE_LINES=200/MAX_CAPTURE_CHARS=4000（:44-45），账本 notes 只取截断摘录首行 120 字符；失败（non-zero exit/超时/入口核验失败）追加 decoding-ledger.csv status=failed 行、成功也记账（append_decoding_ledger_row :195，不静默）；工具路径 resolve_managed_tool（:138）fail-closed 链：registry 加载失败/未注册/非 active/越界 tools/managed/app 前缀/磁盘缺失/gov_exercise_config.json tools 白名单 {base} 模板不匹配→全部拒绝执行；grep 全模块无硬编码绝对路径（唯一命中为测试自身负例断言 tests/test_app_static_engine.py:410）；"只观察不绕过"在 hardening docstring（:5）、OBSERVE_ONLY_RULE（:168）、HARDENING_INVARIANTS（:172）三处在场。
4. **测试全绿 + validator — PASS**：.venv/Scripts/python.exe -m pytest tests/test_app_contract_sync.py tests/test_app_static_engine.py -q → **40 passed, 1 warning**（PytestCacheWarning：.pytest_cache/v/cache WinError 183，环境噪音同 B2-B4 先例，与交付无关）；python scripts/maintenance/validate_run_contracts.py → "run 契约校验通过"退出码 0；全量 .venv python -m pytest -q → **1712 passed, 0 failed**（64s，与 W19 自验备注一致，无回归）。加验 check_app_engine_sync 真实生效（validate_run_contracts.py:2021 定义、:2480 接入 main 校验链）：临时目录复制 contracts/ 全目录→未篡改对照 app_* 违例=0（临时根噪音 1 项为缺无关受检文件，同 B4 先例）；篡改 app_storage_package_schema.json hardening 分支 signing_integrity→signing_integrity_TAMPERED→exit 1，同时命中 "package_integrity_hardening_review.branches drift against init seed" 与 "branches drift against engine" 双违例；临时目录与中间产物已全部删除。
5. **范围纪律 + W19 台账 — PASS**：B5 时间窗（2026-09-09 17:10-19:00）定向 mtime 扫描（git 跟踪改动全集＋未跟踪路径逐一核查）：窗口内触碰严格落在允许路径集——src/authorized_assessment/app/ 7 件（18:04-18:26）＋ tests/ 两测试（18:20-18:21）＋ scripts/maintenance/validate_run_contracts.py（18:23:31，B5 允许路径集第 7 项）＋ CONSTRUCTION_STATUS.md（18:26:56，I-B5 收尾动作明确要求的 W19 行更新，同 W16-W19 先例）＋ docs/APP_CONSTRUCTION_ACCEPTANCE.md（17:20，B4 验收会话台账写入）；窗口内其余触碰仅 tmp_ins_analysis/eng_ins_app_20260906/ 两件报告（18:03:56-57，B5 开工前 1 分钟；内容为仪器信息网 APP 密钥硬编码报告 v3 修订，grep B5/引擎模块关键词 0 命中），定性为同工作树用户并行报告域工作，非 B5 越界；docs/APP_WORKFLOW_CONSTRUCTION_PLAN.md（mtime 09-07）与 miniapp/policy 契约既有 M 改动（09-02/09-07）均不在窗口；check_skill_drift.py 退出码 0（42 文件三镜像一致，B5 未触碰 skills）。CONSTRUCTION_STATUS.md W19 行状态="施工中(B4 已验收，B5 静态引擎完成待验收，B6 待开工)"，备注含"B5 静态引擎完成"及自验摘要（40 用例全绿/validator=0/全量 1712 passed）。

**判定**：全部 PASS → B5 验收通过；W19 行状态更新为"施工中(B4 已验收，B5 已验收，B6 待开工)"、备注追加"已验收 2026-09-09"。下一批次 B6（认证/对账/云引擎，W19 收尾）可开工。

## B6 验收 · 通过（2026-09-09，逐项证据摘要）

1. **九件交付物在场 — PASS**：src/authorized_assessment/app/ 下 platform_login_exchange.py、session_token_lifecycle.py、signature_replay_review.py、local_data_exposure.py、crypto_secret_review.py、static_dynamic_reconciliation.py、cloud_function_review.py、cloud_storage_review.py、third_party_boundary_review.py 九模块与 tests/test_app_review_engines.py（18 个 test 函数）全部存在。
2. **分支同源（脚本比对）— PASS**：验收会话临时脚本（系统临时目录，验收后删除）解析 docs/APP_WORKFLOW_CONSTRUCTION_PLAN.md 附录 B JSON 种子，与契约、引擎常量三方比对九 phase 全部一致：auth 三 phase——platform_login_exchange 五分支（platform_login_exchange.PLATFORM_LOGIN_BRANCHES ↔ app_auth_schema.phases.platform_login_exchange.branches ↔ 附录 B substatuses）、session_token_lifecycle 五分支（SESSION_TOKEN_BRANCHES）、signature_replay 四分支（SIGNATURE_REPLAY_BRANCHES），全等含顺序；reconciliation 五分支（RECONCILIATION_BRANCHES：static_endpoint_base/dynamic_endpoint_base/match_status_classification/hidden_flow_identification/stale_entry_disposition）；local 五分支（LOCAL_DATA_BRANCHES）、crypto 四分支（CRYPTO_SECRET_BRANCHES）；cloud 三 phase——cloud_function_testing 三分支（CLOUD_FUNCTION_BRANCHES）、cloud_storage_acl_testing 三分支（CLOUD_STORAGE_BRANCHES）、third_party_sdk_platform_boundary 两分支（THIRD_PARTY_BRANCHES）。九 phase 契约 artifact 与附录 B artifacts 逐一相等，引擎产物路径常量在场（PLATFORM_LOGIN_REVIEW_ARTIFACT/SESSION_TOKEN_REVIEW_ARTIFACT/SIGNATURE_REPLAY_REVIEW_ARTIFACT/LOCAL_DATA_REVIEW_ARTIFACT/CRYPTO_SECRET_REVIEW_ARTIFACT/RECONCILIATION_ARTIFACT/CLOUD_FUNCTION_REVIEW_ARTIFACT/CLOUD_STORAGE_REVIEW_ARTIFACT/THIRD_PARTY_BOUNDARY_ARTIFACT）。
3. **红线锚点 — PASS**：signature_replay_review.py grep requests/httpx/urllib/socket/http.client/aiohttp 零命中（无任何网络/请求代码路径），"永不自动重放任何请求（含只读）"三处在场（:7 docstring、:130 与 :139 INVARIANTS）；local_data_exposure.py 凭证纪律在场（:11 docstring、LOCAL_DATA_MATERIAL_RULE"不读取凭证文件…敏感值不复制到普通日志/报告/prompt/ledger/交接内容"、LOCAL_DATA_INVARIANTS 同语义行），secret_candidate 红线经契约级承载（local 属 app_storage_package_schema，其 red_lines 第 2 条即 secret_candidate）；crypto_secret_review.py 凭证纪律与 secret_candidate 红线均在场（SECRET_CANDIDATE_RED_LINE :136"只能是 secret_candidate…不做 key 有效性探测、不发请求"、CRYPTO_MATERIAL_RULE :140"不读取凭证文件、不复制密钥/AppSecret 原文"、CRYPTO_SECRET_INVARIANTS :147 起首条即 secret_candidate 红线）；static_dynamic_reconciliation.py"永不发新请求"四处在场（:6 docstring、:92 与 :105 invariants"对账为纯离线比较：永不发新请求，本引擎不含任何发请求代码路径"、:221 函数 docstring）。
4. **测试全绿 + validator — PASS**：.venv/Scripts/python.exe -m pytest tests/test_app_review_engines.py -q → **18 passed, 1 warning**（PytestCacheWarning 环境噪音，同 B2-B5 先例）；python scripts/maintenance/validate_run_contracts.py → "run 契约校验通过"退出码 0；全量 .venv python -m pytest -q → **1730 passed, 0 failed**（73s，= B5 的 1712 + B6 新增 18，与 W19 自验备注一致，无回归）。加验 check_app_engine_sync 补齐 B6 九模块后真实生效：临时目录复制 contracts/ 全目录→篡改 app_auth_schema.json platform_login_exchange 首分支 oauth_code_one_time→oauth_code_one_time_TAMPERED→退出码 1，命中 "app_auth_schema.phases.platform_login_exchange.branches drift against init seed" 与 "branches drift against engine" 双违例（另有 1 项临时根噪音缺 tools/tool_registry.json，同 B4/B5 先例）；未篡改基线 validator=0 无 app 违例；临时目录与中间产物已全部删除。
5. **范围纪律 + W19 台账 — PASS**：B6 时间窗（2026-09-09 19:35-19:50）定向 mtime 扫描（git 跟踪改动全集＋83 项未跟踪路径逐一核查）：窗口内触碰——九引擎（19:35:48-19:44:09）＋ tests/test_app_review_engines.py（19:44:24）＋ scripts/maintenance/validate_run_contracts.py（19:45:59，check_app_engine_sync 补齐 B6 九模块）＋ CONSTRUCTION_STATUS.md（19:50:14，W19 行更新，批次规则允许，同 W16-W19 先例）＋ docs/APP_CONSTRUCTION_ACCEPTANCE.md（18:57:25，B5 验收会话台账写入，窗口外前置）。contracts/app_auth_schema.json（19:47:05）为 B4 交付物（B6 允许路径集外）且窗口内有 mtime 触碰，经内容复核无漂移：三 phase 5/5/4 分支、red_lines 5 条（含"永不自动重放"与凭证纪律）、invariants 7 条、coverage_substatus 六值引用 coverage_substatus_schema，与附录 B/引擎三方全等、validator 基线 0 违例——与 W19 备注"B6 负例篡改 app_auth 分支名命中 3 条 drift"对照，定性为负例实验触碰-还原，非内容改动；skills 三镜像 check_skill_drift.py 退出码 0（42 文件一致，B6 未触碰 skills）；tmp_ins_analysis/ 窗口无触碰；其余未跟踪路径最新 mtime 均 ≤ 09-08。CONSTRUCTION_STATUS.md W19 行状态="已落地(待验收)（B4-B6 三段齐）"，备注含"B6 认证/对账/云引擎完成"及自验摘要（18 用例全绿/validator=0/全量 1730 passed），与实测一致。

**判定**：全部 PASS → B6 验收通过，W19 批次（APP 流 B4-B6 契约+引擎）整体完工；W19 行状态更新为"已落地(已验收)"、备注追加"已验收 2026-09-09"。

## B7 验收 · 通过（2026-09-09，逐项证据摘要）

1. **文件存在/修改 — PASS**：prompts/配方APP_App流程.md（5,134B，2026-09-09 20:15，git 未跟踪新文件）在位。配方P 三处：:10 输入识别行"…或已有 APP engagement：路由到 APP"、:24 配方来源行"APP：`prompts/配方APP_App流程.md`"、:53-60 "## APP 路由规则"节。配方C 规则 1（:8）与规则 6（:17）均含"APP 使用 `phase_status.app.json`（stream=app）"，规则 1 另含共址三流互不读写条款。tools/copy_prompt.py：RECIPES `"APP": "配方APP_App流程.md"`（:29）、ALIASES `"12": "APP"`（:32）、--list 展示元组含 APP（:41）、usage 提示同步 1-12（:67）。docs/CONTEXT_LOADING_MAP.yaml：workflows.app（:71-78，SKILL/workflow/test-matrix 三件）+ phases.app_* 七域（app_package_analysis/app_hardening/app_auth/app_storage_package/app_reconciliation/app_webview_ipc/app_cloud，:237 起逐一在盘）。AGENTS.md：入口表 :30（AI配方 bat 菜单 1-12 含 APP）与 :31（配方APP 行）、:68 prompts 清单加 APP、:69 skills 列表 {wz,xcx,app,fh}。README.md :42 流程描述行含 APP；docs/PROJECT_STRUCTURE.md :60 Skill 行"工作流 skill：wz/xcx/app/fh"。
2. **桌面文件（追加式）— PASS**：D:\Desktop\AI配方_一键复制.bat 菜单含 "12. APP App流程     (direct mobile app workflow)"；对照 W20 备注差异清单抽查"其余行未变"：菜单 1-11 行（A Review…R Learn）、0 Exit、PY 探测链（.venv→PATH，符合 W14"保持原样"约定）均未动，唯一其他差异为范围提示 `set /p "CH=Number (1-12): "`（与差异清单"范围提示 1-11→1-12"精确一致）。D:\Desktop\PROJECT_OVERVIEW_FOR_NEW_SESSIONS.md：路由表 :648 APP 行（"App 名称/包名、APK/IPA/XAPK、已解包 App 目录、App 流量或 APP engagement | APP"）＋权威文件表 :961 prompts/配方APP_App流程.md（W20 备注所述双行均在）。
3. **命令核验 — PASS**：python tools/copy_prompt.py --list → 12 配方全 OK，含 "APP  ->  配方APP_App流程.md  [3037 chars / OK]"；python scripts/check_doc_drift.py → "无文档漂移：所有被引用路径均存在"退出码 0；python scripts/check_skill_drift.py → status ok、42 文件三处一致退出码 0；CLM yaml 解析成功（top keys 含 workflows/phases），workflows keys = [fh, wz, xcx, app]，phases 七个 app_* 域齐全。加验 .venv pytest tests/test_context_loading_map.py + tests/test_context_loading_map_batch8.py → **15 passed**（与 W20 自验一致；REQUIRED_WORKFLOWS+"app"、REQUIRED_PHASES+七个 app_* 域经 git diff 确认，batch8 六个既有用例无回归）。
4. **内容红线 — PASS**：配方APP 审批门在阶段推进 7（:61-62"设备 root/越狱、装证书、frida/objection 注入、SSL pinning bypass、重打包、脱壳和一切写型动作必须走审批门"）与"不自动脱壳"（:56"解包失败或壳包记录 blocked/failed 原因，不能写成 not_applicable，不自动脱壳"）；配方P APP 路由规则同两项（"壳包默认 blocked，不自动脱壳"；"root/越狱、装证书、frida/objection 注入、SSL pinning bypass、重打包全部是审批门（tool_strategy.json approval_gated_phases.device_instrumentation）"）。两文件全文无真实目标/凭证：仅含本机 Burp MCP 127.0.0.1:9876、项目根路径与盘上通用文件引用，无真实域名/IP/cookie/token/密钥。加验：配方APP 与底稿 docs/APP_SKILL_DRAFT.md 第二节（第二个 ````markdown 块）脚本 diff 逐字一致（identical: True），与 W20 备注"底稿第二节逐字落盘"相符。
5. **范围纪律 + W20 台账 — PASS**：B7 施工窗（2026-09-09 20:15-20:19）git 跟踪文件 mtime 扫描（git ls-files × mtime，排除运行时目录）：窗口内改动仅 配方P（20:15:21）/配方C（20:15:36）/tools/copy_prompt.py（20:15:45）/CONTEXT_LOADING_MAP.yaml（20:16:21）/AGENTS.md（20:16:40）/README.md＋PROJECT_STRUCTURE.md（20:16:50）/tests/test_context_loading_map.py（20:19:30）/CONSTRUCTION_STATUS.md（20:19:55，W20 行更新，批次规则允许，同 W16-W19 先例）＋ 新增未跟踪 prompts/配方APP_App流程.md ＋ 桌面两文件（仓库外，B7 允许路径），全部落在 B7 允许路径集；19:45:59 的 scripts/maintenance/validate_run_contracts.py 属 B6 施工窗（19:35-19:50）内合法交付（check_app_engine_sync 补齐九模块，B6 验收记录已确认），非 B7 触碰；tests/test_context_loading_map_batch8.py（08-30）本批未动。CONSTRUCTION_STATUS.md W20 行状态 = "施工中(B7 配方/导航完成待验收，B8 待开工)"，备注含"B7 配方/导航完成，2026-09-09"及完整差异清单（与实测逐项一致）。

**判定**：全部 PASS → B7 验收通过；W20 行状态更新为"施工中(B7 已验收，B8 待开工)"、备注追加"已验收 2026-09-09"。下一批次 B8（验收收尾，W20 下半：全量 pytest/verify_offline + 样本 APK 演练）可开工。

## B8 端到端验收执行记录（2026-09-09，施工会话产出；结论待附录 J-B8 独立验收）

> 执行会话：B8 施工会话（W20 下半）。本批不写生产代码；除本台账与 CONSTRUCTION_STATUS.md W20 行外未改动任何仓库文件，演练产物全部在系统临时目录并已删除。

### 1. 全量回归与离线验收命令（命令 / 结果 / 退出码）

| # | 命令 | 结果 | 退出码 |
|---|---|---|---|
| 1 | `.venv/Scripts/python.exe -m pytest -q` | **1730 passed, 1 warning**（85.88s；warning 为 PytestCacheWarning 环境噪音，同 B2-B6 先例） | 0 |
| 2 | `.venv/Scripts/python.exe scripts/verify_offline.py --json` | status=ok，四检查（compile / skill-drift 42 文件 / doc-drift / tests 内嵌全量 1730 passed 71.77s）全 ok | 0 |
| 3 | `python scripts/maintenance/rebuild_tool_inventory.py --check` | "工具 registry 校验通过：结构完整、status 与盘上路径一致、config 候选表全覆盖、tool_strategy 引用无漂移" | 0 |
| 4 | `python scripts/maintenance/validate_run_contracts.py` | "run 契约校验通过：契约文件结构完整，状态模型与门控阈值无漂移" | 0 |
| 5 | `python scripts/check_skill_drift.py` | status=ok，42 文件三镜像零缺失/零多余/零改动 | 0 |
| 6 | `python scripts/check_doc_drift.py` | "无文档漂移：所有被引用路径均存在" | 0 |

全量用例数与 B6 验收基线一致（1730，无回归；B7 未新增测试，CLM 测试 15 passed 已在 B7 验收复核）。

### 2. 端到端演练（关键路径，方案 §11 基线 4；全程零外部网络）

**样本材料：方案 b（无操作者当场样本）**。构造最小伪 APK **目录**（已解包树形态）：AndroidManifest.xml（伪可读 manifest：exported MainActivity + `b8dryrun://` 自定义 scheme 深链 + allowBackup/debuggable/usesCleartextTraffic 三标志）+ 2 个伪 java source + assets/config.json + lib/arm64-v8a/libexample-native.so。安全性：host 全部为 RFC2606/.test 保留域（api.example-app.test、cdn.example.com、analytics/maps.example3rd.test），密钥串为 AWS 文档公开示例假密钥（AKIAIOSFODNN7EXAMPLE）；零真实目标、零请求、零下载。**"真实样本演练"已登记为待操作者提供**（演练工作区 notes/operator_tasks.md 追加条目：提供后补 apktool/jadx 标准解包链）。

**路径**：临时目录 `%TEMP%\b8-app-dryrun\`（material\ 素材 + ws\ 工作区）→ `init_app_engagement.py material --output ws --name "B8 Dryrun App" --package com.example.b8dryrun --operator B8-Acceptance --version 1.0.0` → **exit 0**，`input_type=unpacked_source / platform=android / identity=confirmed / phase_status_file=phase_status.app.json / stream=app`（classify_input 路径 ✓）；materials.csv:2 登记目录清单 sha256 `1aa6ee27…a449`（骨架路径 ✓）。之后逐阶段推进，每阶段 = phase note（notes/phase-history/）+ phase_status.app.json 游标 + notes/target-model.md 对应节追加（intake 两阶段先行，保证不跨序推进 preflight）：

| 阶段 | 关键产物 | 要点 |
|---|---|---|
| material_acquisition | materials.csv:2 notes 标注 | 演练素材性质标注（保留域/假密钥/真实样本待提供） |
| initial_decoding | artifacts/decoding-ledger.csv:2 | classify_input→unpacked_source 落台账（mode=classify_only, status=classified）；ledger 路径 ✓ |
| preflight | notes/runtime-inventory.md | apktool 3.0.3 / jadx 1.5.6 `--version` 实测 exit 0（PATH Temurin 17.0.19；registry 配对天狐 Java_11_win 在盘）；审批门工具保持 unavailable；无指定设备（只登记不连接） |
| package_inventory | artifacts/app/package-inventory.csv:2 | 结构清单 + 附录 F 加固特征扫描（libjiagu/libDexHelper/libexecmain/libshella 等）未命中——负结果显式记录（hardening_signal=none） |
| package_unpack_decompile | artifacts/decoding-ledger.csv:3 | unpacked_source 输入无包可解：already_unpacked/ok；真实 APK 的 apktool d / jadx 标准链（含失败→重试→blocked 路径）待样本，不为演练伪造解包输出 |
| source_reconstruction | artifacts/source-map.csv:2-6 + phase note | 5 文件逐 sha256 溯源；manifest 深解析：exported MainActivity（launcher + b8dryrun:// 深链，:16-31）、PushService exported=false、allowBackup/debuggable/cleartext=true、无 networkSecurityConfig；负空间（无 dex 未还原区检查、无签名材料）显式记录 |
| static_analysis | artifacts/whitebox/（sink_findings.jsonl + whitebox_review.md）+ review_ledger.csv b8-L1/b8-L2 + materials.csv:2 analyzed | whitebox_triage.py --scan 实跑：62 sink 模式 0 命中（exit 0，负结果照记）；secrets/SDK/API 路径提取；2 条 candidate 入台账（b8-L1 secret_candidate——红线：仅线索不做 key 有效性探测不发请求；b8-L2 cleartext 端点） |
| host_classification | hosts.csv:2-5 | 4 host 全分类零请求零移除：api.example-app.test=confirmation_required（归属未确认禁请求）、cdn/analytics/maps=third_party（SDK/CDN 不误报自有后端） |

游标终态：stream=app、last_completed_phase=host_classification、current_phase=package_integrity_hardening_review、11 complete / 22 pending / 0 blocked。

**演练后审计**：`audit_app_engagement.py <ws> --json` → **state=AUTHORIZATION_PENDING，exit 1，唯一 issue = "active testing authorization is not explicitly confirmed"**（离线静态演练不确认 active testing，该状态的正确输出）。一致性核对（与推进状态逐项全等）：safety_controls_recorded=true（双审批门在位）、identity_confirmed=true、material_counts={analyzed:1}、package_materials=0（unpacked_source 非包材料）且 package 三阶段 package_phase_incomplete=[]、package_inventory_records=1 / source_map_records=5、host_counts={confirmation_required:1, third_party:3} 与 hosts.csv 全等、unresolved_hosts=[]、phase_counts={complete:11, pending:22}、blocked_phases=[]、review_counts={candidate:2} 与台账 b8-L1/b8-L2 全等、open_review_items=[b8-L1,b8-L2]、missing_evidence_items=[]（candidate 不要求证据）、reporting_not_applicable=true（无可报告成果）。incomplete_core_phases 列出 19 个未推进核心阶段（含关键路径设计跳过的 package_integrity_hardening_review 与 endpoint_inventory，二者的引擎/分支已由 B5/B6 验收覆盖；动态/认证/存储/云/后端各阶段未启动）——与演练推进范围精确一致。审计后临时目录整体删除（material/ws/辅助脚本，已确认不存在）。

### 3. §11 验收基线逐项对照

1. `.agents/skills/app/` 十件齐全且三镜像 drift=0 — **达成**（check_skill_drift 42 文件三处一致）。
2. `pytest tests/test_app_* -q` 全绿、全量不回归 — **达成**（全量 1730 passed 无回归；app 测试含于全量）。
3. validator / rebuild_tool_inventory / check_skill_drift / check_doc_drift 全部退出 0 — **达成**（另有 verify_offline=ok）。
4. 样本端到端演练各留 phase note + target-model 更新，audit 一致 — **达成（伪 APK 路径）**：8 份 phase note、target-model 六节更新、audit --json 与推进状态全等；**待办：真实样本演练待操作者提供样本**（operator_tasks 已登记；J-B8 判定规则允许"通过（带待办：样本演练）"）。
5. AGENT_MANIFEST/CONSTRUCTION_STATUS/AGENTS.md/配方P 均反映 APP 流存在 — **达成**（B7 已验收；本批未改动该四文件，基线未回退）。

### 4. 发现的问题与观察（不修复，记录交回）

- **缺陷（需返工）：无。** 六命令、init→audit 全链路未发现需返工批次缺陷。
- **待办（非缺陷）**：① 真实无害样本 APK/IPA 演练待操作者提供（提供后补 apktool/jadx 实际解包链 + 失败→blocked 路径实测）；② B8 关键路径按方案 §8/§11 设计不含 package_integrity_hardening_review 与 endpoint_inventory 两阶段，真实工作区续跑时按游标回到 package_integrity_hardening_review。
- **观察（记录不改）**：① 游标 next_phase 字段为"顺序下一项"语义（init 种子同款），已完成的 static_analysis 也会出现在 next 位置，续跑会话应以 phases 列表实际状态/current_phase 为准——与 B2 已验收行为一致，非本批缺陷；② audit exit=1 是 AUTHORIZATION_PENDING 的预期表现（闭合不变量），不表示演练失败；③ verify_offline 内嵌 tests 检查会再跑一次全量 pytest（71.77s），与独立跑结果一致（1730 passed），仅耗时叠加，属已知执行成本。

## J-B8 验收 · 通过（带待办：样本演练）（2026-09-09，独立验收会话，逐项证据摘要）

1. **台账核对 — PASS**："B8 端到端验收执行记录"小节在场，六命令表含全量 pytest **1730 passed, 1 warning, exit 0** 与五项退出码（verify_offline / rebuild_tool_inventory / validate_run_contracts / check_skill_drift / check_doc_drift 均 0）；演练路径（`%TEMP%\b8-app-dryrun\` material+ws → init 命令逐字含参数）与八阶段逐阶段产物表（每阶段关键产物路径 + 要点）齐全；§11 基线五项对照与 §4 问题/待办/观察分节在场。
2. **抽查复跑（三项只读重放）— PASS**：① `.venv/Scripts/python.exe -m pytest -q` → **1730 passed, 1 warning, exit 0**（79.32s vs 记录 85.88s，机器噪音，计数/warning/退出码全同）；② `.venv/Scripts/python.exe scripts/verify_offline.py --json` → status=ok、四检查（compile / skill-drift 42 文件零缺失零多余零改动 / doc-drift / tests 内嵌 1730 passed）全 ok、exit 0；③ `python scripts/maintenance/rebuild_tool_inventory.py --check` → 校验通过消息与记录逐字一致、exit 0。三项均与记录一致。
3. **演练闭环判定 — PASS（伪 APK 路径，真实样本待提供）**：记录明确标注方案 b"真实样本演练待操作者提供"（§2 样本材料段、§4 待办①、W20 备注三处在场）；伪 APK 覆盖 classify_input（init → exit 0，input_type=unpacked_source / platform=android / identity=confirmed / stream=app）/骨架（materials.csv:2 sha256 `1aa6ee27…a449`、phase_status.app.json 游标、phase note×8、target-model 六节）/ledger（decoding-ledger.csv:2-3、review_ledger b8-L1/b8-L2）；audit --json 与推进状态一致的逐字段证据在记录（AUTHORIZATION_PENDING / exit 1 / 唯一 issue / 11 complete 22 pending / host、review、package 计数与盘上全等）。独立机制复放（本会话，临时目录 `jb8-accept-replay` 事后已删，仓库零写入）：自建最小伪解包树跑 init → exit 0 且六输出字段与记录同款（unpacked_source/android/confirmed/phase_status.app.json/stream=app/target_received）、materials.csv 登记 sha256 行、骨架目录齐全；新工作区 audit --json → state=AUTHORIZATION_PENDING、exit 1、safety_controls_recorded=true、blocked_phases=[]、missing_evidence_items=[]——与记录行为同型；**阶段算术自洽**：init 新工作区 phase_counts={complete:3, pending:30}，演练推进 8 阶段后恰为记录的 {complete:11, pending:22}；观察①同款 next_phase"顺序下一项"语义在复放中现场确认。preflight 工具声明复验：Temurin jdk-17.0.19 在盘，`java -jar apktool_3.0.3.jar --version` → 3.0.3、`jadx.bat --version` → 1.5.6，均 exit 0（registry 白名单路径 tools/managed/app/ 逐一在盘）。`%TEMP%\b8-app-dryrun` 实测不存在——记录"临时目录整体删除"声明属实。
4. **无越界 — PASS**：B8 施工窗（B7 结束 20:19:55 之后）git 跟踪文件 mtime 扫描（排除 runs/engagements/运行时目录）：窗口内改动仅 CONSTRUCTION_STATUS.md（21:19:12，W20 行，批次允许）一份；未跟踪侧仅 docs/APP_CONSTRUCTION_ACCEPTANCE.md（21:18:43，本台账，允许）一份——生产代码零触碰，与 B8 声明"除本台账与 CONSTRUCTION_STATUS.md W20 行外未改动任何仓库文件"一致。
5. **W20 台账 — PASS**：状态"施工中(B8 执行记录完成，待 J-B8 验收)"，备注含"B8 执行记录完成，2026-09-09"及六命令/演练摘要（与 B8 小节一致）。

**判定**：五项全 PASS，真实样本演练为待提供 → **J-B8 验收通过（带待办：样本演练）**；W20 行状态更新为"已落地(已验收，带待办：真实样本演练)"、备注追加"J-B8 已验收 2026-09-09"。**待办进 operator 跟踪**：操作者提供无害样本 APK/IPA 后补真实样本端到端演练（apktool/jadx 实际解包链 + 失败→blocked 路径实测），完成后在 W20 备注销项。至此 W16-W20 全部已验收，APP 流施工（B1-B8）验收闭环。

## J-B9 验收 · 打回（2026-09-09，独立验收会话，逐项证据摘要）

1. **文件存在 — PASS**：contracts/app_graph_schema.json、src/authorized_assessment/orchestration/app_graph.py、tests/test_app_graph.py、tests/test_app_graph_integration.py、tests/test_app_graph_phase_status_isolation.py 五件全部在盘。
2. **契约锚点 — PASS**（schema/代码/运行时三重核验）：① schema：`workflow={"const":"app"}`、`$defs.node.cursor_file={"const":"phase_status.app.json"}`、x-app-safety{status_file、forbidden_cursors 三游标、approval_gates=[device_instrumentation, app_hardened_unpack]、approval_gates_auto_advance=false、双钥匙 rule 在场}（contracts/app_graph_schema.json:11,27,45-52）；② 33 阶段：len(APP_PHASES)=33 程序化证实，33 阶段全部作为图节点在场，validate_app_graph 缺阶段即报错（app_graph.py:168-170），与 init 种子同源有测试锁定（test_app_graph.py:55-58）；③ 审批门不可自动推进双重体现：schema 侧 approval_gates_auto_advance=false+rule；代码侧双门 kind=approval、**出边=0**、入边全部 gates 类、供能精确（device_instrumentation←{dynamic_setup, dynamic_mapping}、app_hardened_unpack←{package_unpack_decompile}，本会话程序化核验 outbound=0 / inbound_kinds=['gates']），metadata approval_gates_auto_advance=False，validate_app_graph 对门出边/门缺失/门 task 化 fail-closed（app_graph.py:171-195；tests/test_app_graph.py:107-124）；终末 approval→verifier(terminal) 链与 wz/xcx 图 terminal 模式同型（wz_graph.py:65-68），不属双钥匙审批门。
3. **隔离证明 — PASS**：隔离测试六项全过（含于 22 passed），源码审读为真实多层断言、非空壳——①全节点 cursor_file==phase_status.app.json + 序列化产物无 wz/xcx/run_status 游标字样（test_app_graph_phase_status_isolation.py:29-35）；②跨流游标篡改 fail-closed（:38-42）；③共址实盘：同目录放置三流游标（内容含各流阶段名），app graph 全生命周期（构建/校验/from_dict 往返/序列化）前后 sha256 **字节级比对相等**，并断言图产物不含工作区路径（:50-75）——图构造不接收路径参数，该测试实际证明"图生命周期零游标 I/O"，与④互补构成完整证明链；④app_graph 模块源码零 I/O/网络 marker 断言（:78-94）；⑤wz/xcx 图同进程校验通过 + 三流游标互不串写断言（:97-108）。
4. **测试全绿 — PASS**：三件 graph 测试 → **22 passed, 1 warning, exit 0**（0.46s）；`validate_run_contracts.py` → **exit=0**（check_app_graph_contract 已接线 collect_violations :2810，结构校验+工厂/契约/init 种子三方同源交叉核验在场 :2709-2788）；全量 pytest → **1752 passed, 1 warning, exit 0**（72.5s）= B8 基线 1730 + 本批 22，无回归；1 warning 为既有 .pytest_cache ACL 环境噪音（同先例）。
5. **范围纪律 — FAIL**：允许路径集 {contracts/app_graph_schema.json, src/authorized_assessment/orchestration/app_graph.py, tests/test_app_graph*.py, scripts/maintenance/validate_run_contracts.py}（=附录 I-B9【本批只做以下文件】，且【明确不做】"不改 worker 合同之外的既有编排行为"）。实测 B9 施工窗（2026-09-09 21:42-21:46）在允许集外修改两文件，mtime+git diff+备注自认三重证据：①src/authorized_assessment/orchestration/graph.py（mtime 21:42:23；WORKFLOWS/CURSORS 两 frozenset 增补 "app"/"phase_status.app.json"，为 vs HEAD 唯一改动）；②src/authorized_assessment/orchestration/graph_validation.py（mtime 21:42:32；expected_cursor 三元式改四流映射，为 vs HEAD 唯一改动）。两处即 W21 备注第 ③ 点自称的"共享基座最小登记"——披露属实，但披露不等于授权，验收通用规则 ④"越界即打回"。orchestration 目录其余全部文件 mtime≤09-03 未触碰；tests/ 窗口内仅三个 test_app_graph*.py；W21 行验收前状态"已落地(待验收)"本身符合。

**判定**：4/5 PASS、范围纪律 FAIL → **J-B9 验收打回**；W21 状态改回"待返工"，CONSTRUCTION_STATUS.md"APP 流程建设闭环（B0-B9 全部验收通过）"标注暂缓。**返工说明（供操作者决策）**：共享基座登记经核实为功能必需——graph_validation.py:31 硬校验 workflow∈WORKFLOWS、:70 校验 cursor∈CURSORS，不登记则 app 图 validate/roundtrip 直接失败、B9 交付物无法工作，即蓝图 I-B9 白名单与"新建 app_graph.py 并接入共享基座"存在内在冲突；两处越界改动本身对既有三流判定逐字节等价、diff 最小且已在备注披露。出路二选一，由操作者定：a) **扩批**——操作者明确把 graph.py/graph_validation.py 纳入 B9 允许路径集后，按附录 J 通用规则在本批次追加"复验"记录重走本验收（五项中四项已 PASS，复验预期通过）；b) **守白名单返工**——下一轮施工会话给出不触碰共享基座的等价接入方案并保持全绿。另：xcx_graph.py 的未提交改动（XCX_PHASES 删 "retest"，mtime 09-03 21:57）经核为更早批次遗留，不属 B9 改动，不在本判定范围。

## J-B9 验收 · 复验 · 通过（2026-09-09，独立验收会话，逐项证据摘要）

**扩批授权**：操作者于本验收会话明确批准"graph.py / graph_validation.py 两个共享基座登记文件纳入 B9 允许路径集"。扩批后允许集 = {contracts/app_graph_schema.json, src/authorized_assessment/orchestration/app_graph.py, tests/test_app_graph*.py, scripts/maintenance/validate_run_contracts.py} + {src/authorized_assessment/orchestration/graph.py, src/authorized_assessment/orchestration/graph_validation.py}。按附录 J 通用规则以扩批后允许集重走验收，同批次追加本"复验"记录。

1. **零漂移核对 — PASS**：B9 全部八件交付物（schema / app_graph.py / graph.py / graph_validation.py / validate_run_contracts.py / 三测试件）mtime 均停留在原施工窗 21:42:23-21:48:58，自打回验收逐项核验以来无任何触碰——打回记录中第 1-4 项证据（文件存在、契约锚点程序化核验、隔离测试源码审读、测试全绿）原样有效，无需重验。
2. **范围纪律（扩批后重判）— PASS**：B9 施工窗实测改动全集 = schema + app_graph.py + tests/test_app_graph*.py×3 + validate_run_contracts.py + graph.py + graph_validation.py，恰好六类 ⊆ 扩批后允许路径集；orchestration 目录其余全部文件未触碰（mtime≤09-03）；tests/ 窗口内仅三个 test_app_graph*.py。全树 mtime 扫描（21:35-22:30 窗，排除 .git/.venv/缓存）佐证：除上述六类交付物与 CONSTRUCTION_STATUS.md 外，仅 oob_hits.jsonl 与 artifacts/asset_fingerprint_views/{README.md,tomcat.txt} 三件 gitignore 运行时产物在窗内有 mtime——均为本验收会话复跑全量 pytest 的追加/再生成副产物（fingerprint_ingest 生成链，mtime 22:21-22:22 与复跑时段吻合，内容时间戳佐证），非施工会话改动，零源码影响。
3. **复跑取证 — PASS**：三件 graph 测试 → **22 passed, 1 warning, exit 0**（复验实跑）；`validate_run_contracts.py` → **exit=0**（复验实跑）；全量 pytest → **1752 passed, 1 warning, exit 0**（94.7s，复验实跑）= B8 基线 1730 + 本批 22，无回归。

**判定**：五项全 PASS（范围纪律按扩批授权重判通过）→ **J-B9 复验通过，B9 已验收 2026-09-09**。W21 行状态更新为"已落地(已验收)"、备注追加"已验收 2026-09-09"；CONSTRUCTION_STATUS.md 标注"**APP 流程建设闭环（B0-B9 全部验收通过）**"——W16-W21（B1-B9）全部验收通过，B0 此前已完成，APP 流施工至此闭环。

## 建设闭环终验 · 通过（2026-09-09，独立复核会话＝蓝图编写会话，非任何施工/批次验收会话）

对当前盘上实态（不依赖批次验收记录）重放全部验收门与关键行为，结果：

| 项 | 结果 | 证据 |
|---|---|---|
| check_skill_drift / check_doc_drift / rebuild_tool_inventory --check / validate_run_contracts | 全部退出 0 | 四命令实跑 |
| verify_offline --json（项目 venv） | status=ok（compile/skill/doc/tests 四检查全 ok） | 实跑 |
| 全量 pytest | 1752 passed / 1 warning / 0 failed（76s） | 实跑 |
| 三流路由真实模块 §7.4 四用例复放 | 全过（fail-closed 不回落 wz/xcx、只提议 phase_status.app.json、解析 stream=app、stream 缺省 app） | 导入 .agents/skills/app/scripts/phase_status_routing.py 实测 |
| 真实 init 冒烟 | exit 0、stream=app、33 phase 种子 | 临时目录实测（已删） |
| 真实 audit 冒烟（新工作区） | exit 1（未闭合，符合预期）、state=AUTHORIZATION_PENDING、结构化输出、无 traceback | 临时目录实测（已删） |
| B1 内容锚点 | SKILL 锚点 8 处命中；6 references 在场；MASTG-TEST-0001 与 libjiagu 特征表在位 | grep 实测 |
| B7 锚点 | copy_prompt --list 显示 APP；配方P 含"路由到 APP"；CLM workflows.app + 7 个 app_* 域；AGENTS.md 入口表含配方APP 行 | grep/解析实测 |
| 桌面副本同步 | docs/APP_WORKFLOW_CONSTRUCTION_PLAN.md 与 D:\Desktop 副本 sha256 一致（提示词两份提取件随之有效） | sha256 实测 |

遗留待办（不阻塞闭环）：①B8"真实样本演练"待操作者提供无害样本 APK/IPA 后补测（apktool/jadx 真实解包链 + 失败→blocked 实测），销项后更新 W20 行；②B9 共享基座扩批（graph.py/graph_validation.py 纳入 app 允许路径集）为操作者已授权决议，记录在案。

结论：**W15-W21 全部验收通过，APP 流程建设闭环在独立终验下成立。**

