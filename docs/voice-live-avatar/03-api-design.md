# 03 — API 接口设计

路由前缀：`/api/v1/voice-live`，源码：`backend/app/api/voice_live.py`

## REST 端点

### 配置查询

| 方法 | 路径 | 功能 | 认证 |
|------|------|------|------|
| GET | `/models` | 获取支持的 AI 模型列表 | JWT |
| POST | `/token` | 获取 VL 连接元数据（masked token） | JWT |
| GET | `/status` | 检查 VL + Avatar 可用性 | JWT |

#### POST /token
```json
// Request
{ "hcp_profile_id": "uuid-optional" }

// Response 200
{
  "endpoint": "https://xxx.services.ai.azure.com",
  "token": "***configured***",    // 永远 masked，安全设计
  "region": "eastasia",
  "model": "gpt-4o",
  "auth_type": "api_key",
  "avatar_enabled": true,
  "avatar_character": "lisa",
  "avatar_style": "casual-sitting",
  "voice_name": "zh-CN-XiaoxiaoMultilingualNeural",
  "agent_id": null,                // 同步成功后非空；未同步的 HCP 会被拒绝而非静默回退（D-08）
  "agent_version": null,
  // 每个 HCP 的个性化字段
  "turn_detection_type": "azure_semantic_vad",
  "noise_suppression": true,
  "echo_cancellation": true,
  "recognition_language": "zh-CN",
  "response_temperature": 0.8,
  "proactive_engagement": false,
  "auto_detect_language": true,
  "playback_speed": 1.0,
  "custom_lexicon_enabled": false
}
```

### Avatar 角色

| 方法 | 路径 | 功能 | 认证 |
|------|------|------|------|
| GET | `/avatar-characters` | 获取全部 Avatar 角色列表 | JWT |
| GET | `/avatar-thumbnail/{character_id}` | 307 重定向到 CDN 缩略图 | 无需 |

```json
// GET /avatar-characters Response
{
  "characters": [
    {
      "id": "lisa",
      "display_name": "Lisa",
      "gender": "female",
      "is_photo_avatar": false,       // false=Video(WebRTC H.264), true=Photo(VASA-1)
      "styles": [
        { "id": "casual-sitting", "display_name": "Casual Sitting" },
        { "id": "graceful-standing", "display_name": "Graceful Standing" }
      ],
      "default_style": "casual-sitting",
      "thumbnail_url": "https://learn.microsoft.com/...lisa.png"
    }
  ]
}
```

### VL 实例 CRUD

| 方法 | 路径 | 功能 | 状态码 |
|------|------|------|--------|
| POST | `/instances` | 创建实例 | 201 |
| GET | `/instances` | 分页列表 | 200 |
| GET | `/instances/{id}` | 获取单个 | 200 |
| PUT | `/instances/{id}` | 更新实例 | 200 |
| DELETE | `/instances/{id}` | 删除实例（自动取消分配） | 204 |
| POST | `/instances/{id}/assign` | 分配给 HCP | 200 |
| POST | `/instances/unassign` | 取消 HCP 分配 | 200 |

```json
// POST /instances Request (VoiceLiveInstanceCreate)
{
  "name": "VL-Dr. Wang Fang",
  "voice_live_model": "gpt-4o",
  "enabled": true,
  "voice_name": "zh-CN-XiaoxiaoMultilingualNeural",
  "avatar_enabled": true,
  "avatar_character": "lisa",
  "avatar_style": "casual-sitting",
  "turn_detection_type": "azure_semantic_vad",
  "noise_suppression": true,
  "echo_cancellation": true,
  "response_temperature": 0.8,
  "recognition_language": "zh-CN",
  "auto_detect_language": true,
  "agent_instructions_override": "你是王芳医生，肿瘤科主任..."
}

// Response 201 (VoiceLiveInstanceResponse)
{
  "id": "uuid",
  "name": "VL-Dr. Wang Fang",
  "hcp_count": 0,                    // 已分配的 HCP 数量
  "created_at": "2026-04-06T...",
  "updated_at": "2026-04-06T...",
  // ... 全部配置字段
}
```

## WebSocket 端点

### WS /ws — 实时语音代理

**连接**：`wss://host/api/v1/voice-live/ws?token=<JWT>`

> 浏览器 WebSocket API 不能设置 Header，所以 JWT 通过 query param 传递。

**协议流程**：

```
Client → Backend: session.update
{
  "type": "session.update",
  "session": {
    "hcp_profile_id": "uuid",
    "system_prompt": "你是一位肿瘤科医生..."
  }
}

Backend → Client: proxy.connected
{
  "type": "proxy.connected",
  "message": "Connected to Azure Voice Live",
  "avatar_enabled": true,
  "model": "gpt-4o"
}

Azure → Client (via proxy): session.created
Azure → Client (via proxy): session.updated (含 ICE servers)

Client → Azure (via proxy): input_audio_buffer.append
{
  "type": "input_audio_buffer.append",
  "audio": "<base64 PCM16 24kHz>"
}

Azure → Client (via proxy): response.audio.delta
{
  "type": "response.audio.delta",
  "delta": "<base64 audio>"
}

Azure → Client (via proxy): response.audio_transcript.delta
{
  "type": "response.audio_transcript.delta",
  "delta": "你好，我是..."
}

Client → Azure (via proxy): session.avatar.connect
{
  "type": "session.avatar.connect",
  "client_sdp": "<base64 encoded SDP offer>"
}

Azure → Client (via proxy): session.updated (含 server_sdp)
```

**关键消息类型**：

| 方向 | 消息类型 | 用途 |
|------|----------|------|
| C→S | `session.update` | 初始化会话配置 |
| C→S | `input_audio_buffer.append` | 发送音频数据 |
| C→S | `conversation.item.create` | 发送文本消息 |
| C→S | `response.create` | 触发 AI 响应 |
| C→S | `session.avatar.connect` | 发送 SDP Offer |
| S→C | `proxy.connected` | Backend 确认连接成功 |
| S→C | `session.created` | Azure 会话已创建 |
| S→C | `session.updated` | 配置确认（含 ICE servers） |
| S→C | `input_audio_buffer.speech_started` | VAD 检测到说话 |
| S→C | `input_audio_buffer.speech_stopped` | VAD 检测到停止 |
| S→C | `conversation.item.input_audio_transcription.completed` | 用户语音转文字完成 |
| S→C | `response.audio.delta` | AI 音频增量 |
| S→C | `response.audio_transcript.delta` | AI 文字增量 |
| S→C | `response.audio_transcript.done` | AI 文字完整 |
| S→C | `response.done` | AI 响应结束 |
| S→C | `error` | 错误消息 |
