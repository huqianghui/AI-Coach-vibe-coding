# 附录 — 术语表

<!-- merged from README/appendix/general-glossary.md, README/appendix/webrtc-glossary.md -->

> 返回 [文档目录](./00-index.md)

---

## 通用术语

以下是本手册中涉及的通用技术术语速查表。这些术语不局限于 WebRTC，而是整个 Voice Live + Avatar 技术栈中会反复出现的基础概念。

| 术语 | 解释 |
|------|------|
| **WebSocket** | 基于 TCP 的全双工通信协议，浏览器和服务器可以互相推送消息。用 `wss://` URL 连接。 |
| **WebRTC** | Web Real-Time Communication，浏览器原生的实时音视频通信技术。用 ICE/SDP 协商连接，无 URL。 |
| **PCM16** | 脉冲编码调制，16bit 采样深度，无压缩的原始音频格式。本项目中 WebSocket 音频用此格式。 |
| **Opus** | 一种高效音频压缩编码，WebRTC 默认使用。延迟低，压缩比高。 |
| **H.264** | 视频压缩标准。本项目中 WebRTC 传输数字人视频用此编码。 |
| **VAD** | Voice Activity Detection，语音活动检测。Azure 用它判断用户是否在说话，决定何时触发 AI 回复。 |
| **AudioWorklet** | 浏览器音频处理 API，在独立线程中采集麦克风数据。比旧的 ScriptProcessorNode 性能更好。 |
| **base64** | 一种将二进制数据（如音频字节）编码为纯文本字符串的方式，以便塞进 JSON 传输。 |
| **NAT** | Network Address Translation，网络地址转换。家庭/企业路由器把内网地址映射为公网地址的机制，是 WebRTC 需要 ICE 穿透的根本原因。 |
| **RTP/SRTP** | Real-time Transport Protocol，实时传输协议。WebRTC 用它在 UDP 上传输音视频帧。SRTP 是加密版本。 |
| **Hosted Agent** | 部署在 Azure AI Foundry 项目中的 Agent（区别于已废弃的 classic `asst_*` assistant 路径）。文本会话与语音会话（经 Voice Live）最终都路由到同一个 Hosted Agent。详见 [01-architecture.md](./01-architecture.md)。 |

---

## WebRTC 术语

> 用项目真实代码对照解释每个术语，看完就能读懂 `use-avatar-stream.ts` 的每一行。

### PC — PeerConnection（对等连接）

**全称**：`RTCPeerConnection`

**是什么**：WebRTC 的核心对象，代表浏览器和远端（Azure Avatar）之间的一条媒体通道。所有 WebRTC 操作都围绕它展开。

**类比**：如果 WebSocket 的 `ws` 对象是"一部电话"，那 PC 就是"一台视频会议终端"——功能更强，但设置更复杂。

**在代码中**：

```typescript
// use-avatar-stream.ts 第 21 行
const pcRef = useRef<RTCPeerConnection | null>(null);

// 第 41-44 行：创建 PC
const pc = new RTCPeerConnection({
  iceServers: iceServers,        // 告诉 PC："用这些 TURN/STUN 服务器来探路"
  bundlePolicy: "max-bundle",    // 尽量把音频和视频打包在一条通道里
});

// 第 176 行：保存引用
pcRef.current = pc;

// 第 211 行：关闭连接
pcRef.current.close();
```

**PC 的生命周期**：

```
创建 → 配置收发模式 → 生成 Offer → ICE 探路 → 交换 SDP → DTLS 握手 → 媒体流动 → 关闭
 new     addTransceiver  createOffer   gathering   exchange    handshake    ontrack     close()
```

---

### SDP — Session Description Protocol（会话描述协议）

**是什么**：一段纯文本，描述"我能收发什么格式的音视频"。WebRTC 连接双方各生成一份 SDP，交换后才能协商出共同支持的格式。

**类比**：两个人要一起吃饭，各自写一张"我能吃什么"的清单（SDP Offer 和 SDP Answer），交换后找到都能吃的菜（共同编码格式）。

**SDP 长什么样**（简化版）：

```
v=0
o=- 123456 2 IN IP4 0.0.0.0
s=-
t=0 0
m=video 9 UDP/TLS/RTP/SAVPF 96           ← 我要接收视频，用端口 9
a=rtpmap:96 H264/90000                    ← 视频编码：H.264
a=recvonly                                ← 我只收不发
m=audio 9 UDP/TLS/RTP/SAVPF 111          ← 我要接收音频
a=rtpmap:111 opus/48000/2                 ← 音频编码：Opus
a=recvonly                                ← 我只收不发
a=fingerprint:sha-256 4A:3B:2C:1D:...    ← 我的 DTLS 证书指纹（密码学身份）
a=candidate:1 1 udp 2122260223 192.168.1.100 54321 typ host  ← 我的网络地址（ICE candidate）
```

**Offer 和 Answer 的关系**：

```
浏览器生成 Offer: "我能收 H.264 视频 + Opus 音频，我的地址是 X，我的指纹是 Y"
     ↓ （通过 WebSocket 传给 Azure）
Azure 生成 Answer: "OK，我也支持 H.264 + Opus，我的地址是 Z，我的指纹是 W"
     ↓ （通过 WebSocket 传回浏览器）
双方达成一致 → 开始传输
```

**在代码中**：

```typescript
// use-avatar-stream.ts 第 151-152 行：生成 Offer
const offer = await pc.createOffer();       // 浏览器自动生成 SDP 文本
await pc.setLocalDescription(offer);        // "这是我的描述，我确认了"

// 第 98-103 行：编码后通过 WebSocket 发送
const encodedSdp = btoa(JSON.stringify({
  type: "offer",
  sdp: pc.localDescription.sdp              // SDP 纯文本内容
}));
// → 通过 voiceLive.send({ type: "session.avatar.connect", client_sdp: encodedSdp })

// 第 171-174 行：收到 Azure 的 Answer
await pc.setRemoteDescription({             // "这是对方的描述，我确认了"
  type: "answer",
  sdp: serverSdp                            // Azure 返回的 SDP 文本
});
// → 此刻双方都知道对方的能力，WebRTC 正式连通
```

---

### ICE — Interactive Connectivity Establishment（交互式连接建立）

**是什么**：WebRTC 用来解决"我怎么找到对方"的机制。因为浏览器和 Azure 之间可能隔着 NAT、防火墙、路由器，不能直接互通，ICE 会尝试多种路径找到能用的那条。

**类比**：你要寄一个包裹给对方，但不知道对方确切地址。ICE 就是同时派出多个快递员（candidate），走不同的路线（直送、转发），看谁先到。

**ICE 探路的三种方式**：

```
方式 1: Host Candidate（直连）
  你的电脑 ───────────── Azure
  "我的本地 IP 是 192.168.1.100:54321，你能直接连吗？"
  → 局域网内可能成功，公网上几乎不可能（被 NAT 挡住）

方式 2: Server Reflexive / srflx（STUN 探测）
  你的电脑 ──► STUN 服务器 ──► "你的公网 IP 是 203.0.113.5:12345"
  "我的公网 IP 是 203.0.113.5:12345，你能连吗？"
  → 对称 NAT 下可能失败

方式 3: Relay Candidate（TURN 中继）
  你的电脑 ──► TURN 服务器 ◄── Azure
  "我们都连到中继服务器，通过它转发"
  → 一定能成功，但延迟稍高
```

**ICE 的工作过程**：

```
pc.createOffer() 触发
  → ICE Agent 开始收集 candidate（候选地址）
  → 每找到一个 candidate → 触发 pc.onicecandidate 回调
  → 全部找完 → onicecandidate(null) 或 iceGatheringState = "complete"
  → 把所有 candidate 写入 SDP
  → 发给对方
```

**在代码中**：

```typescript
// use-avatar-stream.ts 第 88-110 行
pc.onicecandidate = (e) => {
  if (e.candidate) {
    // 每找到一个候选地址，打印日志
    console.debug("[AvatarStream] ICE candidate: %s %s",
      e.candidate.type,    // "host" / "srflx" / "relay"
      e.candidate.protocol // "udp" / "tcp"
    );
  }
  if (!e.candidate) {
    // null = 所有候选地址都收集完了
    // 现在可以把完整的 SDP（包含所有 candidate）发给 Azure
    resolve(encodedSdp);
  }
};

// 第 132-147 行：8 秒安全超时
// 有些网络环境下 null candidate 事件永远不触发，所以设超时兜底
setTimeout(() => {
  if (!offerSent) {
    console.warn("[AvatarStream] ICE gathering timeout (8s)");
    resolve(encodedSdp);  // 超时了就用已经收集到的 candidate 先发
  }
}, 8000);
```

**ICE 状态机**（可以在浏览器 DevTools 中观察 `pc.iceConnectionState`）：

```
new → checking → connected → completed
                     ↓
                  failed（所有路径都不通 → WebRTC 连接失败）
```

---

### STUN — Session Traversal Utilities for NAT

**是什么**：一个轻量协议，用来让浏览器知道"我在公网上的 IP 和端口是多少"。

**类比**：你在房间里不知道自己家的门牌号，打电话问邻居（STUN 服务器）："你看到我的来电显示是什么号码？"邻居告诉你："你的公网地址是 203.0.113.5:12345"。

**在代码中**：STUN 地址包含在 Azure 返回的 ICE servers 里：

```typescript
// use-voice-live.ts 收到 session.updated 后：
iceServers = [
  { urls: "stun:xxx.communication.azure.com:3478" },    // ← STUN 服务器
  { urls: "turn:xxx.communication.azure.com:3478",       // ← TURN 服务器
    username: "临时用户名", credential: "临时密码" }
]
```

STUN 只"问路"，不"带路"。如果问到的地址能直连，就不需要 TURN。

---

### TURN — Traversal Using Relays around NAT

**是什么**：当 STUN 发现的地址直连不通时（对称 NAT、严格防火墙），TURN 服务器作为"中继"，双方都把数据发给 TURN，由 TURN 转发。

**类比**：你和朋友都在各自小区里，保安不让外人进。你们约在一个咖啡馆（TURN 服务器）见面，所有东西都通过咖啡馆转交。

**和 STUN 的对比**：

```
STUN: "你的公网地址是 X" → 双方尝试直连
  ✅ 快（直连），免费
  ❌ 穿不透对称 NAT 或严格防火墙

TURN: "把数据发给我，我帮你转发" → 中继模式
  ✅ 一定能通（没有穿透问题）
  ❌ 稍慢（多一跳），消耗中继服务器带宽
```

**为什么 TURN 需要用户名和密码**：因为 TURN 服务器帮你转发流量要花带宽和计算资源，所以需要认证，防止被滥用。Azure 为每个 Voice Live session 动态生成临时 TURN 凭据。

**在代码中**：

```typescript
// use-voice-live.ts 第 152-175 行
const sessionUsername = avatarResp?.username || avatarResp?.ice_username;
const sessionCredential = avatarResp?.credential || avatarResp?.ice_credential;

// 凭据应用到所有 ICE server
servers.map(s => ({
  urls: s.urls,
  username: sessionUsername || s.username,       // ← TURN 用户名（临时）
  credential: sessionCredential || s.credential, // ← TURN 密码（临时）
}));
```

---

### DTLS — Datagram Transport Layer Security

**是什么**：WebRTC 的加密层，相当于 UDP 版本的 TLS（HTTPS 用的就是 TLS）。保证媒体流是加密的，且能验证对方身份。

**类比**：DTLS 就像给视频通话加了一把锁。即使数据经过 TURN 中继，中继服务器也只能看到加密后的乱码，不能偷看视频内容。

**DTLS 指纹 = 密码学身份证**：

```
SDP 中的这行：
  a=fingerprint:sha-256 4A:3B:2C:1D:EF:...

含义：
  "我的 DTLS 证书的 SHA-256 哈希是 4A:3B:2C:1D:EF:..."
  "如果你在 DTLS 握手时发现我的证书指纹不是这个，说明我是假冒的，请拒绝连接"
```

这就是前面章节中提到的"怎么保证 WebRTC 客户端就是 WebSocket 认证的那个客户端"的密码学机制。

---

### Offer / Answer（提议 / 应答）

**是什么**：SDP 交换的两个角色。发起方（浏览器）生成 Offer，接收方（Azure）生成 Answer。

**在代码中**：

```typescript
// Offer: 浏览器说"我要什么"
const offer = await pc.createOffer();          // 自动生成
await pc.setLocalDescription(offer);           // 确认

// Answer: Azure 说"我能给什么"
await pc.setRemoteDescription({                // 设置对方的应答
  type: "answer", sdp: serverSdp
});
```

**规则**：
- 一次连接只有一对 Offer/Answer
- 必须先 Offer 后 Answer（不能反过来）
- Offer 方先 `setLocalDescription(offer)`，再发给对方
- Answer 方先 `setRemoteDescription(offer)`，再 `setLocalDescription(answer)`
- 在本项目中，浏览器是 Offer 方，Azure Avatar 是 Answer 方

---

### Transceiver（收发器）

**是什么**：PC 上的"一个轨道口"，决定这个口是发视频、收音频、还是双向。

**在代码中**：

```typescript
// use-avatar-stream.ts 第 80-81 行
pc.addTransceiver("video", { direction: "recvonly" });  // 加一个视频口，只收
pc.addTransceiver("audio", { direction: "recvonly" });  // 加一个音频口，只收
```

**direction 的四种模式**：

```
"sendrecv"  — 又发又收（视频通话标配）
"sendonly"  — 只发不收（直播推流）
"recvonly"  — 只收不发（本项目！只看数字人，不传自己的画面）
"inactive"  — 既不发也不收（暂停）
```

为什么是 `recvonly`？因为用户的语音通过 WebSocket 发送（base64 PCM16），不走 WebRTC 上传。WebRTC 在本项目中只负责从 Azure 接收数字人的视频和音频。

---

### Track（轨道）和 MediaStream（媒体流）

**是什么**：
- **Track** = 一条单独的音频或视频数据流
- **MediaStream** = 一个或多个 Track 的容器

**类比**：Track 是"一根水管"（视频管或音频管），MediaStream 是"一组水管的接口"。

**在代码中**：

```typescript
// use-avatar-stream.ts 第 47-76 行
pc.ontrack = (event) => {
  // 每收到一个 Track 触发一次

  if (event.track.kind === "video") {
    // 视频轨道 → 绑定到 <video> 元素
    videoElement.srcObject = event.streams[0];  // streams[0] 是包含此 track 的 MediaStream
    videoElement.play();
  }

  if (event.track.kind === "audio") {
    // 音频轨道 → 创建隐藏的 <audio> 元素
    const audio = document.createElement("audio");
    audio.srcObject = event.streams[0];
    audio.autoplay = true;
    audio.style.display = "none";
    document.body.appendChild(audio);           // 必须加到 DOM 里，某些浏览器才播放
  }
};
```

在本项目中，Azure Avatar 通过 WebRTC 推送 2 个 Track：
1. **Video Track**：H.264 编码的数字人视频（面部表情、口型、身体动作）
2. **Audio Track**：Opus 编码的数字人语音（与口型同步）

---

### Candidate（候选地址）

**是什么**：ICE 探测到的"我可以通过这个地址被联系到"的信息。一个 PC 通常会收集多个 candidate。

**三种类型**：

```
host     — 本地直接地址 (192.168.1.100:54321)
           "这是我在局域网的地址"

srflx    — STUN 探测到的公网地址 (203.0.113.5:12345)
           "这是 NAT 外面看到的我的地址"

relay    — TURN 中继地址 (turn-server.azure.com:3478)
           "如果其他地址都连不上，通过这个中继找我"
```

**在代码中**：

```typescript
// use-avatar-stream.ts 第 88-94 行
pc.onicecandidate = (e) => {
  if (e.candidate) {
    console.debug("[AvatarStream] ICE candidate: %s %s",
      e.candidate.type,     // "host", "srflx", or "relay"
      e.candidate.protocol  // "udp" or "tcp"
    );
  }
  // e.candidate === null 表示收集结束
};
```

---

### bundlePolicy（打包策略）

**在代码中**：

```typescript
const pc = new RTCPeerConnection({
  iceServers: ...,
  bundlePolicy: "max-bundle",   // ← 这个
});
```

**含义**：尽量把所有媒体（视频 + 音频）打包到一条网络连接上，而不是每种媒体单独建连接。

```
"max-bundle":  视频 + 音频 → 一条 UDP 连接      ✅ 更快，candidate 更少
"balanced":    每种媒体可能单独一条连接
"max-compat":  完全分开，每种媒体独立连接         ❌ candidate 多，协商慢
```

本项目用 `max-bundle` 是因为我们只有一路视频 + 一路音频，打包在一起最高效。
