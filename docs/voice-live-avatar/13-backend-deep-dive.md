# 13 — 后端深入

<!-- merged from README/07-backend/README.md, README/08-architecture/README.md -->

> 返回 [文档目录](./00-index.md)

---

在前端完成 WebRTC 连接管理和媒体流渲染之后（见 [12-frontend-deep-dive.md](./12-frontend-deep-dive.md)），一个自然的问题随之而来：**Python 服务端在 WebRTC 体系中扮演什么角色？需要用到哪些库？实现有多复杂？** 本章先回答这个问题，再退一步，从场景驱动的角度讨论 WebSocket/WebRTC 的架构选型，以及本项目和标准视频会议架构的区别。

---

## 后端实现 —— Python 服务端

答案取决于一个关键判断：**服务端是否需要接触（"碰"）媒体流**。如果只做信令转发（SDP/ICE 消息的中继），那不需要任何 WebRTC 库，和普通 WebSocket 服务器一样简单；如果要转发甚至处理媒体流，才需要引入 `aiortc` 等专用库。本节将按照这三种角色逐一讲解，并给出生产环境的技术选型建议。

### 服务端角色决定实现复杂度

在 WebRTC 架构中，服务端可以承担三种截然不同的角色，每种角色对应的实现复杂度差异巨大。下面这张表格是理解后续所有内容的基础：

```
┌──────────────┬───────────────┬───────────────────────────────────────┐
│ 角色          │ 碰不碰媒体流？ │ 复杂度                               │
├──────────────┼───────────────┼───────────────────────────────────────┤
│ 信令服务器    │ ❌ 不碰        │ ★☆☆ 和 WebSocket 一样简单            │
│ (Signaling)  │ 只转发 SDP/ICE│ 就是 WebSocket 消息路由               │
├──────────────┼───────────────┼───────────────────────────────────────┤
│ 媒体转发服务器│ ⚠️ 转发但不处理│ ★★★ 需要专门的媒体服务器框架          │
│ (SFU)        │ 收A的流→发给B │ Python: aiortc / 更推荐: mediasoup   │
├──────────────┼───────────────┼───────────────────────────────────────┤
│ 媒体处理服务器│ ✅ 处理媒体    │ ★★★★ 需要编解码+WebRTC 全栈          │
│ (MCU/AI)     │ 解码→处理→编码│ Python: aiortc + opencv/ffmpeg       │
└──────────────┴───────────────┴───────────────────────────────────────┘
```

可以看到，从"信令"到"媒体处理"，复杂度跨越了几个量级。接下来我们依次展开。

### 信令服务器（本项目方案，最常见）

本项目的后端就是典型的**信令服务器**：服务端完全不碰 WebRTC 媒体流，只用 WebSocket 转发 SDP 和 ICE 候选。这是最常见也是最简单的方案。实际生产代码中，这个角色由 `voice_live_websocket.py` 承担，转发的是 Azure SDK 事件而非通用 SDP 房间广播，但底层原理一致。

#### 完整的信令服务器示例

```python
# ===== 一个完整的 WebRTC 信令服务器（通用示例，非本项目实际实现）=====
# 依赖: pip install fastapi uvicorn websockets
# 注意: 不需要任何 WebRTC 库！

from fastapi import FastAPI, WebSocket
import json

app = FastAPI()
rooms: dict[str, list[WebSocket]] = {}

@app.websocket("/ws/{room_id}")
async def signaling(ws: WebSocket, room_id: str):
    await ws.accept()
    if room_id not in rooms:
        rooms[room_id] = []
    rooms[room_id].append(ws)

    try:
        while True:
            msg = await ws.receive_text()
            # 服务端做的事：原封不动转发给房间里的其他人
            for peer in rooms[room_id]:
                if peer != ws:
                    await peer.send_text(msg)
            # data["type"] == "offer"     → 转发 SDP Offer
            # data["type"] == "answer"    → 转发 SDP Answer
            # data["type"] == "candidate" → 转发 ICE Candidate
    except Exception:
        rooms[room_id].remove(ws)
```

这就是全部了——不到 20 行代码。服务端只需要懂 WebSocket，对 WebRTC 协议本身完全不需要了解。

#### 对应的前端代码

```javascript
// 前端：通过信令服务器建立 WebRTC P2P 连接（通用示例）
const ws = new WebSocket(`wss://server/ws/room123`);
const pc = new RTCPeerConnection({
  iceServers: [{ urls: "stun:stun.l.google.com:19302" }]
});

// 本地摄像头
const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
stream.getTracks().forEach(track => pc.addTrack(track, stream));

// ICE candidate → 通过 WebSocket 发给对方
pc.onicecandidate = (e) => {
  if (e.candidate) ws.send(JSON.stringify({ type: "candidate", candidate: e.candidate }));
};

// 收到对方的媒体流
pc.ontrack = (e) => { document.getElementById("remoteVideo").srcObject = e.streams[0]; };

// 发起方：创建 Offer
const offer = await pc.createOffer();
await pc.setLocalDescription(offer);
ws.send(JSON.stringify({ type: "offer", sdp: offer.sdp }));

// 收到信令消息
ws.onmessage = async (e) => {
  const data = JSON.parse(e.data);
  if (data.type === "offer") {
    await pc.setRemoteDescription({ type: "offer", sdp: data.sdp });
    const answer = await pc.createAnswer();
    await pc.setLocalDescription(answer);
    ws.send(JSON.stringify({ type: "answer", sdp: answer.sdp }));
  }
  if (data.type === "answer") await pc.setRemoteDescription({ type: "answer", sdp: data.sdp });
  if (data.type === "candidate") await pc.addIceCandidate(data.candidate);
};
```

#### 数据流向

理解信令服务器的关键在于理解数据流向——服务端只参与信令交换，不参与媒体传输：

```
用户 A 浏览器                Python 服务端              用户 B 浏览器
     │                         │                          │
     │ ──SDP Offer──►         │                          │
     │   (WebSocket)          │ ──转发 Offer──►          │
     │                         │   (WebSocket)            │
     │                         │          ◄──SDP Answer── │
     │          ◄──转发 Answer──│           (WebSocket)    │
     │            (WebSocket)  │                          │
     │                         │                          │
     │ ══════════ WebRTC 媒体流（P2P直连）══════════════ │
     │           服务端完全不参与！                        │
     │           视频音频直接在两个浏览器之间流动           │

Python 服务端的工作量：
  ✅ 处理 WebSocket 连接
  ✅ 转发 JSON 消息（SDP、ICE candidate）
  ❌ 不处理任何音视频数据
  ❌ 不需要任何 WebRTC 库
```

这种架构下，音视频数据直接在两端之间点对点传输，服务端的压力极低。本项目中，Azure Avatar 服务扮演了"对端"的角色（而不是另一个用户浏览器），但服务端不碰媒体流这一核心原则完全一致。

### SFU 媒体转发（多人视频会议）

当场景从 1v1 扩展到多人视频会议时，纯 P2P 架构会遇到带宽瓶颈。此时需要引入 SFU（Selective Forwarding Unit），服务端负责接收每个人的媒体流并转发给其他参与者。**本项目不需要 SFU**（只有 1 个用户看 1 个数字人），此节仅供架构选型参考。

#### 为什么需要 SFU？

```
没有 SFU（纯 P2P，3人会议）：
  每个人要向其他 2 人各发一份流
  A ══► B    A ══► C    B ══► A    B ══► C    C ══► A    C ══► B
  每人上传 2 份 = 6 条流
  10 人会议 = 每人上传 9 份 = 90 条流 → 带宽爆炸

有 SFU（服务端转发）：
  每个人只上传 1 份给服务器，服务器转发给其他人
  A ══► SFU ══► B, C
  B ══► SFU ══► A, C
  C ══► SFU ══► A, B
  每人上传 1 份 = 3 条上行，SFU 负责复制转发
  10 人会议 = 每人上传 1 份 = 10 条上行 → 可控
```

#### Python 用 aiortc 实现 SFU（简化示例）

```python
# 依赖: pip install aiortc aiohttp
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaRelay
from aiohttp import web

relay = MediaRelay()
peers: dict[str, RTCPeerConnection] = {}

async def offer_handler(request):
    params = await request.json()
    user_id = params["user_id"]
    pc = RTCPeerConnection()
    peers[user_id] = pc

    @pc.on("track")
    async def on_track(track):
        # 收到一个用户的媒体轨道 → 转发给其他人
        for other_id, other_pc in peers.items():
            if other_id != user_id:
                other_pc.addTrack(relay.subscribe(track))  # 零拷贝复制

    offer = RTCSessionDescription(sdp=params["sdp"], type="offer")
    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    return web.json_response({"sdp": pc.localDescription.sdp, "type": "answer"})
```

`aiortc` 提供了 Python 原生的 WebRTC 实现，`MediaRelay` 可以高效地将一个 track 复制分发给多个接收者。这对于原型验证和小规模场景已经够用。

### 媒体处理服务器（AI 分析/录制/混流）

最复杂的场景是服务端不仅要接收 WebRTC 流，还要对媒体数据进行解码、AI 处理（如人脸检测、情感分析）、再编码后发回客户端。本项目也不需要这一层——数字人渲染完全在 Azure 侧完成，本地服务端不参与媒体处理。

```python
# 依赖: pip install aiortc opencv-python-headless numpy
from aiortc import VideoStreamTrack
from av import VideoFrame
import cv2

class AIProcessedVideoTrack(VideoStreamTrack):
    """接收视频帧 → AI 处理 → 返回处理后的帧"""
    def __init__(self, source_track):
        super().__init__()
        self.source = source_track

    async def recv(self):
        frame = await self.source.recv()
        img = frame.to_ndarray(format="bgr24")      # 解码为 OpenCV 格式

        # AI 处理（如人脸检测）
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.3, 5)
        for (x, y, w, h) in faces:
            cv2.rectangle(img, (x, y), (x+w, y+h), (0, 255, 0), 2)

        new_frame = VideoFrame.from_ndarray(img, format="bgr24")
        new_frame.pts = frame.pts
        new_frame.time_base = frame.time_base
        return new_frame                              # 编码后发回客户端
```

这种模式下，服务端需要完整的视频编解码能力，CPU 开销显著增加。适用于 AI 监控、实时字幕叠加、虚拟背景替换等场景。

### 三种场景的技术选型对比

了解了三种角色之后，我们可以从多个维度进行横向对比，以便在实际项目中做出正确选型：

```
┌──────────────┬─────────────────┬────────────────────┬──────────────────┐
│              │ 场景1: 信令      │ 场景2: SFU 转发     │ 场景3: 媒体处理   │
├──────────────┼─────────────────┼────────────────────┼──────────────────┤
│ Python 库    │ 无需WebRTC库     │ aiortc             │ aiortc + av      │
│              │ fastapi/aiohttp  │                    │ + opencv         │
├──────────────┼─────────────────┼────────────────────┼──────────────────┤
│ 协议处理      │ 只处理WebSocket  │ WebSocket + WebRTC │ WebSocket+WebRTC │
│              │ (JSON 转发)      │ (RTP 包转发)       │ (完整编解码)      │
├──────────────┼─────────────────┼────────────────────┼──────────────────┤
│ CPU 开销      │ 极低             │ 中等（网络IO）     │ 高（编解码+AI）  │
├──────────────┼─────────────────┼────────────────────┼──────────────────┤
│ 适用场景      │ 1v1 视频通话     │ 多人视频会议       │ AI监控/录制/     │
│              │ 本项目的后端      │ 直播间             │ 虚拟背景/字幕    │
├──────────────┼─────────────────┼────────────────────┼──────────────────┤
│ 生产环境推荐  │ ✅ Python 足够   │ ⚠️ 推荐 mediasoup │ ⚠️ 推荐专用引擎 │
│              │                 │ (Node.js) 或       │ 或 C/Rust 实现   │
│              │                 │ Janus (C)          │                  │
└──────────────┴─────────────────┴────────────────────┴──────────────────┘
```

核心结论很明确：对于本项目这样只需要信令转发的场景，Python + FastAPI 就是最佳选择；而对于需要碰媒体流的场景，Python 更适合做原型验证，生产环境则应考虑专用引擎。

### 生产级 SFU/MCU 方案

如果你的项目确实需要在服务端处理媒体流（如多人视频会议、直播间），需要了解 `aiortc` 的局限性以及更成熟的替代方案。

#### aiortc 的定位

```
aiortc 的定位：
  ✅ 功能完整，API 优雅，学习和原型开发首选
  ❌ 单线程 Python 处理 RTP → 高并发下 CPU 瓶颈
  ❌ 视频编解码（libav）在 Python 中开销大
  ❌ 没有大规模生产验证（不像 mediasoup/Janus）
```

#### 生产级方案对比

```
生产级方案对比：
  ┌─────────────────┬───────────┬──────────────────────────┐
  │ 方案              │ 语言      │ 特点                      │
  ├─────────────────┼───────────┼──────────────────────────┤
  │ mediasoup        │ Node.js+C │ 最流行的 SFU，性能好      │
  │ Janus Gateway    │ C         │ 功能丰富，插件架构         │
  │ Pion             │ Go        │ 纯 Go，易部署             │
  │ LiveKit          │ Go        │ 开箱即用，自带前端 SDK     │
  │ aiortc           │ Python    │ 原型/小规模/AI处理场景    │
  └─────────────────┴───────────┴──────────────────────────┘
```

#### 推荐的混合架构

最佳实践是将 Python 的优势（业务逻辑、AI 集成）与专用媒体引擎的优势（高性能媒体处理）结合起来：

```
  推荐架构模式：信令用 Python，媒体处理用专用引擎
    Python FastAPI (信令+业务逻辑) → 调用 mediasoup/LiveKit API (媒体转发)
```

### 后端角色小结

WebSocket 信令服务器用纯 Python 就够了（本项目就是这样），不需要任何 WebRTC 库。如果需要服务端碰媒体流（SFU 转发或 AI 处理），用 `aiortc` 可以快速原型开发，但生产环境推荐用 mediasoup/LiveKit 等专用引擎处理媒体，Python 专注于信令和业务逻辑。本项目的后端实际代码位于 `backend/app/services/voice_live_websocket.py`（WebSocket 代理层）和 `backend/app/services/agent_chat_service.py`（文本会话，走 Agent Responses API），两者最终共享同一个 Hosted Agent（详见 [01-architecture.md](./01-architecture.md)）。

---

## 架构选型 —— 场景驱动的技术决策

在掌握了 WebSocket 和 WebRTC 的底层原理之后，面对实际项目时往往会遇到一个核心问题：**我要做的东西应该用 WebSocket 还是 WebRTC？还是两者配合？**

答案取决于你要做的事情。WebSocket 管"信令和数据"，WebRTC 管"实时音视频"。大多数场景需要两者配合，但主次不同。本节通过四种典型场景的对比分析，帮助你建立场景驱动的技术选型思维。

### 四种典型场景

不同的应用场景对实时性、带宽、方向性的需求截然不同，下面分别分析每种场景的架构特点。

#### 场景 1：视频会议（如 Zoom/Teams）

```
WebRTC = 主角（音视频传输）
WebSocket = 配角（信令 + 聊天 + 控制）

┌─────────────┐     WebRTC (音视频)      ┌─────────────┐
│  用户 A 浏览器 │◄═══════════════════════►│  用户 B 浏览器 │
│             │                          │             │
│  摄像头+麦克风 │     WebSocket (信令)     │  摄像头+麦克风 │
│             │◄────────────────────────►│             │
└──────┬──────┘                          └──────┬──────┘
       │ WebSocket                              │ WebSocket
       ▼                                        ▼
┌──────────────────────────────────────────────────────┐
│              信令服务器 (WebSocket)                     │
│  - SDP Offer/Answer 交换                               │
│  - ICE candidate 中继                                  │
│  - 聊天消息、举手、静音状态                               │
│  - 房间管理（谁在线、谁退出）                             │
└──────────────────────────────────────────────────────┘

特点：
  - WebRTC 负责：摄像头视频 + 麦克风音频 + 屏幕共享
  - WebSocket 负责：房间信令、SDP 交换、文字聊天、状态同步
  - Transceiver direction: "sendrecv"（双向收发）
  - 可能需要 SFU 服务器（多人会议时中转视频流）
```

视频会议是 WebRTC 最经典的应用场景，WebRTC 承载核心的音视频传输，WebSocket 做辅助的信令和控制。

#### 场景 2：直播/视频媒体播放（如 B站/YouTube Live）

直播场景有多种技术方案可选，延迟要求决定了最终选型：

```
方案 A: 纯 WebSocket（低延迟直播，如弹幕互动）
  观众浏览器 ◄── WebSocket ── 服务器 ◄── 推流端
  - 视频帧编码为二进制通过 WebSocket 传输
  - 延迟 ~1-3s，足够应对大多数互动场景
  - 优点：实现简单，服务端可以广播给所有观众
  - 缺点：TCP 拥塞可能导致卡顿

方案 B: WebRTC（超低延迟直播，如拍卖/电竞）
  观众浏览器 ◄═══ WebRTC ═══ 媒体服务器 ◄═══ 推流端
  - Transceiver direction: "recvonly"（观众只收）
  - 延迟 < 500ms
  - 优点：延迟最低，浏览器硬件解码
  - 缺点：需要 SFU/MCU 媒体服务器支撑大量观众

方案 C: HLS/DASH（传统点播/直播）
  观众浏览器 ◄── HTTP ── CDN ◄── 编码服务器
  - 视频切片通过 HTTP 分发
  - 延迟 5-30s
  - 优点：CDN 缓存，支撑百万观众
  - 缺点：延迟高，不适合强互动
```

#### 场景 3：AI 数字人对话（本项目！）

本项目的架构比较特殊，WebSocket 和 WebRTC 并行工作，各自承担不同的数据通道：

```
WebSocket + WebRTC 并行

  WebSocket: 用户语音（base64 上行）+ AI 文字（下行）+ 控制信令
  WebRTC:    数字人视频+音频（下行 recvonly）

  特殊之处：
  - WebRTC 只用于 Avatar 视频，不传用户的媒体
  - 用户音频通过 WebSocket 走后端代理（保护认证凭据）
  - 和视频会议最大的区别：WebRTC 是单向的（recvonly）
  - 无论是文本会话还是语音会话，最终都路由到同一个 Hosted Agent
    （详见 01-architecture.md 的双路径架构一节）
```

#### 场景 4：在线教育白板/协作

```
WebSocket = 主角（实时数据同步）
WebRTC = 可选（如果需要视频/语音）

  WebSocket: 画笔轨迹、文档编辑、光标位置、聊天
  WebRTC:    老师的摄像头/屏幕共享（如果需要）

  白板数据是 JSON，用 WebSocket 足够
  视频/语音才需要 WebRTC
```

### 选择决策树

面对新项目时，可以按照下面的决策树快速定位应该用哪种技术：

```
你要传什么？
  │
  ├── 纯文本/JSON/控制指令 ─────────────────► WebSocket 就够了
  │   (聊天、状态同步、通知推送)
  │
  ├── 音频/视频（实时性要求高 < 500ms）────► WebRTC
  │   (视频通话、低延迟直播)                    + WebSocket 做信令
  │
  ├── 音频/视频（延迟 1-5s 可接受）─────────► WebSocket 传二进制
  │   (直播弹幕、语音消息)                     或 HLS/DASH
  │
  └── 混合场景 ─────────────────────────────► WebSocket + WebRTC 并行
      (AI数字人、在线教育、远程医疗)             各管各的
```

核心原则是：**文本/控制走 WebSocket，实时音视频走 WebRTC，混合场景两者并行**。不要过度设计——能用 WebSocket 解决的就不要引入 WebRTC。

### 本项目 vs 标准视频会议的区别

对于已经了解视频会议架构的读者，理解本项目和标准视频会议的差异至关重要。下表从多个维度进行对比：

| 维度 | 本项目（AI 数字人） | 标准视频会议（Zoom） |
|------|-------------------|---------------------|
| **WebRTC 方向** | `recvonly`（只看数字人） | `sendrecv`（双向音视频） |
| **用户摄像头** | 不需要 | 需要（上传视频流） |
| **用户麦克风音频** | 走 WebSocket（base64） | 走 WebRTC（直接传） |
| **为什么音频不走 WebRTC** | 后端需要代理保护认证凭据 | 不需要代理，直连对方 |
| **信令服务器** | 后端 FastAPI（WebSocket proxy，`voice_live_websocket.py`） | 独立信令服务器 |
| **媒体服务器** | 不需要（Azure Avatar 直推） | 大规模需要 SFU |
| **SDP 交换** | 通过业务 WebSocket | 通过独立信令 WebSocket |

最关键的区别在于 **WebRTC 的方向性**：本项目是单向接收（`recvonly`），而视频会议是双向收发（`sendrecv`）。这个差异决定了本项目不需要处理本地 MediaStream、不需要媒体服务器，架构大幅简化。

### 从零开始做视频会议的架构大纲

如果你的下一个项目是做视频会议而不是 AI 数字人，以下是需要准备的架构蓝图：

```
Frontend
├── useSignaling()        ← WebSocket hook: 房间管理 + SDP 交换
├── useMediaStream()      ← WebRTC hook: 本地摄像头/麦克风
├── usePeerConnection()   ← WebRTC hook: 和对方建立音视频连接
├── useScreenShare()      ← WebRTC hook: 屏幕共享
├── useChat()             ← WebSocket hook: 文字聊天
└── <VideoGrid />         ← UI: 多个 <video> 元素

Backend
├── signaling-server      ← WebSocket: SDP/ICE 中转 + 房间管理
├── TURN server           ← coturn: NAT 穿透中继
└── SFU (可选)            ← mediasoup/Janus: 多人会议媒体转发

关键区别：
  - direction: "sendrecv"（双向，不是 recvonly）
  - 需要处理本地 MediaStream（getUserMedia）
  - 需要处理多人场景（N 个 PeerConnection 或 SFU）
  - 不需要后端代理音频（没有认证凭据要保护）
```

对比本项目的架构，视频会议多出了本地媒体采集（`getUserMedia`）、多人连接管理、SFU 中转等复杂度。但信令层面的 WebSocket 使用方式是相似的，本章以及前面章节学到的 SDP/ICE 知识可以直接复用。

### 架构选型小结

技术选型不存在"银弹"——WebSocket 和 WebRTC 各有所长，选择取决于具体场景。记住决策树的核心逻辑：纯数据用 WebSocket，实时音视频用 WebRTC，混合场景两者并行。理解本项目与标准视频会议的架构差异，有助于你在未来的项目中做出更准确的技术判断。

---

> 返回 [文档目录](./00-index.md) | 相关：[01-architecture.md](./01-architecture.md) · [04-backend-websocket.md](./04-backend-websocket.md)
