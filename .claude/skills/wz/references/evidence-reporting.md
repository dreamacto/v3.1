# Evidence and reporting

## Candidate validation record

Before validation, record:

- hypothesis and affected security boundary
- target, endpoint, method, parameter, role, and precondition
- expected secure behavior
- minimum validating action and negative control
- stop condition, cleanup plan, and approval requirement

After validation, record confirmed, rejected, blocked, or approval required. A tool match without a
repeatable boundary failure remains a candidate.

## Evidence minimum

For each confirmed finding, preserve:

1. Stable finding ID and title.
2. UTC/local timestamp and target.
3. Account role or anonymous context without credentials.
4. Minimal reproducible steps.
5. Redacted request and response structure or equivalent observation.
6. Negative control or expected behavior comparison.
7. Demonstrated impact using disposable or synthetic data where possible.
8. Cleanup result.
9. SHA-256 hashes and paths for evidence files.

A separate retest phase is not part of the WZ workflow. If a later fix verification is needed, record it
as an external/manual activity without making it a prerequisite for closure.

## Severity

Assign severity from demonstrated impact, exploitability, required access, affected scope, detectability,
and environmental controls. Separate technical severity from business priority when needed. Do not
inflate severity from a product version or theoretical exploit chain that was not validated.

## Report structure

1. Executive summary and overall risk.
2. Authorization, scope, exclusions, timing, and rules.
3. Architecture and attack-surface summary.
4. Methodology, tools, accounts, and coverage.
5. Confirmed findings ordered by business risk.
6. Rejected high-priority candidates and why they were rejected.
7. Untested, blocked, approval-gated, and not-applicable areas.
8. Cleanup and residual risk.
9. Evidence index and technical appendices.

Each finding includes title, severity, affected asset, description, preconditions, evidence, impact,
root cause, remediation, verification guidance, cleanup, and references. Keep raw secrets and sensitive
data out of the report.


## Final report is DOCX (2026-08-23；命令与文案硬规则 2026-09-09)

The client-facing deliverable is generated, not hand-written. Its reader is the vulnerability
reviewer, not the operator — every sentence must be understandable and reproducible by someone who
does not know this project:

1. Reporting phase: curate `reports/findings.json` (one entry per reportable finding — merge related
   ledger rows; `description` ≤100 字、2~3 句；`commands` are complete one-line reproductions, each
   followed by its real captured output as `# 预期:` / `# 实测原始输出:` comments) and
   `reports/meta.json`（只用 `target_name`、`asset_proof_url`、`filing_proof_url`）.
2. Command hard rules: commands run in Windows Git Bash by default and must have been executed
   successfully there before entering the report; raw command + raw output only — never a bare
   reference to a local script/artifact; if a script is required, paste its full source first
   (`# 完整源码全文如下` … `# 源码结束`) and use absolute paths; omit commands that do not affect
   reproduction (environment prep and similar filler is forbidden).
3. No project-internal terminology in any field: `engagements/`、`runs/`、`artifacts/` paths,
   `auth_sessions.local.json`、“本地凭证文件”、“操作员”、审批编号、队列/L 编号、phase 游标. Credential
   placeholders read “替换为测试账号的有效会话值”. The renderer no longer supports `meta.limitations` /
   `meta.env_lines` and emits no 限制与观察 section.
4. Run `python report_docx.py --meta ... --findings ... --out reports/攻防成果报告_<名>_<日期>.docx`
   (skeleton first pass: `--from-ledger <engagement>` fills titles/URLs/levels from confirmed rows).
5. The generator inserts red 【需截图 S-N】 markers automatically — every marker must be replaced
   with a real screenshot (system time visible, sensitive values redacted) before submission.
6. `final-report.md` remains internal working notes only.
