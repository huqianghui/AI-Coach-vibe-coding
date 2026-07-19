# 04 — 后端 WebSocket 代理

源码：`backend/app/services/voice_live_websocket.py`

## 核心架构

Backend 作为 **透明代理**，在前端 WebSocket 和 Azure Voice Live SDK 之间双向转发消息。

```
Client WebSocket ←→ handle_voice_live_websocket() ←→ azure.ai.voicelive.aio.connect()
```

## 连接流程

```python
async def handle_voice_live_websocket(websocket: WebSocket, db: AsyncSession):
    # 1. Accept WebSocket
    await websocket.accept()

    # 2. 等待 session.update（30s 超时）
    data = await asyncio.wait_for(websocket.receive_json(), timeout=30)
    hcp_profile_id = data["session"].get("hcp_profile_id")
    system_prompt = data["session"].get("system_prompt")

    # 3. 加载配置 _load_connection_config()
    config = await _load_connection_config(db, hcp_profile_id, system_prompt)

    # 4. 连接 Azure SDK（agent_name/project_name 定位 Hosted Agent，取代旧的 model= 参数；D-05/D-06/D-08 起废弃 classic asst_* 分支）
    async with azure.ai.voicelive.aio.connect(
        endpoint=config["endpoint"],
        credential=get_credential(),  # Entra ID 优先，API Key 回退（D-01）
        agent_name=config["agent_name"],
        project_name=config["project_name"],
        api_version=settings.voice_live_api_version  # "2026-07-15"（GA，见 backend/app/config.py）
    ) as azure_conn:
        # 5. 配置会话 RequestSession
        session_config = RequestSession(
            modalities=["text", "audio"] + (["avatar"] if avatar_enabled else []),
            turn_detection=AzureSemanticVad(),
            audio_noise_reduction=AudioNoiseReduction(...),
            audio_echo_cancellation=AudioEchoCancellation(...),
            input_audio_transcription=AudioInputTranscriptionOptions(...),
            voice=AzureStandardVoice(name=voice_name, type=voice_type),
            instructions=instructions,
            avatar=avatar_config  # AvatarConfig 或 dict(VASA-1)
        )
        await azure_conn.configure(session_config)

        # 6. 发送 proxy.connected 到客户端
        await websocket.send_json({
            "type": "proxy.connected",
            "avatar_enabled": avatar_enabled,
            "model": model
        })

        # 7. 双向消息转发
        await _handle_message_forwarding(websocket, azure_conn)
```

## 配置解析 `_load_connection_config()`

```python
# 优先级链：
# 1. ServiceConfig(service_name="azure_voice_live") — 专用配置
# 2. ServiceConfig(is_master=True, service_name="ai_foundry") — Master fallback
# 3. resolve_voice_config(profile) — VoiceLiveInstance > HCP inline

# endpoint 直接使用（SDK 支持 .services.ai.azure.com）
# instructions: agent_instructions_override > build_agent_instructions(profile)
```

## Avatar 配置

```python
# Video Avatar (WebRTC H.264)
avatar_config = AvatarConfig(
    character=character_id,
    style=style,
    video=VideoParams(codec="h264"),
    output_audit_audio=True  # WebRTC 音频输出
)

# Photo Avatar (VASA-1)
avatar_config = {
    "type": "photo-avatar",
    "model": "vasa-1",
    "character": character_id
}
```

## 双向消息转发

```python
async def _handle_message_forwarding(ws, azure_conn):
    # 两个并行 asyncio Task
    client_task = asyncio.create_task(_forward_client_to_azure(ws, azure_conn))
    azure_task = asyncio.create_task(_forward_azure_to_client(ws, azure_conn))

    # FIRST_COMPLETED: 任一结束则取消另一个
    done, pending = await asyncio.wait(
        [client_task, azure_task],
        return_when=asyncio.FIRST_COMPLETED
    )
    for task in pending:
        task.cancel()
```

**Client → Azure**：`ws.receive_json()` → `azure_conn.send(parsed_message)`
**Azure → Client**：`async for event in azure_conn` → `ws.send_json(event_dict)`

## 关键注意事项

1. **JWT via Query Param** — WebSocket 不支持 Header，token 通过 `?token=` 传递
2. **30s 超时** — session.update 必须在连接后 30 秒内发送
3. **Avatar SDP 透传** — `session.avatar.connect` 直接转发，不做处理
4. **错误处理** — WebSocket 断开时自动清理 Azure 连接
5. **日志** — 记录 avatar 事件（ICE servers、SDP、credentials）用于调试
