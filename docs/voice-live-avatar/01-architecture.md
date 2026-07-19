# 01 — 系统架构

## 整体架构

Voice Live + Avatar 功能采用 **三层架构**：Frontend (React) ↔ Backend (FastAPI WebSocket Proxy) ↔ Azure AI Services。

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           FRONTEND (React SPA)                               │
│                                                                              │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐   │
│  │VoiceSession │  │useVoiceLive  │  │useAvatarStream│  │useAudioHandler│   │
│  │ (编排组件)   │  │ (WebSocket)  │  │  (WebRTC)    │  │ (麦克风采集)   │   │
│  └──────┬──────┘  └──────┬───────┘  └──────┬───────┘  └───────┬───────┘   │
│         │                │                  │                   │            │
│    ┌────┴────┐     ┌─────┴─────┐     ┌─────┴──────┐    ┌──────┴──────┐    │
│    │AvatarView│    │WebSocket  │     │RTCPeerConn │    │AudioWorklet │    │
│    │<video>   │    │Client     │     │ICE/SDP     │    │24kHz PCM16  │    │
│    │<audio>   │    │           │     │            │    │             │    │
│    └─────────┘    └─────┬─────┘     └─────┬──────┘    └─────────────┘    │
└─────────────────────────┼───────────────────┼────────────────────────────────┘
                          │ WebSocket          │ WebRTC (ICE/SDP via WS)
                          │ wss://host/api/    │
                          │ v1/voice-live/ws   │
┌─────────────────────────┼───────────────────┼────────────────────────────────┐
│                  BACKEND (FastAPI ASGI)       │                                │
│                          │                   │                                │
│  ┌───────────────────────┴──────────┐        │                                │
│  │  voice_live_websocket.py         │        │                                │
│  │  WebSocket Proxy Handler         │        │                                │
│  │                                  │        │                                │
│  │  Client ←→ [Message Router] ←→ Azure SDK  │                                │
│  │            ↕                     │        │                                │
│  │  Config Resolution               │        │                                │
│  │  (VoiceLiveInstance > HCP inline) │        │                                │
│  └───────────────────────┬──────────┘        │                                │
│                          │ azure-ai-voicelive│                                │
│                          │ Python SDK        │                                │
└──────────────────────────┼───────────────────┼────────────────────────────────┘
                           │                   │
┌──────────────────────────┼───────────────────┼────────────────────────────────┐
│                    AZURE AI SERVICES          │                                │
│                          │                   │                                │
│  ┌───────────────────────┴──────────┐  ┌─────┴──────────────────────────┐    │
│  │  Voice Live API                  │  │  Azure AI Avatar               │    │
│  │  - GPT Realtime (对话)           │  │  - H.264 视频流 (WebRTC)       │    │
│  │  - Azure STT (语音识别)          │  │  - 口型同步 (Lip Sync)          │    │
│  │  - Azure TTS (语音合成)          │  │  - 面部表情 (Facial Expression)  │    │
│  │  - VAD (语音活动检测)            │  │  - VASA-1 (Photo Avatar)        │    │
│  │  - 降噪 / 回声消除              │  │  - TURN Server (ICE)            │    │
│  └──────────────────────────────────┘  └────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────────┘
```

## 连接建立时序

```
Browser                      Backend                       Azure Voice Live
   │                            │                               │
   │  1. WS Connect             │                               │
   │  ws://host/api/v1/         │                               │
   │  voice-live/ws?token=JWT   │                               │
   │───────────────────────────►│                               │
   │                            │  2. JWT 验证                  │
   │                            │                               │
   │  3. session.update         │                               │
   │  {hcp_profile_id,          │                               │
   │   system_prompt}           │                               │
   │───────────────────────────►│                               │
   │                            │  4. 加载配置                   │
   │                            │  VoiceLiveInstance             │
   │                            │  > HCP inline fields           │
   │                            │                               │
   │                            │  5. azure.ai.voicelive.connect│
   │                            │───────────────────────────────►│
   │                            │                               │
   │                            │  6. session.configure          │
   │                            │  (model, voice, avatar,        │
   │                            │   VAD, noise, echo)            │
   │                            │───────────────────────────────►│
   │                            │                               │
   │  7. proxy.connected        │                               │
   │  {avatar_enabled, model}   │                               │
   │◄───────────────────────────│                               │
   │                            │                               │
   │                            │  8. session.created            │
   │  8. session.created        │◄───────────────────────────────│
   │◄───────────────────────────│                               │
   │                            │                               │
   │                            │  9. session.updated            │
   │  9. session.updated        │  (含 ICE servers, credentials)│
   │  (含 ICE config)           │◄───────────────────────────────│
   │◄───────────────────────────│                               │
   │                            │                               │
   │  10. WebRTC 建立            │                     Azure Avatar
   │  RTCPeerConnection         │                         │
   │  + ICE gathering           │                         │
   │  + SDP Offer               │                         │
   │─────────────────── session.avatar.connect ──────────►│
   │                            │                         │
   │◄───────────── SDP Answer (server_sdp) ──────────────│
   │  setRemoteDescription      │                         │
   │                            │                         │
   │◄═══════ WebRTC Media ═════════════════════════════►│
   │  H.264 Video + Audio       │                         │
   │                            │                         │
   │  11. 开始录音               │                         │
   │  AudioWorklet → PCM16      │                         │
   │  → input_audio_buffer.     │                         │
   │    append (base64)         │                         │
   │───────────────────────────►│────────────────────────►│
   │                            │                         │
   │  response.audio.delta      │                         │
   │  response.audio_transcript │                         │
   │◄───────────────────────────│◄────────────────────────│
```

## 关键设计决策

### 1. Backend Proxy 模式（非前端直连）
- **原因**：保护 Azure API Key 不暴露到浏览器
- **实现**：后端使用 `azure-ai-voicelive` Python SDK 建立与 Azure 的连接，前端仅通过 backend WebSocket 通信
- **Token 端点**：`/voice-live/token` 返回 masked token（`***configured***`），前端不获取真实密钥

### 2. 双路径架构 (Dual-Path Architecture)
- **原因**：文本会话和语音会话使用不同的传输协议，但都必须路由到同一个 Hosted Agent，避免"两套人格/两套知识库"的不一致
- **文本路径**：MR/Browser 通过 HTTP 直接调用 Agent Responses API（`backend/app/services/agent_chat_service.py`）
- **语音路径**：MR/Browser 通过 WebSocket 连接后端的 `voice_live_websocket.py` 代理，后端以 `azure.ai.voicelive.aio.connect(agent_name=..., project_name=...)` 建立到 Azure Voice Live 的会话，Voice Live 内部再路由到同一个 Hosted Agent
- **同步机制**：`agent_sync_service.py` 负责确保 Hosted Agent 在 Azure AI Foundry 侧的配置与 HCP Profile 数据保持一致，避免文本/语音两条路径读到不同版本的 Agent 定义

```
文本会话:  MR/Browser ──HTTP──► Agent Responses API (agent_chat_service.py) ──► Hosted Agent (Foundry)
语音会话:  MR/Browser ──WebSocket──► voice_live_websocket proxy ──azure.ai.voicelive.aio.connect(agent_name=...)──► Hosted Agent (Foundry)
```

- **认证**：Entra ID (Azure AD) 优先，API Key 作为回退（D-01）；两条路径共享同一套凭据解析逻辑
- 经典的 `asst_*` classic-agent 分支已被移除（D-06/D-08），未同步到 Hosted Agent 的 HCP 会被拒绝而非静默回退（D-08）

### 3. 配置强制要求
```
每个 HCP Profile 必须分配一个 VoiceLiveInstance（无回退路径）
```
- `resolve_voice_config(profile)` 函数解析 HCP 关联的 `VoiceLiveInstance` 配置
- HCP Profile 内联语音字段已被彻底删除（D-09），不再作为 fallback 存在——这不是"deprecated 但保留兼容"，而是字段本身已从模型中移除

### 4. 双通道并行
- **WebSocket 通道**：语音数据 + 文本消息 + 控制事件
- **WebRTC 通道**：Avatar 视频流 + 音频流
- 两个通道独立建立，互不阻塞

### 5. 音频参数
- 采样率：**24kHz**
- 编码：**PCM16** (Int16)
- 声道：**单声道 (Mono)**
- 传输：**Base64 编码** 通过 WebSocket JSON
- 浏览器采集：AudioWorklet (`audio-processor.js`)

## 技术依赖

### Backend
| 依赖 | 版本 | 用途 |
|------|------|------|
| `azure-ai-voicelive` | latest | Voice Live SDK（connect + session config） |
| `azure-core` | latest | AzureKeyCredential 认证 |
| `fastapi` | >=0.115 | WebSocket 端点 |
| `python-jose` | >=3.3 | JWT 解析（WS 认证） |

### Frontend
| 依赖 | 版本 | 用途 |
|------|------|------|
| 原生 WebSocket API | - | 与后端通信 |
| 原生 RTCPeerConnection | - | Avatar WebRTC |
| 原生 AudioWorklet | - | 麦克风采集 |
| 原生 AudioContext | - | 音频播放 |

> 前端零第三方语音/WebRTC 依赖，全部使用浏览器原生 API。
