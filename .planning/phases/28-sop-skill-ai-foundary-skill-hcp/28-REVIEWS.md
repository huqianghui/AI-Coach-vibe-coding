---
phase: 28
reviewers: [claude]
reviewed_at: 2026-07-18T07:57:22Z
plans_reviewed: [28-01-PLAN.md, 28-02-PLAN.md, 28-03-PLAN.md, 28-04-PLAN.md]
---

# Cross-AI Plan Review — Phase 28

> Note: gemini/opencode/coderabbit not installed; codex install broken (missing native binary).
> Per user decision, review performed by a separate `claude -p` session (independent context,
> same model family as the planning session).

## Claude Review

# Phase 28 计划评审（Cross-AI Plan Review）

## 1. Summary

四份计划整体质量很高：严格锚定 doc 10 的实测结论（Entra-ID-only、Foundry-Features 头、ZIP 根目录布局、MCP 405 缺口），对未验证假设（D-03 版本递增）做了显式标注而非默默当作事实，降级链（MCP → download → 本地 DB 注入）设计诚实且对上层透明，E2E 计划（28-04）补上了 CLAUDE.md 最高优先级规则的缺口。依赖顺序（wave 1 → 2 → 2 → 3）正确。但存在两个未被任何计划处理的实质性风险：**`update_sop_progress` 每条用户消息触发完整云端链路（性能回归）**和 **`_sanitize_skill_name` 无唯一性保证导致跨 Skill 云端实体互相覆盖/误删**。这两点建议在执行前修订。

## 2. Strengths

- **实测驱动**：`<interfaces>` 块直接给出 SDK 精确调用形状并要求 executor 逐字使用，杜绝签名猜测——这是对 doc 10 §12 修复过程教训的正确内化
- **假设诚实标注**：D-03 版本递增被明确标为 UNTESTED ASSUMPTION，附带代码注释要求 + 非阻断性人工冒烟测试 + SUMMARY 记录义务，这是罕见的高质量风险处理
- **D-06 语义贯穿**：`sync_skill_to_foundry` never-raise、`mount_skill_toolbox` never-raise、`get_skill_content_for_session` 全链路 try/except 落到本地降级——发布不阻断、培训不中断在每一层都有断言级测试要求
- **MCP 探测而非硬编码跳过**（D-04）：405 是当下现实，但探测式实现让路径在 Azure 修复后自愈，符合 CONTEXT 决策
- **BLOCKER-1 修复干净**：提升 `_parse_skill_md` 为共享 `parse_skill_frontmatter` 而非引入 `python-frontmatter` 新依赖，且有回归守卫（pyproject 不得新增该依赖）
- **WARNING-2 处理正确**：幂等 re-publish 不重触发 sync 的决定有注释、有回归测试（两次 publish 只调一次 sync）、有替代恢复路径（28-03 retry 路由）
- **UI 复用既有模式**：SkillFoundryStatusSection 结构镜像 AgentStatusSection，28-04 要求先读组件确认真实 label/selector 再写断言，避免了 E2E 与实现漂移
- **威胁建模务实**：Entra-only 无 API-key 分支（含 grep 级验收标准 `AzureKeyCredential` 零匹配）、错误信息截断 2000 字符、admin-gated 路由复用既有依赖

## 3. Concerns

- **[HIGH] 28-02 Task 2：`update_sop_progress` 每条消息触发云端链路。** Phase 24 中 `update_sop_progress` 在每条用户消息后调用。替换为 `get_skill_content_for_session` 后，每条消息 = Toolbox `create_version`（网络）+ MCP 探测（必 405，网络）+ 完整 ZIP `skills.download()`（网络）。原来是一次本地 DB 查询，现在是三次串行 Azure 调用（各 30s 超时上限）。对话延迟和 Foundry API 配额都会受冲击。计划无任何缓存/记忆化设计。
- **[HIGH] 28-01：`_sanitize_skill_name` 无唯一性保证。** 两个本地 Skill（如 "My Skill!" 和 "My Skill?"）会 sanitize 成同一个 `my-skill`，导致：(a) 两者在 Foundry 侧共享/互相覆盖同一云端实体的版本；(b) 归档/删除其中一个会 `delete` 掉另一个仍在使用的云端 skill。计划未引入 skill id 后缀或冲突检测。
- **[MEDIUM] 28-02：Toolbox 版本无限增殖且永不清理。** 每次 session 创建都对同名 toolbox 调 `create_version` → Foundry 侧版本数随 session 数线性增长；D-03 只删 skill 不删 toolbox，废弃资源残留恰是 D-03 想避免的。且今天没有任何消费方真正使用这个 toolbox（MCP 405，Test 8 走的是 download 路径）——mount 是纯成本。
- **[MEDIUM] 28-02：云端路径丢失版本 pin 语义。** `load_skill_for_scenario`（本地路径）会解析 scenario pin 的 SkillVersion；`skills.download()` 永远取云端最新版。若 scenario pin 了旧版本，synced skill 的培训内容与 pin 不一致，且两条路径返回内容可能不同（降级时内容突变）。
- **[MEDIUM] 28-01/28-03：archive 删除 vs retry-sync 允许 archived 自相矛盾。** D-03 规定归档即从 Foundry 删除，但 28-03 的 retry 路由允许对 `archived` skill 重新 sync，会复活刚被 archive hook 删除的云端实体。retry 应限 `published`。同理 `restore_skill` 不重新 sync，恢复后的 published skill 云端状态为 "none"，只能靠管理员手动 retry——可接受但应在 SUMMARY/UI 提示。
- **[MEDIUM] 28-01 Task 2 步骤 3：`credential.get_token(...)` 是同步阻塞调用**，直接在 async 函数里执行会阻塞事件循环（首次可能触发交互式/IMDS 探测，秒级）。且 `DefaultAzureCredential()` 每次调用新建，无缓存。
- **[MEDIUM] publish/retry 请求内联执行云端 sync。** `publish_skill()` HTTP 请求要等 ZIP 导出 + Entra token + 上传完成才返回（虽然失败不阻断，但延迟阻断）。管理员发布大 skill 时可能撞前端 30s axios 超时。
- **[LOW-MEDIUM] i18n 缺失。** SkillFoundryStatusSection 的 label（"Foundry Synced" 等）与 toast 文案按计划是硬编码英文（镜像了同样有此债务的 AgentStatusSection），但项目既有 phase 的 success criteria 和用户反馈均要求 en-US + zh-CN 双语外部化。四份计划均未列 i18n key 任务。
- **[LOW] 28-02 `_try_mcp_fetch` 访问 `client._config.credential` / `toolboxes_op._config` 私有属性**——SDK 小版本升级即碎。已是权宜之计，建议加防御性 getattr（计划已部分做到）。
- **[LOW] 28-04 test 2 的 `page.route(**/api/v1/skills/${skillId})` GET mock** 需要返回完整 Skill 形状，fixture 若漏字段会导致页面其它区域渲染异常，测试脆弱性偏高；计划已提示但未给完整 fixture。

## 4. Suggestions

1. **（对应 HIGH-1）在 28-02 增加缓存层**：`get_skill_content_for_session` 结果按 `(skill_id, foundry_cloud_version)` 做进程内 TTL 缓存，或更简单——`update_sop_progress` 直接复用 session 创建时已快照的 `focus_instruction`/SOP steps（Phase 24 本就持久化了快照 D-03），仅 `create_session` 走云端链路。
2. **（对应 HIGH-2）Foundry 命名加唯一后缀**：`_sanitize_skill_name(f"{skill.name}-{skill.id[:8]}")`（截断后仍 ≤64、无 `--`），并在首次 sync 后固化到 `foundry_skill_name`（计划已固化，只需改首次生成规则）。
3. **（对应 Toolbox 增殖）mount 前先 `get_version`/list 判重**，同一 skill 版本已有 toolbox version 则跳过 create；或将 mount 移到 sync 时机（skill 级一次）而非 session 级。既然今天无消费方，也可考虑把 mount 降级为 feature-flag off 的 stub，等 MCP 打通再启用——但这偏离 D-02 决策，需 owner 确认。
4. **retry-sync 状态守卫改为仅 `published`**，与 archive-即-删除的 D-03 语义对齐；`restore_skill` 后在 UI 状态区提示 "restored skill needs manual Foundry re-sync"。
5. **token 探测与 `DefaultAzureCredential` 构造包进 `asyncio.to_thread`**，并模块级缓存 credential 实例。
6. **给 `create_from_files`/`download` 加显式超时或整体 `asyncio.wait_for` 上限**（如 60s），避免 publish 请求被 SDK 默认重试拖死。
7. **补 i18n 任务**：四个状态 label + retry/portal 按钮 + toast 文案入 en-US/zh-CN locale（顺手可修 AgentStatusSection 同类债务，或明确记为已知债务不扩散）。
8. 28-02 云端路径考虑尊重 pin：若 scenario pin 了非最新版本，直接走本地路径（跳过云端），保证内容确定性。

## 5. Risk Assessment

**MEDIUM**

计划对已知未知（D-03 版本递增、MCP 缺口、Voice Live 挂载）的处理是模范级的，降级链保证了"最坏情况 = 现状（Phase 19 本地注入）"，所以功能性风险低。风险集中在两处计划**没有意识到**的问题：`update_sop_progress` 的每消息云端链路是明确的性能回归（会直接影响培训对话体感延迟），sanitized name 冲突是低概率但后果严重（跨 skill 云端实体误删）的正确性缺陷。两者修复成本都很小（缓存/复用快照 + id 后缀），建议作为计划修订在执行 wave 2 前落实；28-01 可先行执行但 Task 2 的命名规则应先改。

---

## Consensus Summary

Single reviewer — no cross-reviewer consensus possible. Treat HIGH concerns as priority items.

### Key Strengths
- Plans are grounded in measured SDK behavior (doc 10): Entra-ID-only, Foundry-Features header, ZIP layout, MCP 405 gap
- Untested assumptions (D-03 version increment) explicitly labeled with smoke-test + SUMMARY obligations
- Non-blocking degradation chain (MCP → download → local DB) asserted at every layer (D-06)
- E2E plan (28-04) closes the CLAUDE.md testing-rule gap; wave ordering is correct

### Priority Concerns (HIGH)
1. **28-02**: `update_sop_progress` fires the full cloud chain (toolbox create_version + MCP probe + ZIP download, 3 serial Azure calls) on EVERY user message — performance regression vs. the previous single local DB query. No caching/memoization in plan. Fix: reuse the session-creation snapshot or add TTL cache keyed on `(skill_id, foundry_cloud_version)`.
2. **28-01**: `_sanitize_skill_name` has no uniqueness guarantee — distinct local skills can collide on the same Foundry name, causing cross-skill overwrite and wrong-entity deletion on archive. Fix: suffix with `skill.id[:8]` before first sync.

### Secondary Concerns (MEDIUM)
- Unbounded toolbox version growth per session; no cleanup and no real consumer today (MCP 405)
- Cloud path ignores scenario version pins (`skills.download()` always fetches latest)
- retry-sync allowing `archived` skills contradicts D-03 archive-deletes semantics; restrict to `published`
- Sync `credential.get_token()` blocks the event loop; wrap in `asyncio.to_thread` and cache the credential
- Publish/retry run cloud sync inline in the HTTP request — may hit frontend 30s axios timeout
- Missing i18n keys for SkillFoundryStatusSection labels/toasts (en-US + zh-CN required)

### Overall Risk
MEDIUM — functional risk is low (worst case degrades to Phase 19 local injection), but the two HIGH items are cheap to fix and should be incorporated before executing wave 2; 28-01 naming rule should change before its Task 2 runs.
