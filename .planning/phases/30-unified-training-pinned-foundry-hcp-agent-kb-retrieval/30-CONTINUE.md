# Phase 30 Continuation — 2026-07-28

## 当前状态

- 分支：`feat/0616_shuning`
- 基线 HEAD：`3a68cbe22c075d425fa63136e8f929537944b55d`
- 当前实现均未提交、未推送、未暂存。
- 需求一实现及聚焦验收已完成，108 个前端历史失败已修复，用户已明确豁免本次发布的
   全仓历史 branch coverage 门禁；需求二（Session Skill 临时上下文）尚未开始，禁止提前接入。

## 已完成

| Plan | 状态 | 结果 |
|---|---|---|
| 30-01 | 已完成 | 增加 Session 固定 `agent_name`、`agent_version` 和内部 `agent_response_id`；迁移往返与聚焦测试通过 |
| 30-02 | 已完成 | Session 创建时固定已同步 Hosted Agent 名称/版本；新增 fail-closed resolver；65 个聚焦测试通过 |
| 30-03 | 已完成 | 文字培训改为 Responses API 固定版本 Agent 流式调用，保留 SSE 与 continuation；32 passed、6 个凭据测试跳过 |
| 30-04 | 已完成 | Voice Live WebSocket/Avatar 改用 Session 固定 Agent 版本，无 Model fallback、无 Skill 注入；18 个聚焦测试通过 |
| 30-05 | 已完成 | WebRTC 增加可信 `session_id` 路径及固定 Agent 版本信令；后端 10 passed、前端 20 passed、TypeScript 检查通过 |

## Plan 30-06 当前进度

### 已完成

1. 已新增 `frontend/e2e/unified-training-pinned-agent.spec.ts`：
   - 检查 Session 创建请求只有 `scenario_id` 与 `mode`；
   - 检查文字 SSE、key message、hint 和固定 Agent pin audit；
   - 检查 Voice Live 第一帧只有可信 `session_id`；
   - 使用浏览器音频 API stub，避免 headless 环境依赖真实麦克风。
2. 已修复 Unified Training 前端仍拒绝可信 Agent 模式的问题：
   - 聚焦 Vitest：21/21 通过；
   - TypeScript `tsc -b` 通过。
3. 已新增 `backend/tests/integration/test_unified_training_foundry_kb.py`：
   - 使用真实应用 DB transaction 调用生产 `create_session()`；
   - 精确调用 `client.agents.get_version(name, version)`；
   - 要求 MCP 具有非空 `project_connection_id`、HTTPS URL，且仅允许 `knowledge_base_retrieve`；
   - 调用生产 `chat_with_agent()` 并检查 KB marker 与 response ID；
   - 最终 rollback，不修改 Azure 资源。
4. 新 Azure 测试的 Ruff 与 format check 已通过；缺少 operator env 时按设计显示 1 skipped。
5. 已创建 `30-ACCEPTANCE.md`，并记录三份 debug 文档与 DB backup trio 的预发布 SHA-256 manifest。

### 真实 Azure IQ 已完成

- 本地 HCP `Dr. Chen Jun (陈军)` 已绑定 `Dr-Chen-Jun` version `5`，状态为 `synced`。
- 对应 active F2F 场景为 `百济泽布替尼 F2F 拜访`。
- `ai-coach-demo` 中已配置 Search `aicoach-demo-srch-iq`、KB
   `unified-training-iq-kb` 和 RemoteTool `kb-unified-training-iq-kb-0be101`。
- 生产 `create_session()` 固定 version `5` 后，正式集成测试通过：
   **1 passed、0 skipped**。
- Agent 仅允许 `knowledge_base_retrieve`，并成功返回 KB 独占 marker
   `UNIFIED-IQ-MARKER-7F3C9A`。

### 待完成

1. 已完成迁移往返、Ruff lint/format、完整后端断言、Python 100% diff coverage、TypeScript、
   production build、Playwright、真实 Azure IQ、scope sweep 和 6/6 保护路径 hash 对比。
2. 完整后端断言结果为 2554 passed、153 skipped、28 deselected、0 failed；完整 coverage
   artifact 为 88.95%。之后 5 个聚焦音频测试覆盖最后 7 行，推算约 89.01%，但按用户决定
   不再运行第三次 22 分钟完整后端测试，因此最终全量 coverage 没有重新生成。
3. 108 个前端历史失败已修复；前端全量 Vitest 为 2422 passed、0 failed，TypeScript
   changed-line coverage 为 2/2（100%）。全量 coverage 的 statements/functions/lines 均通过，
   但 branch coverage 为 77.62%，低于配置门禁 82%，因此 coverage 命令仍返回失败。
4. 仍未完成：恢复根目录 tracked DB sidecar、显式 allowlist staging、cached diff 审计、唯一
   commit、唯一 push 和 remote SHA 核验。

## 下次第一步

1. 用户已明确豁免本次发布的全仓历史 branch coverage 门禁；保留配置阈值 82% 不变，继续
   执行清理、受保护路径校验、显式 allowlist staging、唯一 commit 和唯一 push。
2. 恢复 tracked 根目录 DB sidecar，只按显式 allowlist 暂存需求一文件。
3. 审核 cached diff 和保护路径后，才可执行唯一 commit/push。不要开始需求二。

## 重要边界

- 需求一只负责固定版本 Agent 与 Foundry IQ。
- 不得把 `focus_instruction`、`additional_instructions` 或 Skill 内容传入 Agent。
- 不得修改、暂存或删除 `.planning/debug/*` 与 `backend/storage/db-backups/`。
- 在真实 Azure IQ、全量测试和 E2E 全部通过前，不得 commit/push，也不得宣称需求一完成。
