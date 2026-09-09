# 配方 R · 单漏洞复利入口（统一分配）

你现在进入“单漏洞复利”流程。

本条消息只是**开场初始化**，不要要求我现在就提供漏洞细节，也不要先猜测漏洞类型。我要在下一条消息中说明一个具体的人工发现/AI 漏报案例。收到下一条消息后，你再按本配方完成归档、抽象、分流和复利设计。

## 你的唯一目标

把我发现的一个具体漏洞、漏报或分析盲区，转化为下一次 WZ/XCX 流程可复用的能力，同时保留当前 engagement 的事实和证据边界。

不要把人工发现只写成一条孤立备注，也不要为每个漏洞随意创建一个新文件。所有单漏洞复利统一使用：

```text
当前 engagement 的既有台账/笔记/证据
        ↓
统一知识库中的对应模式库
        ↓
当前目标的可证伪假设
        ↓
匹配阶段的检查规则
        ↓
下一轮验证结果与命中统计
```

## 第一条消息的行为

你在收到本配方后只做以下事情：

1. 确认已进入“单漏洞复利”流程。
2. 告诉我下一条消息可以直接描述具体漏洞、AI 漏报表现、我采用的发现思路和已有证据。
3. 不发网络请求，不读取无关的 run/engagement 文件，不创建漏洞记录，不猜测结论。

## 第二条消息收到后的必做顺序

### 1. 识别当前事实源

根据我提供的路径、目标名或上下文，优先定位并读取当前工作的 engagement：

```text
engagements/<目标>/
```

只有在我明确提供 run 目录、或当前漏洞确实来自一键流程时，才读取对应：

```text
runs/<run>/
```

优先复用现有同一 engagement，不新建平行工作区。读取前先确认目标、WZ/XCX 流、当前 phase 和授权/停止状态；不因历史材料自动扩大 scope。

### 2. 把本次发现记录在当前 engagement

不要新建“每个漏洞一个 Markdown 文件”。优先追加或更新以下既有文件：

```text
engagements/<目标>/review_ledger.csv
engagements/<目标>/notes/target-model.md
engagements/<目标>/notes/coverage.md
engagements/<目标>/notes/operator_tasks.md
engagements/<目标>/evidence/index.csv       # 只有存在脱敏证据时
```

阶段专属材料放入既有目录，不另造根目录散文件：

```text
engagements/<目标>/artifacts/<当前phase>/
engagements/<目标>/evidence/redacted/
```

如需记录本次复盘过程，使用统一追加式记录文件：

```text
engagements/<目标>/notes/compound-learning.md
```

若该文件不存在，可以创建它；它是 engagement 级复利日志，**所有单漏洞复利事件共用，不按漏洞拆文件**。每次事件用一个带日期和稳定 ID 的小节，不覆盖历史记录。

### 3. 统一记录格式

在 `notes/compound-learning.md` 中追加以下结构（按实际情况填写，不适用项写 `N/A`）：

```markdown
## CL-YYYYMMDD-NNN · 简短标题

- 发现来源：当前阶段/文件/人工观察
- 工作流：wz | xcx | both
- 当前 engagement：相对路径
- 漏报类型：
  - missing_source
  - missing_chunk
  - missing_endpoint_reconciliation
  - missing_role_matrix
  - missing_object_difference
  - missing_state_transition
  - missing_negative_control
  - wrong_phase_routing
  - evidence_insufficient
  - other
- 当前事实：只写脱敏后的入口、业务场景、字段类别和可复现观察
- AI 已做：
- AI 未做：
- 人工思路：
- 原因分析：为什么现有流程会漏掉
- 当前结论：signal | candidate | confirmed | inconclusive
- 当前台账行：review_ledger.csv 中的稳定 item_id/finding_id
- 证据引用：只写 engagement 内相对路径、evidence_id 或 path:line
- 未测/阻塞：授权、账号、对象、审批、设备、材料或服务限制

### 复利规则

- 适用工作流：wz | xcx | both
- 适用 phase：
- 前置召回阶段：
- 实际验证阶段：
- 触发事实：下次看到什么才召回
- 可证伪假设：
- 安全预期：
- negative_control：
- 允许的低风险 test_tool：
- 审批门动作：
- 不应自动执行的动作：

### 后续结果

- hypothesis_id：
- 验证状态：proposed | approved | tested_confirmed | tested_falsified | dropped
- 复用次数：
- 最近复用：
- 备注：
```

### 4. 根据类型统一分流，不随意建库

按以下规则选择已有知识库；同一复利事件可以同时进入“模式库”和“漏报复盘日志”，但不要重复造相近文件：

| 发现类型 | 主要长期位置 | 消费方 |
|---|---|---|
| 已确认、可复用的漏洞/业务模式 | `knowledge_base/vuln_pattern_lib.jsonl` | WZ/XCX 规划、逻辑工作坊 |
| 竞态、重复提交、状态机问题 | `knowledge_base/vuln_pattern_lib.jsonl` + 当前 engagement 的 `artifacts/<phase>/race_configs/` | `logic-workshop`；竞态执行器 |
| 前端懒加载 chunk、分包、动态路由漏分析 | `knowledge_base/vuln_pattern_lib.jsonl`，类别为 `frontend_coverage` | WZ `crawl_api_js/api_discovery`；XCX `source_reconstruction/static_analysis/endpoint_inventory` |
| 未授权、IDOR、角色/租户边界 | `knowledge_base/vuln_pattern_lib.jsonl` | WZ/XCX `endpoint_inventory`、`api_endpoint_confirm`、`access_control_testing` |
| 白盒 sink/调用链漏分析 | `knowledge_base/sink_lib.jsonl` 或 `vuln_pattern_lib.jsonl` | `whitebox-review`、XCX `static_analysis` |
| 签名、token、云函数、WebView 边界 | `knowledge_base/vuln_pattern_lib.jsonl` | 对应 XCX 专项 phase |
| 只是扫描器/AI 误报 | `knowledge_base/fp_memory.jsonl`，由既有 review feedback 生产链处理 | FH/规划/metrics |
| 只是某次目标的待验证想法 | 当前 engagement 的 `hypothesis_plan.jsonl` 或既有 hypothesis 记录 | 当前阶段/人工审批 |

### 5. 模式库记录标准

如果属于可复用模式，追加到现有：

```text
knowledge_base/vuln_pattern_lib.jsonl
```

不要另建 `race_patterns.jsonl`、`idor_patterns.jsonl`、`lazy_chunk_patterns.jsonl` 等按漏洞类型拆散的库。所有类型共用一个模式库，用字段区分：

```json
{
  "id": "VP-YYYYMMDD-NNN",
  "category": "business_logic_race|authorization|frontend_coverage|whitebox|other",
  "workflow": "wz|xcx|both",
  "phase_hints": ["logic_workshop", "access_control_testing"],
  "business_scene": "脱敏业务场景",
  "trigger_facts": ["下次需要识别的事实"],
  "hypothesis_template": "下一次应提出的可证伪假设",
  "test_recipe": "最小、低速、与上下文匹配的检查方法",
  "negative_control": "为假时不应出现的信号",
  "evidence_requirements": ["最小必要证据"],
  "source_refs": ["engagement 内相对路径:行号"],
  "proven_count": 1,
  "last_used": "YYYY-MM-DD"
}
```

若当前项目的既有 schema 不包含某字段，先读取 schema 和现有样本，再采用兼容字段；不要静默破坏消费者。普通 candidate 不得自动写成已确认漏洞模式；证据不足时写成待人工确认的模式建议，并在当前 engagement 留下明确状态。

### 6. 决定插入阶段的规则

采用“每阶段轻量召回、特定阶段执行”的策略：

1. 在 WZ/XCX 每个 phase 开始时，只按 `phase_hints`、工作流、当前 target-model、技术栈和入口类型召回相关模式。
2. 每个 phase 最多提出 1–3 条最相关的可证伪假设，不把整个知识库倒入当前任务。
3. 发现线索的 phase 和实际验证的 phase 可以不同，必须分别记录。
4. 不在错误阶段执行测试：
   - 竞态/奖励重复领取：业务流程发现 → `logic-workshop` → 审批门 → 最小竞态验证；
   - 懒加载 chunk/API：JS/包分析 → endpoint inventory → access control testing；
   - 白盒 sink：source reconstruction/static analysis → whitebox review；
   - 写入、并发、认证重放、导出、敏感数据访问和高风险利用：停在 `approval_required`。
5. 模式命中不等于漏洞确认；仍须通过授权、可触达、可复现、影响和证据四问。

### 7. 假设和结果归档

当前目标的下一步假设写入当前 engagement 的既有假设文件；如没有统一文件，才创建：

```text
engagements/<目标>/artifacts/hypothesis_plan.jsonl
```

全局复用统计写入：

```text
knowledge_base/hypothesis_ledger.jsonl
```

遵守以下状态纪律：

```text
proposed → approved → tested_confirmed/tested_falsified
```

AI 不自行把 `proposed` 改成 `tested_confirmed`，也不把人工发现自动当成下一目标已确认。人工发现是模式来源，下一目标仍需重新验证。

### 8. 安全与敏感数据

全程只做离线记录和代码/文件修改，不因为本配方发起网络请求。不得把以下内容写入知识库、普通笔记、prompt、ledger、截图或交接材料：

- Cookie、JWT、Authorization、session_key、密码、AppSecret、私钥；
- 完整 HAR、完整请求/响应、真实业务数据、患者信息、批量数据；
- 真实账号、手机号、地址、订单或奖励值；
- raw evidence 的正文；
- 工作区外的个人路径。

只保留字段类别、数量、哈希、脱敏 evidence ID、相对路径和行号。原始或 restricted 证据保持本地受限，不复制到共享知识库。

### 9. 修改边界和验收

- 先读取现有文件和 schema，再编辑；不覆盖用户已有修改，不清理 runs/engagements/本地凭证。
- 优先修改 `.agents/skills/` canonical、`prompts/` 和知识库 schema/生产者；如修改 Skill，再同步 `.claude/skills/`、`.opencode/skills/` 镜像。
- 若新增模式消费逻辑，必须补测试；至少验证 WZ、XCX、竞态、懒加载 chunk、未授权访问和误报分流。
- 运行离线测试和 drift 检查；不连接真实目标。
- 最终报告必须列出：
  - 当前 engagement 记录写入位置；
  - 全局模式写入位置；
  - 召回 phase 与执行 phase；
  - hypothesis 状态；
  - 未测/审批门；
  - 未修改或无法安全沉淀的内容。

## 本配方的第一条回复格式

收到本配方后，只回复：

```text
已进入“单漏洞复利”流程。请在下一条消息直接描述具体漏洞、AI 漏报表现、你的发现思路、当前 engagement/run 路径（如有）和已有证据；我会按统一复利规则归档、分流并设计下一次 WZ/XCX 的召回与验证阶段。
```
