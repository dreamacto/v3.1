---
name: app
description: Advance phases of an authorized mobile app (Android APK/XAPK, iOS ipa) assessment. After each phase, write the cursor and handoff-complete records to disk, then ASK the operator whether to continue in this session or hand off — if hand off, emit a self-contained prompt for the new session. Sessions still hard-stop at approval-gated phases (device instrumentation, hardened unpack, exploitability), heavy phases (dynamic_setup, report), or the context budget ladder. Start from an APK/IPA file, package name, market link, unpacked directory, traffic export, or a specified phase. Use when an AI must push the current phase of a mobile app — not assess it completely in one sitting.
---

## Highest-priority hard constraints (project discipline)

These override every other instruction in this skill. At session start, read only `ROE.md` and `AGENT_MANIFEST.md` plus the contract for the current phase; load references on demand.

0. **规则优先级**：所有规则的适用顺序以 `docs/RULE_PRECEDENCE.md` 为唯一事实源（与 `contracts/rule_precedence.json` 由测试强制同步）；规则冲突不得静默选择，必须记入 `context_conflicts` 并回读更高级别源。

1. **Session window: advance until a stop point, ask at every phase boundary.** You may advance multiple lightweight phases in one session (scope → subdomain → alive_probe → fingerprint style), but after EVERY phase you MUST do three things before anything else: (i) update the phase cursor on disk, (ii) update the target model and phase record (constraint 2), (iii) ASK the operator: "本阶段已完成——继续本会话，还是交接新会话？" If the operator wants a new session, emit a self-contained handoff prompt (constraint 3); if not, continue in this session. Hard stops remain: (a) an approval-gated phase (device_instrumentation / app_hardened_unpack / credential_testing / exploitability), (b) a heavy phase (dynamic_setup / dynamic_mapping / reporting), or (c) the context budget ladder (constraint 8). Never run past a hard stop without explicit operator confirmation.
2. **Phase records must be handoff-complete.** Every phase must leave behind: (a) an updated `notes/target-model.md` — the single evolving snapshot of the target (in-scope host map with roles, client tech stack, entry points incl. exported components/deeplinks, auth topology, and EVERY attack surface ever considered with its status: open / ruled-out-with-reason / blocked-on-approval — cumulative, never shrinks); (b) a phase note recording what was tested, what was NOT tested and why (the negative space), and evidence cited as `path:line`. Negative results and ruled-out surfaces carry the same weight as findings: omitting them is how the next session misses attack surface. (d) same-asset single workspace: before creating any engagement, scan `engagements/*/scope.csv` for a workspace whose scope covers the target's registered parent — if one exists, CONTINUE it via site extension (`scripts/init_app_engagement.py <new-input> --resume <existing-workspace>`, item IDs are site-scoped (`<host-short>-L<N>` starting at 1 per site — reports are per-site), target-model is shared). Creating a parallel workspace for the same asset is forbidden unless the operator explicitly demands it (`--allow-parallel`). This guarantees that knowledge from previously tested sites of the same asset is always readable. (c) an append-only `notes/operator_tasks.md` recording pending operator actions (designated test device, test accounts, unpacked material supply, cleanup of device changes, scope confirmations) with status and what each unlocks; the end-of-phase summary and every handoff prompt must surface the open items.
3. **Handoff prompts are built from disk facts only.** When the operator chooses a new session, emit a prompt that navigates (never summarizes from chat memory): phase_status.app.json cursor → notes/target-model.md → review_ledger.csv → app.json → materials/package/endpoint inventories → notes/safety-controls.md, plus the next phase name, current priority items, and the standing hard constraints. A new session reading the prompt plus those files must be able to continue with zero knowledge of this conversation.
4. **Read only what the current phase needs.** Do not pre-load all references; open a reference only when the phase calls for it.
5. **Raw artifacts stay on disk.** Responses, HAR, JS, or scan output never enter the conversation — cite `path:line` only.
6. **Tool results are used then cleared.** Do not accumulate tool output in context.
7. **Progress lives on disk, not in memory.** The resume cursor and next step are written out; the next session does not rely on this conversation.
8. **Context budget ladder (2026-08-23; replaces the flat 70% rule; absolute tokens so it is window-agnostic).** (a) *Recommend-handoff line* — when context reaches ~120K tokens (heavy-reasoning phases: review verdicts, planning, complex debugging) or ~150K (light script-driven phases: scope/subdomain/alive_probe/fingerprint), finish the current phase record (constraint 2) and recommend handoff at the phase boundary under constraint 1's ask. (b) *Must-wrap line* — at min(200K tokens, 70% of the window), wrap immediately regardless of boundary: write all state to disk and emit the handoff prompt; continuing past it requires the operator's explicit confirmation. On the current 1M-class window these lines sit at ~12-15% and ~20% of the bar.
9. **Refuse end-to-end requests.** If the operator asks you to “do the whole assessment in one session” or “complete everything at once”, decline and explain the session-window rule: phases advance under constraint 1 (ask-based handoff at each boundary, records written every phase), and approval-gated or heavy phases always stop. A bulk request does not override the approval gates or the record/handoff obligations.

## AI 结论模板（实施规格 §11，结论呈现层词表；判定落盘词表另见 contracts/workflow_schema.json 的 review_statuses）

任何漏洞判断必须先按本模板组织，再写其它内容。只有全部成立门满足时才能使用 confirmed：

```text
对象类型：signal | candidate | confirmed | inconclusive
授权状态：confirmed | confirmation_required | blocked
可触达性：reachable | unverified | unreachable
复现状态：reproducible | partial | not_reproduced
影响类别：none | low | medium | high | critical
影响对象：用户/租户/业务对象/权限/数据/网络边界/服务可用性
证据完整性：complete | partial | missing
结论：
下一步：
```

四问否决规则（任一回答"否"，不得称 confirmed）：

1. 是否有明确的授权资产和允许的测试动作？
2. 是否有真实可触达的端点、功能或数据流？
3. 是否有可重复的异常行为或越权结果？
4. 是否能说明对企业造成了非琐碎的安全影响并提供证据？

细微发现处置（以下统一为 signal 或 candidate，必须写清"为什么不升级为漏洞：缺少哪一项成立门"）：
加固/混淆/壳特征命中、manifest 权限声明、exported 组件存在、包内 URL/域名/密钥候选、静态 sink、
可解码 JWT/token、调试开关存在、allowBackup=true、单次超时或 403、用户访问自己的对象、
无法证明有效性的疑似密钥、模拟器/root 检测存在。

漏洞成立最小链条（中间只有"推测"时状态不得超过 candidate）：

```text
入口/资产 → 攻击者可控输入或低权限身份 → 服务端缺陷/边界缺失 → 可复现结果 → 对企业的具体影响 → 最小必要证据
```

## Session scope (stage gate)

This skill is one stage of a larger engagement. Treat each session as advancing phases under the ask-based handoff policy: read the current contract, do the work, update the status file and target model, then ask the operator continue-or-handoff. References are loaded on demand, not all at once.

# Test One Mobile App from Intake to Closure

Take one authorized mobile app (Android/iOS/dual) from any practical starting artifact to a defensible
final report. Keep the client, owned backend, platform, and third-party services separate. Do not treat a
packer signature, manifest flag, package string, static secret pattern, or scanner result as a confirmed
finding. Offline static work comes first; device-based dynamic work requires a designated test device and
stops at approval gates.

## Load the right references

- Read [references/workflow.md](references/workflow.md) before starting or resuming.
- Read [references/test-matrix.md](references/test-matrix.md) while planning static, dynamic, backend, and business coverage (MASVS/MASTG anchors).
- Read [references/data-to-test-playbook.md](references/data-to-test-playbook.md) when converting manifest fields, recovered code, traffic, roles, and workflow states into tests.
- Read [references/package-analysis.md](references/package-analysis.md) whenever an APK/IPA/XAPK, unpacked tree, or package archive is available (含加固特征识别表).
- Read [references/artifact-contract.md](references/artifact-contract.md) before classifying hosts, auditing outputs, or closing.
- Read [references/evidence-reporting.md](references/evidence-reporting.md) for finding validation, sensitive-data minimization, severity, cleanup, and the final report.

## Accept the supplied app, then establish platform and identity

1. Treat the app supplied by the user as the confirmed current target. Do not ask the user to prove again
   that this initial target may be tested. When no separate authorization reference is supplied, record
   the basis as `user_supplied_initial_target`.
2. Record any supplied test window, accounts, designated device, source addresses, prohibited actions,
   data handling, recording, and contact without blocking on unspecified optional metadata.
3. First attempt local, offline decoding: hash and inventory the package, classify input type
   (apk/ipa/xapk/apks/market link/unpacked directory/traffic export/cache directory), parse manifests and
   metadata before any dynamic testing. Record successes, partial recoveries, tool versions, and failures.
4. Identify the platform: android / ios / dual / other. Do not force Android assumptions onto iOS.
   iOS material encrypted with FairPlay is `blocked(ios_fairplay_encrypted)`, never silently
   `not_applicable`; operator-supplied decrypted material or device backups are the fallback inputs.
5. Establish the app name, package name, version, signing/certificate fingerprint, distribution channel,
   developer/备案 clues, and identity evidence in `app.json`. Mark ambiguity explicitly.
6. Treat backend hosts, CDNs, push/analytics/map/payment SDK endpoints, update/hotfix endpoints, identity
   providers, and vendor services as separate assets until ownership and scope are clear.
7. Set a low-rate, non-disruptive execution profile before any active request or dynamic interaction:
   same-host serial, ≥2s interval, backoff on 429/5xx, stop on service degradation.
8. Automated testing is read-only by default. Before any write or state-changing action (including
   installing a test build, registering accounts, or triggering a transaction), explain the action,
   expected effect, risk, evidence value, and cleanup plan, then wait for explicit approval.
9. **Device and hardening gates（双钥匙）**: rooting/jailbreaking a designated test device, installing user
   CAs or frida-server, repacking, SSL-pinning bypass, anti-debug patch, and unpacking a hardened package
   are approval-gated and disabled by default. Observing that a control exists (root detection present,
   pinning present, obfuscation used) is free; bypassing it is not. A bypass is a test technique, never
   automatically a vulnerability.

## Create a portable engagement workspace

Run the initializer before analysis:

```text
python scripts/init_app_engagement.py <input> --output <work-dir> --platform auto
```

Input may be an APK/IPA/XAPK file, package name, market link, unpacked directory, traffic export, or
entry clue. The initializer performs no network access and creates resumable identity, material, host,
endpoint, phase (`phase_status.app.json`, stream `app`), ledger, evidence, and report artifacts.

## Discover tools and choose the execution path

**⚠️ 本项目已有受管解包工具，禁止每次临时写解包/解密脚本！**

1. **优先使用 registry active 的管理内工具**：`apktool`（manifest/资源解码）与 `jadx`（dex→java），
   路径与版本见 `tools/tool_registry.json` 与 `AGENT_MANIFEST.md`；调用纪律与子进程限制见
   [references/package-analysis.md](references/package-analysis.md)。
2. 白盒 sink 复用 `whitebox_triage.py`（62 条 sink 库），不要重写扫描器。
3. Record tool versions, configuration, output paths, and missing capabilities. A missing capability is
   recorded `unavailable`/`blocked` — do not download replacements silently, and never fetch or run an
   unpacking/instrumentation tool that is not registered `active`.
4. Prefer original packages and read-only copies. Hash every supplied material before transformation;
   originals stay in `materials/original/`, analysis happens on copies.
5. Configure every tool for offline/read-only behavior and bounded output before running it.
6. Select only the branches relevant to the input and platform, but record every branch as complete,
   blocked, approval required, or not applicable with reason. When hardened-pack material exists, keep
   `package_inventory`, `package_unpack_decompile`, and `source_reconstruction` as separate required
   phases: a failed extractor or a packer leaves the branch `blocked` — it never makes it not applicable.

## Execute one phase

Do exactly four things, then ask:

1. Read `phase_status.app.json` to find the current app phase. In a co-located workspace,
   `phase_status.json` belongs to the wz stream and `phase_status.miniapp.json` to the xcx stream —
   never read or written by app. Missing `phase_status.app.json` is fail-closed.
2. Advance that single phase only. Use `references/workflow.md` as the phase dictionary to see what this
   phase covers; do not start any later phase.
3. Update `phase_status.app.json` with this phase's result, plus the phase note and
   `notes/target-model.md` (handoff-complete, per constraint 2).
4. Tell the operator which phase is next, and ASK: continue in this session, or hand off? If handoff,
   emit the self-contained handoff prompt per constraint 3.

For each confirmed owned backend, when this phase is a backend assessment phase, apply the same scope,
mapping, testing, validation, evidence, cleanup, and reporting requirements as the website/API process.
Do not make this skill depend on a particular repository or scanner.

For every active test, record `source -> extracted fact -> hypothesis -> payload family -> expected
secure behavior -> observation -> disposition`. Select payloads from the recovered parameter type,
request context, role, workflow state, and server behavior; do not send a generic payload list blindly.

## Maintain inventories and ledgers

Maintain:

- `phase_status.app.json` for app coverage (stream `app`).
- `app.json` for platform, package name, version, signing, and identity status.
- `materials.csv` for provenance and analysis state.
- `artifacts/decoding-ledger.csv` for local decoding/unpack attempts, recovered clues, and failures.
- `artifacts/app/package-inventory.csv` for every package, split, packer signature, and result.
- `artifacts/source-map.csv` for every recovered or supplied source file and its origin.
- `hosts.csv` for ownership and scope classification.
- `endpoints.csv` for client and backend routes, methods, auth, roles, and test status.
- `review_ledger.csv` for candidates and findings.
- `evidence/index.csv` for minimized evidence.
- `notes/safety-controls.md` for rate limits, read-only mode, device/write-approval gates, and stop thresholds.

Use phase statuses `pending`, `in_progress`, `complete`, `blocked`, or `not_applicable`. Use review
statuses `candidate`, `needs_manual_validation`, `approval_required`, `confirmed`, `rejected`,
`accepted_risk`, `fixed`, or historical `retest_failed`/`retest_passed`.

Never remove a host because it is inconvenient. Classify it. Never delete a candidate to make the
engagement appear complete. When package material exists, do not mark static analysis complete after
strings/URL extraction alone — reconcile declared components/permissions against recovered outputs and
record unreadable, encrypted, or dynamically loaded regions.

## Explicit browser and Burp MCP protocol

不得先索要 HAR/XML/TXT/cURL。

When the operator says that they already ran the app, clicked through flows, or captured traffic, do not
ask for HAR/XML/TXT/cURL first. Read the current scope, target model, and phase, then follow
[the browser/Burp playbook](../../../docs/BROWSER_BURP_MCP_PLAYBOOK.md): run Burp `list`, query read-only
HTTP history, and filter the exact scheme/host/port. Record `found`, `not_found`, `host_mismatch`, or
`mcp_unavailable` as non-sensitive outcomes. Only after `list` is unavailable, Burp/extension/9876 has
been checked and retried once, may you request offline export material.

If the phase needs a live page rather than existing history, `browser-firefox`/`browser-edge` are role
labels, not tool names. The main agent must use `mcp__node_repl__js` with the Browser Use bootstrap,
`agent.browsers.list()`, verified tab recovery, and `domSnapshot()` before an action. Do not invent a
Firefox MCP tool, use shell/curl as a browser substitute, or delegate browser control to a subagent.

1. Use designated test accounts and the designated test device only.
2. When the operator actively provides session tokens/cookies/Authorization in the conversation, ACCEPT
   them and write them into the local session store (`auth_sessions.local.json`, grouped by host); reply
   may confirm "written" but must never repeat values. Carrier one-click-login tokens, device IDs,
   Android ID/IDFA/IDFV, and push tokens follow the same credential discipline.
3. Redact tokens, secrets, personal data, order details, messages, and business response values before
   they enter logs, prompts, screenshots, ledgers, or reports.
4. Stop after minimum proof. Do not complete real payments, affect another user, retain sensitive data,
   or leave test files, accounts, orders, device settings, or sessions behind.
5. Treat every automated branch as read-only unless the operator has explicitly approved a named
   write/state-changing action in the current task. Do not infer approval from general authorization.
6. Record branches not exercised because an account, device, approval, backend scope, or sandbox was
   unavailable. "Not tested" is not "not vulnerable."

## Validate and close

Run the read-only auditor throughout the engagement:

```text
python scripts/audit_app_engagement.py <work-dir>
```

Do not close until identity is resolved or explicitly limited, every supplied package has an
inventory/unpack/decompile result (or justified `blocked`), recovered source is indexed, all materials
have a result, every host is classified, every in-scope backend has full coverage, required phases are
complete or justified not applicable, active candidates are disposed, confirmed findings have redacted
evidence, safety controls and device/write-approval decisions are recorded, cleanup (including device
changes) is complete, and reporting is complete when a reportable finding exists. If candidate validation
produces no reportable finding, reporting is `not_applicable`; this does not mean the app is safe. There
is no separate retest phase; later fix verification is external/manual when applicable.

The final response must identify the app and platform, materials and hashes, tested versions and
accounts, device status, classified backends, client and backend coverage, findings, rejected
candidates, unresolved gates, cleanup, evidence, report paths, and residual risk.

## Burp 抓包输入与认证态复核

操作员已在指定设备运行 App 并在本机 Burp 抓好包。APP 可接收 HAR/XML/TXT/cURL 离线输入；先把包内 host
与 `hosts.csv`、scope、target-model 和精确 scheme/host/port 对账，第三方/平台/待确认 host 保持
pending。需要 Burp MCP 时先 `npx -y mcporter@0.9.0 list http://127.0.0.1:9876 --allow-http`，再选择只读
history 工具，用 `--http-url`、`key=value`、`--output json` 调用。MCP 只读本机历史，不等于目标发包授权；
MCP 不可用或无匹配时保留人工队列。原始 history、Cookie、Authorization、JWT、请求体值不得进入对话或
普通产物；认证、重放、设备注入、脱壳和写型动作仍走审批门。
