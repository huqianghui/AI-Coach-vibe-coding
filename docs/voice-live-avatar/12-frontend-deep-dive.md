# 12 — 前端深入

<!-- merged from README/06-frontend/README.md, README/06-frontend/media-rendering.md -->

> 返回 [文档目录](./00-index.md)

---

本章带你走进前端代码的核心部分。你将看到 WebSocket 和 WebRTC 两种协议在真实项目中的连接代码长什么样、用了哪些 JS 库、UI 组件和协议之间是如何映射的，以及流媒体到达前端之后如何渲染到页面上。读完本章，你将能够理解整个前端语音交互层的工作原理。

---

## 前端连接代码

### WebSocket 连接代码详解（use-voice-live.ts）

WebSocket 是本项目中承载所有文本、控制指令和音频数据的通道。它的连接过程非常简洁——一行代码即可建立。

```typescript
// ===== WebSocket: 一行代码建立连接 =====

// 构造 URL
const protocol = location.protocol === "https:" ? "wss:" : "ws:";
const token = localStorage.getItem("access_token") ?? "";
const wsUrl = `${protocol}//${location.host}/api/v1/voice-live/ws?token=${encodeURIComponent(token)}`;

// 一行连接
const ws = new WebSocket(wsUrl);               // ← 就这一行

// 连接成功后，发 JSON 消息
ws.onopen = () => {
  ws.send(JSON.stringify({
    type: "session.update",
    session: {
      hcp_profile_id: hcpProfileId,
      system_prompt: systemPrompt,
    },
  }));
};

// 收消息
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  // msg.type: "session.created", "response.audio.delta", "response.audio_transcript.delta" ...
};

// 发送用户音频
ws.send(JSON.stringify({
  type: "input_audio_buffer.append",
  audio: "base64编码的PCM16音频..."      // ← 音频塞在 JSON 字符串里
}));
```

可以看到，WebSocket 的使用模式非常直接：

1. **构造 URL**：根据当前页面协议选择 `ws:` 或 `wss:`，附上 JWT token 用于鉴权。
2. **一行建连**：`new WebSocket(wsUrl)` 就完成了。
3. **发消息**：`ws.send()` 发送 JSON 字符串。
4. **收消息**：`ws.onmessage` 回调接收服务端推送。

所有数据——包括音频——都以 JSON 文本帧的形式传输。音频被 base64 编码后塞进 JSON 字符串里。

### WebRTC 连接代码详解（use-avatar-stream.ts）

WebRTC 用于接收数字人的实时视频和音频流。与 WebSocket 不同，WebRTC 的建连是一套多步协商流程。

```typescript
// ===== WebRTC: 一整套协商流程 =====

// 没有 URL！用 ICE servers 配置（从 WebSocket 消息获得）
const pc = new RTCPeerConnection({             // ← 创建连接对象
  iceServers: [                                //    但此时还没真正连通
    {
      urls: "turn:xxx.communication.azure.com:3478",
      username: "临时用户名",
      credential: "临时密码"
    }
  ],
  bundlePolicy: "max-bundle",
});

// 声明"我只接收，不发送"
pc.addTransceiver("video", { direction: "recvonly" });
pc.addTransceiver("audio", { direction: "recvonly" });

// 收到媒体流 → 渲染到 HTML 元素
pc.ontrack = (event) => {
  if (event.track.kind === "video") {
    videoElement.srcObject = event.streams[0];  // ← 视频直接绑到 <video> 标签
  }
  if (event.track.kind === "audio") {
    audioElement.srcObject = event.streams[0];  // ← 音频绑到 <audio> 标签
  }
};

// 创建 SDP Offer（"我的能力清单"）
const offer = await pc.createOffer();
await pc.setLocalDescription(offer);

// 等 ICE gathering 完成（探测网络路径，约 2-8 秒）
// ... 等待 onicecandidate 返回 null 或超时 ...

// 把 SDP Offer 通过 WebSocket 发给 Azure（注意！借用 WebSocket 通道）
const encodedSdp = btoa(JSON.stringify({ type: "offer", sdp: offer.sdp }));
ws.send(JSON.stringify({
  type: "session.avatar.connect",
  client_sdp: encodedSdp                       // ← SDP 协商走 WebSocket
}));

// 等 Azure 返回 SDP Answer（也通过 WebSocket 回来）
// ... 等待 ws.onmessage 收到 server_sdp ...
const answer = JSON.parse(atob(serverSdp));

// 设置对方的 SDP
await pc.setRemoteDescription({                 // ← 此刻 WebRTC 才真正连通！
  type: "answer",
  sdp: answer.sdp
});

// 之后 pc.ontrack 自动触发，视频和音频流开始
```

WebRTC 的建连过程可以拆解为以下关键步骤：

1. **创建 RTCPeerConnection**：用 ICE servers 配置初始化，但此时还没有真正连通。
2. **声明方向**：`addTransceiver` 告诉对方我们只接收（`recvonly`），不发送媒体。
3. **设置 ontrack 回调**：当媒体流到达时，自动绑定到 HTML 元素上。
4. **SDP 协商**：创建 Offer → 等待 ICE gathering → 通过 WebSocket 发给 Azure → 收到 Answer → 设置 RemoteDescription。
5. **流自动开始**：协商完成后，`pc.ontrack` 自动触发，视频和音频流开始推送。

注意一个重要细节：**SDP 协商借用了 WebSocket 通道**。WebRTC 本身没有信令机制，需要借助其他通道（这里是 WebSocket）来交换 SDP。

### 核心差异对比

把两种协议放在一起看，差异一目了然：

```
WebSocket                                 WebRTC
─────────────────────────                 ──────────────────────────────
new WebSocket(url)         ←── 1 行     new RTCPeerConnection(config)
                                          + addTransceiver × 2
                                          + createOffer
                                          + setLocalDescription
                                          + ICE gathering (2-8 秒)
                                          + SDP 交换 (借 WebSocket)
                                          + setRemoteDescription
                                          ←── 7+ 步，异步，可能失败

ws.send(JSON.stringify({}))  发数据      pc.ontrack 自动收到媒体流
ws.onmessage               收数据      （不需要手动"收"，流自动推）

JSON 文本帧                  数据格式     RTP 媒体包（H.264/Opus）
可传任何 JSON                             只传音频和视频流

TCP，可靠有序                 协议        UDP，快但可能丢包
wss://host/path              地址        无 URL，ICE 协商动态发现

主动 send()                  通信方式     被动接收（recvonly）
双向                                    本项目中单向（只收不发）
```

简单总结：WebSocket 是"轻量级文本通道"，一行连通，双向 JSON 消息；WebRTC 是"重量级媒体通道"，多步协商，单向流媒体推送。两者在本项目中协同工作，各司其职。

### 依赖库对比（为什么不用第三方库）

一个令人惊讶的事实是：**两个协议都使用浏览器原生 API，零第三方依赖。**

#### 完整依赖对比

| 维度 | WebSocket | WebRTC |
|------|-----------|--------|
| **核心 API** | `new WebSocket(url)` | `new RTCPeerConnection(config)` |
| **是否浏览器原生** | 是，所有现代浏览器内置 | 是，所有现代浏览器内置 |
| **需要安装 npm 包？** | 不需要 | 不需要 |
| **数据发送** | `ws.send(string)` | 不发（recvonly），或 `RTCDataChannel` |
| **数据接收** | `ws.onmessage` | `pc.ontrack`（媒体流自动推） |
| **关联原生 API** | 无 | `RTCSessionDescription`、`MediaStream`、`HTMLVideoElement`、`HTMLAudioElement` |
| **音频采集** | `AudioWorklet` + `AudioContext`（也是浏览器原生） | 不需要（不采集） |

#### 源码中的 import 对比

```typescript
// use-voice-live.ts — WebSocket hook
import { useCallback, useRef, useState } from "react";  // 只有 React hooks
// 没有任何 WebSocket 的 import，因为 WebSocket 是全局对象 (window.WebSocket)

// use-avatar-stream.ts — WebRTC hook
import { useCallback, useRef, useState } from "react";  // 只有 React hooks
// 没有任何 WebRTC 的 import，因为 RTCPeerConnection 是全局对象 (window.RTCPeerConnection)
```

**两个 hook 的 import 完全一样**——只有 React 的 hooks。所有网络协议能力都来自浏览器自身。

#### 为什么不用第三方库？

| 常见库 | 为什么没用 |
|--------|-----------|
| `socket.io` | 提供自动重连/房间等高级功能，但这里后端是 FastAPI 原生 WebSocket，不需要 socket.io 协议 |
| `simple-peer` | WebRTC 的简化封装，但本项目的 WebRTC 场景很简单（单向接收），用原生 API 更可控 |
| `peerjs` | P2P 通信库，但这里不是 P2P 场景，是浏览器→Azure 单向接收 |
| `mediasoup-client` | SFU 客户端，用于多人视频会议。这里是 1 对 1，不需要 |
| `webrtc-adapter` | 浏览器兼容 polyfill。现代浏览器已统一 API，不再需要 |

> **设计原则**：前端零第三方语音/WebRTC 依赖，全部使用浏览器原生 API。这减少了包体积，避免了版本兼容问题，也让代码更透明可调试。

---

## UI 组件与协议的映射关系

前端的组件并非全部绑定在某一个协议上——有些是共享的，有些是某个协议独占的。下面是完整的组件树和它们的协议归属。

```
VoiceSession (voice-session.tsx) ── 主编排组件，同时管理两个协议
│
├── LEFT PANEL
│   ├── AvatarView (avatar-view.tsx)                    ← WebRTC 独占
│   │   ├── <video ref={videoRef}> ..................... WebRTC ontrack → video
│   │   ├── 隐藏的 <audio> ............................ WebRTC ontrack → audio
│   │   ├── 静态缩略图 <img> .......................... 无协议（纯 UI）
│   │   └── AudioOrb .................................. 无协议（纯 UI 动画）
│   │
│   └── VoiceControls (voice-controls.tsx)              ← 共享（协议无关）
│       ├── 麦克风按钮 ─── toggleMute() ............... → useVoiceLive (WebSocket)
│       ├── 结束通话按钮 ─── disconnect() ............. → 两个协议都断开
│       ├── 键盘切换按钮 ............................... 纯 UI 状态
│       └── 全屏按钮 ................................... 纯 UI 状态
│
└── RIGHT PANEL
    ├── VoiceTranscript (voice-transcript.tsx)           ← WebSocket 独占（数据源）
    │   └── 聊天气泡 ─── transcript 数据 .............. ← 来自 WebSocket 消息
    │
    └── VoiceConfigPanel (voice-config-panel.tsx)        ← 共享（协议无关）
        └── 语言选择、自动检测等 ....................... 纯 UI 配置
```

### 详细分类

| 组件 | 数据来自哪个协议 | 说明 |
|------|-----------------|------|
| **AvatarView `<video>`** | WebRTC 独占 | `pc.ontrack` 把视频流绑定到 `videoRef`，纯 WebRTC 驱动 |
| **AvatarView 隐藏 `<audio>`** | WebRTC 独占 | `pc.ontrack` 创建 `<audio>` 元素，播放数字人口型同步的声音 |
| **AvatarView 静态缩略图** | 无协议 | 连接前显示 Azure CDN 上的角色图片，不涉及任何通信 |
| **AvatarView AudioOrb** | 无协议 | 纯语音模式（无数字人）时显示的动画球，根据 `audioState` 变化 |
| **VoiceTranscript** | WebSocket 独占 | 文字转写全部来自 WebSocket 的 `transcript.delta` / `transcript.done` |
| **VoiceControls** | 协议无关 | 按钮触发 hook 函数（`toggleMute`、`disconnect`），不直接碰协议 |
| **VoiceConfigPanel** | 协议无关 | 纯配置 UI，修改本地 state |
| **useAudioPlayer** | WebSocket | 纯语音模式下，播放 `response.audio.delta`（base64 PCM16）。Avatar 模式下不使用（音频走 WebRTC） |

---

## 模式切换时的组件变化

项目支持两种运行模式：**纯语音模式**和**数字人 Avatar 模式**。切换模式时，同一套组件会展示不同的状态。

```
┌──────────────────────┬──────────────────────┬──────────────────────┐
│                      │  纯语音模式           │  数字人 Avatar 模式   │
│                      │  (voice_realtime)     │  (digital_human)     │
├──────────────────────┼──────────────────────┼──────────────────────┤
│ AvatarView <video>   │  opacity-0 (隐藏)    │  opacity-100 (显示)  │
│ AvatarView AudioOrb  │  显示 (动画波形球)    │  隐藏                │
│ WebRTC <audio>       │  不存在              │  存在 (播放数字人声音) │
│ useAudioPlayer       │  播放 WS 音频        │  不播放 (避免重复)    │
│ VoiceTranscript      │  显示 (文字来自 WS)   │  显示 (文字来自 WS)  │
│ VoiceControls        │  完全相同            │  完全相同             │
│ VoiceConfigPanel     │  完全相同            │  完全相同             │
└──────────────────────┴──────────────────────┴──────────────────────┘

关键切换逻辑在 voice-session.tsx:
  const resolvedMode = result.avatarEnabled
    ? "digital_human_realtime_model"    // WebSocket + WebRTC
    : "voice_realtime_model";           // 仅 WebSocket
```

核心思路是：**纯语音模式只用 WebSocket**（文字、控制、音频全走 WebSocket），**数字人模式同时用 WebSocket + WebRTC**（文字和控制走 WebSocket，视频和音频走 WebRTC）。切换时只需改变 `resolvedMode`，组件自动根据模式调整自己的可见性和行为。

---

## Hooks 与协议的对应

整个前端语音交互层由四个 hook 组成，各管一件事：

```
useVoiceLive      ── WebSocket ── 管理 ws 连接、发送/接收 JSON 消息
useAvatarStream   ── WebRTC   ── 管理 RTCPeerConnection、ICE/SDP、媒体流
useAudioHandler   ── 无协议   ── 管理麦克风采集（AudioWorklet），产出 Float32 → 由 useVoiceLive 发送
useAudioPlayer    ── 无协议   ── 管理音频播放（AudioBuffer），消费 useVoiceLive 收到的 audio.delta
```

四个 hook 通过 `VoiceSession` 这个编排组件串联起来。`VoiceSession` 就像"导演"，WebSocket 和 WebRTC 就像两个"演员"，各自表演不同的部分，但在同一个舞台上。

---

## 流媒体渲染与 UI 组件

当 WebRTC 连接建立后，视频和音频流会源源不断地推送到前端。那么，前端用什么 UI 组件来展示这些流媒体？答案比你想象的简单——**浏览器原生的 `<video>` 和 `<audio>` HTML 标签就是流媒体的渲染组件**。WebRTC 的 MediaStream 通过 `element.srcObject = stream` 绑定到标签上，浏览器自动完成解码和渲染。不需要任何第三方播放器库。

### 核心概念：srcObject 是桥梁

理解流媒体渲染的关键，在于区分传统文件播放和实时流播放的区别：

```
传统的文件播放（你熟悉的）：
  <video src="https://example.com/video.mp4" />
  → 浏览器下载文件 → 解码 → 播放
  → src 是一个 URL，指向一个文件

流媒体播放（WebRTC / 实时流）：
  videoElement.srcObject = mediaStream;
  → 浏览器直接从内存中的 MediaStream 读取帧 → 解码 → 播放
  → srcObject 是一个 JS 对象，指向实时流，不是文件 URL
  → 没有"文件"概念，数据是持续到达的

这就是唯一的区别：src（文件URL） vs srcObject（实时流对象）
```

`srcObject` 就是连接"协议层"和"渲染层"的桥梁。你只需要把 WebRTC 给你的 `MediaStream` 对象赋值给 HTML 元素的 `srcObject` 属性，剩下的一切（解码、渲染、帧率同步）浏览器全包了。

### `<video>` 标签 —— 数字人视频渲染

文件：`frontend/src/components/voice/avatar-view.tsx`

```tsx
// avatar-view.tsx 第 86-95 行
<video
  ref={videoRef}          // ← React ref，让 hook 能通过 JS 操作这个元素
  autoPlay                // ← 收到流后自动播放，不需要用户点击
  playsInline             // ← 移动端不全屏播放（iOS 必需）
  className={cn(
    "absolute inset-0 h-full w-full object-cover",
    isAvatarConnected ? "opacity-100" : "opacity-0",  // ← 连接前透明隐藏
  )}
/>

// 关键：这个 <video> 标签始终在 DOM 中，只是透明度为 0
// 为什么不用 display:none？因为浏览器对 display:none 的元素禁止 autoplay
```

对应的 hook 绑定代码在 `frontend/src/hooks/use-avatar-stream.ts` 中：

```typescript
// use-avatar-stream.ts 第 47-76 行
pc.ontrack = (event) => {
  // WebRTC 每收到一个媒体轨道，触发一次 ontrack

  if (event.track.kind === "video" && videoRef.current) {
    // 视频轨道 → 绑定到 <video> 标签
    videoRef.current.srcObject = event.streams[0];  // ← 就这一行！
    videoRef.current.play();                         // ← 开始播放

    // 之后浏览器自动：
    //   1. 从 MediaStream 中持续读取 RTP 包
    //   2. SRTP 解密
    //   3. H.264 硬件解码（GPU 加速）
    //   4. 渲染到 <video> 元素的画布上
    //   5. 按帧率刷新（通常 30fps）
    //   全自动，JS 代码不需要介入
  }

  if (event.track.kind === "audio") {
    // 音频轨道 → 动态创建隐藏的 <audio> 标签
    const audio = document.createElement("audio");
    audio.srcObject = event.streams[0];   // ← 绑定音频流
    audio.autoplay = true;                // ← 自动播放
    audio.style.display = "none";         // ← 隐藏（只要声音，不要UI）
    document.body.appendChild(audio);     // ← 必须加到 DOM 才能播放
    audio.play();
  }
};
```

核心逻辑非常直观：视频轨道绑定到预先存在的 `<video>` 元素，音频轨道动态创建一个隐藏的 `<audio>` 元素。赋值 `srcObject` 之后，浏览器接管一切。

### 完整的 UI 层次（从上到下）

`avatar-view.tsx` 的渲染结构由四层叠加组成，每层各有用途：

```
avatar-view.tsx 的四层渲染结构：

┌─────────────────────────────────────────────────┐
│  Layer 4 (z-20): HCP 名字条                      │
│  ┌─────────────────────────────────────────────┐│
│  │ "Dr. Zhang"                                 ││
│  └─────────────────────────────────────────────┘│
│                                                  │
│  Layer 3 (z-20): 加载骨架屏                      │
│  ┌─────────────────────────────────────────────┐│
│  │ ⬜ Skeleton + "连接中..."                    ││
│  │ （WebRTC 协商时显示，连接后消失）             ││
│  └─────────────────────────────────────────────┘│
│                                                  │
│  Layer 2 (z-10): WebRTC <video>                  │
│  ┌─────────────────────────────────────────────┐│
│  │ <video ref={videoRef} autoPlay playsInline>  ││
│  │                                             ││
│  │  连接前: opacity-0（透明，但始终在 DOM 中）   ││
│  │  连接后: opacity-100（显示数字人视频）        ││
│  │                                             ││
│  │  数据来源: pc.ontrack → srcObject = stream   ││
│  │  编码: H.264 视频（浏览器 GPU 解码）         ││
│  │  帧率: 30fps                                ││
│  └─────────────────────────────────────────────┘│
│                                                  │
│  Layer 1 (z-5): 静态预览 / AudioOrb             │
│  ┌─────────────────────────────────────────────┐│
│  │ <img> Azure CDN 角色缩略图                   ││
│  │   或                                        ││
│  │ <AudioOrb> 纯语音模式的动画波形球             ││
│  │ （连接后被 <video> 的 opacity-100 覆盖）      ││
│  └─────────────────────────────────────────────┘│
│                                                  │
│  隐藏层: <audio> 数字人语音                      │
│  ┌─────────────────────────────────────────────┐│
│  │ <audio srcObject={stream} autoplay hidden>   ││
│  │ 动态创建，display:none，只播放声音            ││
│  │ 数据来源: pc.ontrack → srcObject = stream    ││
│  │ 编码: Opus 音频（浏览器解码）                ││
│  └─────────────────────────────────────────────┘│
└─────────────────────────────────────────────────┘
```

这种分层设计的好处是：不同状态下只需切换各层的可见性，而不需要销毁和重建 DOM 元素。

### 状态切换时的 UI 变化

随着连接状态和运行模式的变化，各层元素的表现也不同：

```
┌──────────────────┬──────────────┬──────────────┬──────────────┐
│ 状态              │ <video>      │ 静态预览/Orb  │ <audio>      │
├──────────────────┼──────────────┼──────────────┼──────────────┤
│ 未连接            │ opacity-0    │ 显示缩略图    │ 不存在       │
│ (idle)           │ (DOM中但透明) │ 或 AudioOrb  │              │
├──────────────────┼──────────────┼──────────────┼──────────────┤
│ 连接中            │ opacity-0    │ 隐藏          │ 不存在       │
│ (connecting)     │              │ 显示骨架屏    │              │
├──────────────────┼──────────────┼──────────────┼──────────────┤
│ 已连接-数字人模式  │ opacity-100  │ 被覆盖       │ 存在,自动播放 │
│ (digital_human)  │ 显示视频流    │              │ 口型同步声音 │
├──────────────────┼──────────────┼──────────────┼──────────────┤
│ 已连接-纯语音模式  │ opacity-0    │ AudioOrb     │ 不存在       │
│ (voice_only)     │              │ 动画波形球    │ (WS播放音频) │
├──────────────────┼──────────────┼──────────────┼──────────────┤
│ 断开连接          │ srcObject=   │ 恢复缩略图    │ remove()     │
│ (disconnect)     │ null,opacity0│              │ 从DOM移除    │
└──────────────────┴──────────────┴──────────────┴──────────────┘
```

注意"已连接-纯语音模式"和"已连接-数字人模式"的区别：纯语音模式下，AI 回复的音频通过 WebSocket 传输并由 `useAudioPlayer` 播放（程序化方式）；数字人模式下，音频通过 WebRTC 传输并由隐藏的 `<audio>` 元素播放。两种模式下文字转写始终来自 WebSocket。

### 关键的多媒体渲染技巧

以下四个技巧从本项目的真实代码中提炼而来，都是实践中踩过的坑。

#### 技巧 1：`<video>` 始终在 DOM 中，用 opacity 控制可见性

```tsx
// 正确做法（本项目）
<video
  ref={videoRef}
  className={isConnected ? "opacity-100" : "opacity-0"}  // 透明度切换
/>

// 错误做法 1
{isConnected && <video ref={videoRef} />}  // 条件渲染
// 问题: ontrack 触发时 <video> 可能还不在 DOM 中
// → srcObject 赋值失败 → 视频黑屏

// 错误做法 2
<video style={{ display: isConnected ? "block" : "none" }} />
// 问题: display:none 的元素，浏览器会阻止 autoplay
// → play() 抛出异常
```

**为什么**：WebRTC 的 `ontrack` 事件在协商完成后立即触发，此时如果 `<video>` 元素还没有挂载到 DOM（条件渲染延迟），`srcObject` 赋值就会失败。用 `opacity: 0` 可以保证元素始终在 DOM 中、始终可以接收流，只是视觉上不可见。

#### 技巧 2：`playsInline` 是移动端必需的

```tsx
<video
  autoPlay       // 所有平台: 收到流后自动播放
  playsInline    // iOS 专用: 不要全屏播放，在页面内播放
/>

// 如果没有 playsInline:
//   iOS Safari 会在播放视频时自动进入全屏模式
//   你的 UI 布局会被破坏
```

**为什么**：iOS Safari 默认会在播放视频时自动切换到全屏模式。加上 `playsInline` 属性告诉浏览器"我要在页面内播放"，这样 UI 布局才不会被破坏。

#### 技巧 3：音频用动态 `<audio>` 元素，而非 `<video>` 的音轨

```typescript
// 为什么不直接用 <video> 元素的音频？
// 因为 WebRTC 的 video track 和 audio track 是分开到达的
// 它们可能在不同的 MediaStream 中

// 视频: 绑定到已有的 <video> 元素
videoRef.current.srcObject = event.streams[0];

// 音频: 单独创建 <audio> 元素
const audio = document.createElement("audio");
audio.srcObject = event.streams[0];  // 这是音频的 stream，和视频的不同
audio.autoplay = true;
audio.style.display = "none";        // 隐藏，只要声音
document.body.appendChild(audio);    // 必须在 DOM 中才能播放
```

**为什么**：WebRTC 的视频轨道和音频轨道是分开到达的，它们可能属于不同的 `MediaStream`。如果把音频流也绑到 `<video>` 的 `srcObject` 上，可能会覆盖掉视频流。分开处理是最安全的做法。

#### 技巧 4：断开时必须彻底清理

```typescript
// use-avatar-stream.ts disconnect()
const disconnect = () => {
  // 1. 关闭 WebRTC 连接
  pcRef.current?.close();
  pcRef.current = null;

  // 2. 清除视频流绑定
  if (videoRef.current) {
    videoRef.current.srcObject = null;  // ← 必须设为 null
    // 如果不清除，<video> 会显示最后一帧冻结画面
  }

  // 3. 移除动态创建的音频元素
  if (audioElRef.current) {
    audioElRef.current.srcObject = null;
    audioElRef.current.remove();        // ← 从 DOM 中移除
    audioElRef.current = null;
    // 如果不移除，音频会继续播放（直到 GC 回收）
  }
};
```

**为什么**：如果不把 `srcObject` 设为 `null`，`<video>` 会冻结在最后一帧；如果不从 DOM 中移除 `<audio>` 元素，音频可能继续播放。彻底清理可以避免"幽灵"音视频和内存泄漏。

### 通用多媒体 UI 组件速查

不仅限于本项目，下面是浏览器中各类多媒体场景对应的 HTML 元素和数据绑定方式的速查表：

```
┌──────────────┬──────────────────────────────┬──────────────────────────┐
│ 媒体类型      │ HTML 元素                     │ 数据绑定方式              │
├──────────────┼──────────────────────────────┼──────────────────────────┤
│ 文件视频      │ <video src="url">            │ src 属性 = 文件 URL      │
│ (mp4/webm)   │                              │                          │
├──────────────┼──────────────────────────────┼──────────────────────────┤
│ 实时视频流    │ <video>                      │ el.srcObject = stream    │
│ (WebRTC)     │ + autoPlay playsInline       │ (MediaStream 对象)       │
├──────────────┼──────────────────────────────┼──────────────────────────┤
│ 文件音频      │ <audio src="url">            │ src 属性 = 文件 URL      │
│ (mp3/wav)    │                              │                          │
├──────────────┼──────────────────────────────┼──────────────────────────┤
│ 实时音频流    │ <audio>                      │ el.srcObject = stream    │
│ (WebRTC)     │ + autoplay, display:none     │ (MediaStream 对象)       │
├──────────────┼──────────────────────────────┼──────────────────────────┤
│ 麦克风采集    │ AudioContext + AudioWorklet   │ getUserMedia() 获取流    │
│ (用户语音)   │ （无可见 UI 元素）            │ 手动处理 PCM 数据        │
├──────────────┼──────────────────────────────┼──────────────────────────┤
│ 程序生成音频  │ AudioContext + AudioBuffer   │ decodeAudioData() 解码   │
│ (AI TTS回复) │ （无可见 UI 元素）            │ AudioBufferSourceNode 播放│
├──────────────┼──────────────────────────────┼──────────────────────────┤
│ 摄像头预览    │ <video>                      │ el.srcObject = stream    │
│              │ + autoPlay playsInline muted │ getUserMedia({video:true})│
└──────────────┴──────────────────────────────┴──────────────────────────┘
```

### 本项目中四种音频播放方式的对比

本项目中涉及四种不同的音频场景，它们的来源、播放方式和 UI 表现各不相同：

```
┌────────────────┬──────────────────┬────────────────────┬──────────────┐
│ 音频类型        │ 来源              │ 播放方式            │ UI 元素       │
├────────────────┼──────────────────┼────────────────────┼──────────────┤
│ 数字人口型音频  │ WebRTC Audio Track│ <audio>.srcObject  │ 隐藏 <audio> │
│                │ (Opus 编码)       │ 浏览器自动解码      │ display:none │
├────────────────┼──────────────────┼────────────────────┼──────────────┤
│ 纯语音AI回复   │ WebSocket JSON    │ AudioContext +     │ 无可见元素    │
│                │ response.audio.   │ AudioBuffer +      │ (程序化播放) │
│                │ delta (base64     │ AudioBufferSource  │              │
│                │ PCM16)            │ Node               │              │
├────────────────┼──────────────────┼────────────────────┼──────────────┤
│ 用户麦克风采集  │ getUserMedia()    │ AudioWorklet 处理  │ 无可见元素    │
│                │ 浏览器麦克风API    │ → Float32 → base64 │ (采集不播放) │
│                │                  │ → WebSocket 发送   │              │
├────────────────┼──────────────────┼────────────────────┼──────────────┤
│ UI 音效        │ 静态文件          │ new Audio("url")   │ 无可见元素    │
│ (按钮音等)     │ /public/*.mp3     │ .play()            │              │
└────────────────┴──────────────────┴────────────────────┴──────────────┘
```

### 渲染层小结

浏览器的 `<video>` 和 `<audio>` 标签就是流媒体的渲染组件，通过 `srcObject = mediaStream` 绑定实时流。记住以下关键技巧：

1. **标签始终在 DOM 中**，用 `opacity` 切换可见性（不用条件渲染或 `display:none`）。
2. **iOS 必须加 `playsInline`**，否则视频会被强制全屏。
3. **音频和视频分开绑定**，因为 WebRTC 的两种轨道可能在不同的 MediaStream 中。
4. **断开时彻底清理** `srcObject = null`，防止冻结画面和幽灵音频。

本项目中所有多媒体渲染都使用浏览器原生 API，零第三方播放器依赖。

---

> 返回 [文档目录](./00-index.md) | 相关：[09-websocket-webrtc-protocol.md](./09-websocket-webrtc-protocol.md) · [06-webrtc-avatar.md](./06-webrtc-avatar.md)
