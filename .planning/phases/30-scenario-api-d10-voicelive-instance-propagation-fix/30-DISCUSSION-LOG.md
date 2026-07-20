# Phase 30: Scenario API D-10 VoiceLiveInstance Propagation Fix - Discussion Log

**Date:** 2026-07-20
**Areas discussed:** 4 of 4 identified gray areas (user selected all)

---

## Area 1: HcpProfileSummary 目标形状

**Q1: 后端 HcpProfileSummary flat 字段如何处理？**
- Options: 全删，只留嵌套 VL 对象（推荐）/ 保留派生 voice_live_enabled
- User clarifying question: "nested 是什么意思？对应绑定的就是 voice live instance 吗？"
  - Clarified: nested = HCP 绑定的 Voice Live Instance 作为子对象嵌套在响应内返回（对比 flat 硬编码默认值），并给出前后 JSON 示例
- **Selected:** 全删，只留嵌套 VL 对象 → D-01

**Q2: scenario.py 中的 VL summary 字段用哪个 schema？**
- Options: 复用 VoiceLiveInstanceSummary（推荐）/ scenario.py 本地定义精简版
- **Selected:** 复用 `backend/app/schemas/voice_live_instance.py` 的 `VoiceLiveInstanceSummary`（import，单一来源）→ D-02

**Q3: 前端 Scenario.hcp_profile 类型怎么处理？（现为完整 HcpProfile，与后端 summary 不符）**
- Options: 新建 HcpProfileSummary 类型（推荐）/ 保持 HcpProfile 不动
- **Selected:** 前端新建 `HcpProfileSummary` 类型与后端响应一致，`Scenario.hcp_profile` 改用它 → D-04（附带 D-05 删除 hcp.ts 游离 `avatar_enabled`）

## Area 2: avatar 门控语义

**Q: 数字人模式可用性判断 avatar 开关读哪里？**
- Options: 读 VL 实例 avatar_enabled（推荐）/ 只看 features 全局开关
- **Selected:** 读 VL 实例 `avatar_enabled` — 数字人 = `features.avatar_enabled && vl.enabled && vl.avatar_enabled`；语音保持 `features.voice_live_enabled && vl.enabled` → D-06

## Area 3: 回归验证范围

**Q1: summary 是否补 avatar_url / personality_type？**
- User clarifying question: "为什么不返回？是没有还是没返回？如果是有，没有返回的话，就是错误哦"
  - Verified: 两者都是真实模型列（hcp_profile.py:20-21），完整 HCP API 有返回，仅 scenario summary schema 遗漏 → 确认为 bug（scenario 卡片头像退化为首字母、性格徽章不显示）
- **Selected（用户裁定）:** 补齐两字段 → D-03

**Q2: 重验范围？**
- Options: 6 个全部重验（推荐）/ 只验 roadmap 点名的 3 个页面
- **Selected:** 6 个 scenario `hcp_profile` 消费者全部重验（3 页面 + scenario-table / scenario-card / scenario-panel）→ D-07

## Area 4: 测试覆盖策略

**Q1: E2E 策略？**
- Options: 门控恢复为主 + 真实 spec 回归（推荐）/ 仅重跑现有 spec
- **Selected:** 新增门控恢复 E2E 故事 + 实际重跑 `voice-avatar-real.spec.ts` → D-09

**Q2: 单元测试范围？**
- Options: 后端序列化 + 前端门控函数（推荐）/ 仅后端
- **Selected:** 后端序列化（含 null-VL 分支）+ 前端 `getScenarioModes`/`getConferenceModes` 门控矩阵 + 组件渲染测试，95% 覆盖率 → D-08

---

## Outcome

- 9 项决策（D-01 ~ D-09）写入 `30-CONTEXT.md`
- Deferred ideas: 无
