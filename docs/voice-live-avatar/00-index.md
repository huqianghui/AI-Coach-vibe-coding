# Voice Live + Avatar 实现文档套件

> 本文档套件完整描述了 Azure Voice Live API + Digital Human Avatar 的全栈实现。
> 设计为 **分层加载** 格式，Coding Agent 可按需加载特定模块，避免 context 溢出。

---

## 文档目录

| # | 文档 | 内容 | 适用场景 |
|---|------|------|----------|
| 01 | [架构总览](01-architecture.md) | 系统架构、数据流、双路径架构、技术选型 | 理解全局，新功能规划 |
| 02 | [数据库设计](02-database-schema.md) | ORM 模型、字段定义、迁移策略 | 后端开发、Schema 变更 |
| 03 | [API 接口设计](03-api-design.md) | REST + WebSocket 端点、请求/响应格式 | 前后端联调、新接口开发 |
| 04 | [后端 WebSocket 代理](04-backend-websocket.md) | Azure SDK 集成、消息转发、Avatar 配置 | 后端核心逻辑修改 |
| 05 | [前端组件架构](05-frontend-components.md) | React 组件树、Hook 设计、状态管理 | 前端 UI 开发 |
| 06 | [WebRTC Avatar 集成](06-webrtc-avatar.md) | ICE/SDP 协商、音视频流处理 | Avatar 功能开发与调试 |
| 07 | [UI 交互设计](07-ui-patterns.md) | 页面布局、交互流程、视觉规范 | UI 设计、新页面开发 |
| 08 | [日志与可观测性](08-log-monitor.md) | 三层日志体系、诊断手册、远程排障 SOP | 问题排查、性能监控 |
| 09 | [WebSocket + WebRTC 协议详解](09-websocket-webrtc-protocol.md) | SDP/DTLS/ICE 协议深度解析、双通道对比 | 协议层调试、深入原理 |
| 10 | [NAT 穿透与 TURN 服务器](10-nat-traversal.md) | STUN/TURN 原理、防火墙穿透、自建 TURN | 网络连通性问题排查 |
| 11 | [Azure Voice Live API 参考](11-azure-voice-live-reference.md) | Azure Voice Live API 完整参考、SDK/api-version 对照 | Azure API 集成细节查阅 |
| 12 | [前端深入](12-frontend-deep-dive.md) | 前端连接管理、媒体渲染技巧详解 | 前端 WebRTC/WebSocket 深度开发 |
| 13 | [后端深入](13-backend-deep-dive.md) | 后端服务端角色、架构选型场景对比 | 后端架构决策、技术选型参考 |
| 14 | [生产环境运维](14-production-operations.md) | 文字语音同步、扩容策略、远程诊断 SOP | 生产环境性能优化与故障排查 |
| appendix | [术语表](appendix-glossary.md) | 通用术语 + WebRTC 术语速查 | 快速查阅术语定义 |

---

## 加载策略

**Agent 按任务选择性加载：**

- 修改后端 WebSocket → 加载 `01` + `04`
- 新增前端组件 → 加载 `01` + `05` + `07`
- 调整 Avatar WebRTC → 加载 `01` + `06`
- 修改数据库 → 加载 `02` + `03`
- 全栈新功能 → 加载 `01`，然后按需加载其余
- 排查线上问题 → 加载 `08`，按诊断手册定位
- 深入协议细节 → 加载 `09`/`10`
- 深入 Azure API → 加载 `11`
- 前端/后端架构深挖 → 加载 `12`/`13`
- 生产运维排障 → 加载 `14`

---

## 核心架构速览

```
Browser (React)                    Backend (FastAPI)                 Azure Cloud
┌────────────────┐                ┌────────────────┐              ┌──────────────────┐
│ VoiceSession   │◄──WebSocket──►│ voice_live_ws  │◄──SDK──────►│ Voice Live API   │
│   component    │   (audio +    │   proxy handler │  (azure.ai  │ (GPT Realtime    │
│                │    events)    │                │   .voicelive)│  + STT/TTS/VAD)  │
├────────────────┤                └────────────────┘              └──────────────────┘
│ useVoiceLive   │  ← WebSocket hook                                     │
│ useAvatarStream│  ← WebRTC hook                                        │
│ useAudioHandler│  ← Mic capture (AudioWorklet, 24kHz PCM16)            │
│ useAudioPlayer │  ← Playback (base64 PCM16 → AudioBuffer)             │
├────────────────┤                                                       │
│ AvatarView     │◄──WebRTC (ICE/SDP)──────────────────────────────────►│
│  <video>       │   H.264 video + audio tracks                  Azure AI Avatar
│  <audio>       │                                               (Digital Human)
└────────────────┘
```

---

## 关键设计决策

1. **Backend WebSocket Proxy** — 前端不直接连 Azure，通过后端 Python SDK 代理，保护 API Key
2. **双路径 Agent 架构** — 文本会话直连 Agent Responses API（`agent_chat_service.py`），语音会话经 Voice Live WebSocket 代理以 `agent_name=`/`project_name=` 连接同一个 Hosted Agent（详见 [01-architecture.md](01-architecture.md) 的双路径架构一节）；认证以 Entra ID 为先，API Key 为回退（D-01）
3. **VoiceLiveInstance 实体** — 独立于 HCP Profile 的可复用配置实体，一个实例可分配给多个 HCP
4. **配置强制要求** — 每个 HCP 必须分配 `VoiceLiveInstance`（D-09/D-10 起为强制项）；HCP Profile 内联语音字段已彻底删除，不再作为回退路径
5. **双路并行** — WebSocket (语音+文本) 与 WebRTC (数字人视频) 同时建立，互不阻塞
6. **Azure Voice Live SDK** — 使用 `azure-ai-voicelive` Python SDK，非直接 WebSocket 调用

## 源码文件索引

### Backend
| 文件 | 用途 |
|------|------|
| `backend/app/models/voice_live_instance.py` | VL 实例 ORM 模型 |
| `backend/app/models/hcp_profile.py` | HCP Profile（含 VL FK） |
| `backend/app/api/voice_live.py` | REST + WS 路由 |
| `backend/app/schemas/voice_live.py` | Token/Status 响应 Schema |
| `backend/app/schemas/voice_live_instance.py` | 实例 CRUD Schema |
| `backend/app/services/voice_live_websocket.py` | WebSocket 代理核心 |
| `backend/app/services/voice_live_service.py` | Token 分发 + 状态查询 |
| `backend/app/services/voice_live_instance_service.py` | 实例 CRUD + 配置解析 |
| `backend/app/services/voice_live_models.py` | 支持的 AI 模型列表 |
| `backend/app/services/avatar_characters.py` | Avatar 角色元数据 |

### Frontend
| 文件 | 用途 |
|------|------|
| `frontend/src/components/voice/voice-session.tsx` | 主编排组件（549 行） |
| `frontend/src/components/voice/avatar-view.tsx` | Avatar 视频显示 |
| `frontend/src/components/voice/voice-controls.tsx` | 底部控制栏 |
| `frontend/src/components/voice/voice-transcript.tsx` | 实时转写显示 |
| `frontend/src/components/voice/voice-config-panel.tsx` | 配置面板 |
| `frontend/src/hooks/use-voice-live.ts` | WebSocket 客户端 Hook |
| `frontend/src/hooks/use-avatar-stream.ts` | WebRTC 客户端 Hook |
| `frontend/src/hooks/use-audio-handler.ts` | 麦克风采集 Hook |
| `frontend/src/hooks/use-audio-player.ts` | 音频播放 Hook |
| `frontend/src/pages/admin/vl-instance-editor.tsx` | VL 实例编辑器+Playground |
| `frontend/src/types/voice-live.ts` | TypeScript 类型定义 |
| `frontend/public/audio-processor.js` | AudioWorklet 处理器 |
