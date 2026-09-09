# 移动 App engagement artifact contract

## Required root artifacts

既有 engagement、身份（`app.json`）、素材清单、包清单、hosts/endpoints、阶段游标（`phase_status.app.json`，
stream `app`）、review ledger 和 evidence index 等内部产物继续按本契约保存；原始包（APK/IPA/XAPK）、原始
流量、凭证和 PII 只能留在受限本地目录（`materials/original/` 等），报告安全件放在 `evidence/redacted/`。

工作区布局（init 产物，全部本地 git 忽略）：

```text
engagements/<目标名-日期>/
├── engagement.json            # 授权/安全控制/初始化零网络声明
├── app.json                   # platform/name/package_name/version/signing/operator/identity_status
├── phase_status.app.json      # APP 游标（stream=app，33 phase + substatuses）
├── scope.csv / hosts.csv / endpoints.csv / materials.csv / review_ledger.csv
├── materials/original|working/
├── artifacts/
│   ├── decoding-ledger.csv / app/package-inventory.csv / source-map.csv
│   ├── app/apktool/<pkg>/ 与 app/unpacked/<pkg>/      # apktool/jadx 输出（本地受限）
│   ├── app/package/hardening-review.json
│   ├── app/auth/platform-login-review.json 等 3 件
│   ├── app/reconciliation/static-dynamic-endpoints.csv
│   ├── app/storage|crypto|webview|ipc|cloud/…（各 review 产物/清单 CSV）
├── evidence/raw|redacted/ + evidence/index.csv
├── notes/target-model.md / operator_tasks.md / safety-controls.md / phase-history/
├── logs/  sessions/
└── reports/攻防成果报告_<engagement>_<日期>.docx + final-report.md（工作稿）
```

`reports/攻防成果报告_<engagement>_<日期>.docx` 是主交付物，由 `report_docx.py` 依据模板生成；
`reports/final-report.md` 仅为内部工作稿。

## Report contract

报告必须遵循用户 DOCX 模板的固定结构：资产归属证明网址、备案系统证明网址（模板保留时）、目标信息/基本情况表、成果说明、详细复现命令或操作步骤、返回结果/结果解读、存在问题、整改建议。

生成器不得动态生成长标题、团队/日期头部、综述/执行摘要/渗透路径/阶段总结、独立证据截图章节、红色截图语句或证据文件列表。截图由人工插入，生成器只写正常的结果位置。

canonical finding 至少保留 `finding_id`、`title`、`description`、`system`、目标 URL、漏洞类别、风险等级、数据量/影响范围、权限、`commands`、`steps`、`note`、`interpretation`、预期/实际结果、`pagination` 和 `cleanup`。完整命令和步骤按原始顺序保留；边界说明归入备注，不能冒充命令；无真实命令时明确显示“【请补充实际复现命令】”。命令须在 Windows Git Bash 实跑成功后方可写入并附实测原始输出；复现依赖脚本时先完整粘贴脚本全文并用绝对路径；文案面向漏洞审核员，禁止项目/本地内部术语；不设“限制与观察”章节（详见 evidence-reporting.md 硬规则）。

同一规范化资产 + 同一漏洞类别只生成一个成果并合并多个入口；不同资产、不同类别、candidate/安全观察/未测试项必须分开且不得升级为 confirmed。问题和整改建议各最多 2 条；数据量字段遵循有明确条数才显示、否则回退影响范围、两者都无则省略。

App 报告按 client（客户端本地：存储/密码学/组件/WebView/加固观察）/ backend（自有后端）/ platform（平台
与系统面）/ third-party（第三方 SDK 与服务）分节组织；平台共享资产与第三方端点不得误报为自有资产成果。

## Sensitive storage and closure

凭证、会话、密钥、原始 PII 和未脱敏响应不得进入 DOCX、日志、台账或交接文本。凭证纪律扩展到运营商一键
登录 token、device-id、Android ID/IDFA/IDFV 与推送 token。交付前由报告人员自行插入脱敏截图并人工审计；
cleanup（含设备改动恢复）必须完成。若 candidate validation 没有可报告成果，reporting 标记为
`not_applicable`，否则才要求闭合 reporting 并生成报告。流程不再包含独立 retest phase；后续修复复测仅作为
外部/人工活动记录。
