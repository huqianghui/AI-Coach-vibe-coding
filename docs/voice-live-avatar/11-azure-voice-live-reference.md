# 11 — Azure Voice Live API 参考

<!-- merged from README/05-azure-voice-live/README.md -->

> 返回 [文档目录](./00-index.md)

---

在前几章中，我们已经理解了 WebSocket 与 WebRTC 的分工、WebRTC 的信令与媒体机制，以及 NAT 穿透的核心原理（见 [09-websocket-webrtc-protocol.md](./09-websocket-webrtc-protocol.md)、[10-nat-traversal.md](./10-nat-traversal.md)）。本章将这些知识聚焦到 Azure Voice Live API 的实际架构上，逐一拆解安全模型、常见故障、地址体系、通信全景和 TURN 中继的引入流程。读完本章，你将对"浏览器 -- 后端 -- Azure 云"之间的每一条通信链路了然于胸。

> **架构前提**：自 D-05/D-06/D-08/D-09 落地后，Voice Live 会话不再使用独立的 `model` 参数直连模型，而是通过 `agent_name=` / `project_name=` 连接到 Azure AI Foundry 中的 Hosted Agent（与文本会话共享同一个 Agent）。详见 [01-architecture.md](./01-architecture.md) 的双路径架构一节。

---

## 目录

- [11.1 安全架构：为什么 WebRTC 直连 Azure](#111-安全架构为什么-webrtc-直连-azure)
- [11.2 常见故障：只有文字没有音频的根因分析](#112-常见故障只有文字没有音频的根因分析)
- [11.3 Endpoint 与地址体系](#113-endpoint-与地址体系)
- [11.4 完整通信架构全景图](#114-完整通信架构全景图)
- [11.5 TURN 中继器在 Voice Live 中的引入流程](#115-turn-中继器在-voice-live-中的引入流程)
- [11.6 Realtime 模型的音频去哪了？—— 延迟真相与加速方案](#116-realtime-模型的音频去哪了-延迟真相与加速方案)

---

## 11.1 安全架构：为什么 WebRTC 直连 Azure

在 Azure Voice Live 架构中，WebSocket 消息走后端代理，而 WebRTC 媒体流由浏览器直连 Azure。这不是一个"性能优化"的偏好选择，而是由技术限制决定的。同时，安全性通过"临时凭据"机制得到了充分保障。

### 11.1.1 为什么不能走后端代理？

```
                         能不能代理？
WebSocket（文字+音频数据）    可以，且必须代理（保护 API Key/Entra 凭据）
WebRTC（视频+音频流）         不能，技术上走不通
```

原因不是"性能差一点"，而是**根本做不到**：

| 原因 | 详细说明 |
|------|----------|
| **协议不兼容** | WebRTC 用的是 SRTP/DTLS over **UDP**。FastAPI/Python 是 TCP-based 的 Web 服务器，压根不支持 UDP 媒体传输。你需要一个专门的 WebRTC 媒体服务器（如 Janus/mediasoup）才能代理 WebRTC 流。 |
| **带宽爆炸** | H.264 视频流 30fps 约 2-5 Mbps。如果每个用户的视频都经过后端转发，10 个并发用户 = 20-50 Mbps 的后端带宽。这不是优化问题，是成本和架构问题。 |
| **延迟不可接受** | WebRTC 的设计目标是 < 100ms 延迟。加一个 TCP proxy 约增加 100-300ms（TCP 重传+缓冲+解码/编码）。对于口型同步来说，300ms 延迟 = 嘴型和声音明显不同步。 |
| **WebRTC 本身就是 P2P** | WebRTC 的核心设计就是浏览器直连对端。Azure Avatar 服务本质上扮演了 WebRTC 的"对端"角色，与浏览器直接建立媒体通道。 |

> **类比**：WebSocket 代理就像"翻译官"——你说中文，翻译官转述给外国人，外国人回复，翻译官再转述给你。WebRTC 如果要代理，就像"让翻译官同时转播一场高清视频直播"——他不是干这个的，硬要他做只会卡顿和延迟。

### 11.1.2 安全怎么保证？API Key/Entra 凭据不是暴露了吗？

**认证凭据绝对没有暴露。WebRTC 连接用的是临时凭据，不是 API Key/Entra Token。**

安全链路如下：

```
                                     谁知道什么？

浏览器：                              不知道 API Key / Entra 凭据
                                      知道 JWT Token（登录凭证）
                                      知道 临时 TURN 凭据（Azure 动态生成，有效期几分钟）

后端 (FastAPI)：                      知道 API Key 或 Entra Token（环境变量/托管身份，绝不外传）
                                      验证 JWT，代理 WebSocket

Azure Voice Live API：                知道 API Key/Entra 凭据（后端提交的）
                                      生成临时 TURN 凭据 -> 通过 WebSocket -> 传给浏览器
                                      TURN 服务器验证临时凭据
```

### 11.1.3 认证流程详解

```
Step 1: 浏览器用 JWT 连接后端 WebSocket
        -> 后端验证 JWT，确认用户身份
        -> 后端用 API Key/Entra 凭据连接 Azure Voice Live SDK
        -> 该凭据只在后端内存中，浏览器永远看不到

Step 2: Azure 创建会话，返回 session.updated 事件
        -> 事件中包含临时 TURN 凭据：
          {
            ice_servers: [
              {
                urls: "turn:xxx.communication.azure.com:3478",
                username: "临时用户名（几分钟后过期）",
                credential: "临时密码（几分钟后过期）"
              }
            ]
          }
        -> 这些凭据通过已认证的 WebSocket 传给浏览器

Step 3: 浏览器用临时凭据连接 TURN 服务器
        -> TURN 服务器验证凭据有效性
        -> 凭据有效 -> 允许 WebRTC 媒体流通过
        -> 凭据过期/无效 -> 拒绝连接
```

### 11.1.4 安全保障总结

| 安全问题 | 如何保障 |
|----------|---------|
| API Key/Entra 凭据泄露？ | 不可能。凭据只在后端（Python 进程内存/托管身份），从不经过网络传给浏览器。 |
| TURN 凭据被窃取？ | 影响有限。凭据是临时的（几分钟过期），且绑定特定 TURN 服务器和会话。 |
| 有人伪造 WebRTC 连接？ | 做不到。需要有效的 TURN 凭据 + 匹配的 SDP 交换，而 SDP 交换走的是已认证的 WebSocket。 |
| 中间人攻击？ | WebRTC 自带 DTLS 加密（类似 HTTPS），媒体流端到端加密。 |

> **一句话总结**：认证凭据被后端保护，WebRTC 用 Azure 动态颁发的"临时通行证"（TURN 凭据）来认证，通行证几分钟就过期，安全性有充分保障。

---

## 11.2 常见故障：只有文字没有音频的根因分析

在调试 Voice Live + Avatar 时，一个高频出现的现象是：文字转写正常显示，但没有音频输出，数字人的嘴型也不动。这几乎可以确定是 **WebRTC 没有建立成功**。

### 11.2.1 症状与通道对照

结合前面章节的结论（WebSocket 和 WebRTC 是两条独立通道），症状可以精确解释：

| 症状 | 走哪条通道 | 说明 |
|------|-----------|------|
| 文字转写正常 | WebSocket | WebSocket 连接正常，`transcript.delta` 消息正常到达 |
| 没有音频输出 | WebRTC（Avatar 模式） | 数字人的语音通过 WebRTC Audio Track 传输，WebRTC 没连上就没有声音 |
| 数字人嘴型不动 | WebRTC | 嘴型是 WebRTC Video Track 里的内容，没连上就没有画面变化 |

### 11.2.2 WebRTC 可能失败的环节

WebRTC 的建立是一个多步骤的过程，任何一步失败都会导致上述症状：

```
Step  可能的失败点                           如何排查
----------------------------------------------------------------------
 1    session.updated 里没有 ice_servers      检查 WebSocket 消息日志，
      -> 说明 Azure 没返回 ICE 配置             确认 session.updated 内容

 2    ICE servers 格式不对或凭据过期          检查 ice_servers 数组是否有
      -> RTCPeerConnection 无法初始化           username/credential 字段

 3    ICE gathering 超时（>8秒）              网络环境问题（防火墙/NAT），
      -> 本地 SDP Offer 不完整                  检查 iceGatheringState

 4    SDP Offer 发送失败                      检查 session.avatar.connect
      -> Azure 没收到协商请求                    消息是否成功发送

 5    SDP Answer 超时（>15秒）                Azure Avatar 服务不可用，
      -> 协商未完成                              或 SDP 编码格式不对

 6    setRemoteDescription 失败               SDP Answer 解码失败
      -> WebRTC 连接无法建立                     (base64 -> JSON 解析出错)

 7    ICE connectivity check 失败             TURN 服务器不可达，
      -> 有 SDP 但媒体流走不通                   企业防火墙拦截 UDP
```

### 11.2.3 快速诊断方法

打开浏览器控制台（F12），关注以下日志：

1. **检查 WebSocket 消息**：找到 `session.updated` 事件，确认里面有 `ice_servers` 字段
2. **检查 WebRTC 状态**：搜索 `RTCPeerConnection` 相关日志，看 `iceConnectionState` 是否变为 `connected`
3. **检查 SDP 交换**：确认 `session.avatar.connect` 消息已发送，且收到了包含 `server_sdp` 的响应

判断逻辑如下：

- 如果第 1 步就没有 `ice_servers`，问题在 Azure 配置端（Avatar 功能可能未启用或模型不支持）。
- 如果第 1 步正常但第 2 步 ICE 状态卡在 `checking` 或 `failed`，问题在网络环境（防火墙/NAT 穿越失败）。

更完整的三层日志体系和决策树，见 [14-production-operations.md](./14-production-operations.md)。

### 11.2.4 理解确认

> 理解了 WebSocket 和 WebRTC 是两条独立通道之后，这个故障就很好理解了：
>
> - **文字能出来** = WebSocket 通道正常工作
> - **音频出不来 + 嘴型不动** = WebRTC 通道没有建立
>
> 这两个现象完全吻合"WebSocket 正常但 WebRTC 断开"的场景。修复方向就是排查 WebRTC 建立过程中哪一步失败了。

---

## 11.3 Endpoint 与地址体系

Azure Voice Live 通信中到底涉及几个 endpoint？WebRTC 的地址是什么形式？答案是：一共涉及 **5 个地址**，但只有 **1 个**是你配置的（Azure AI Foundry endpoint）。其余都是 Azure 动态提供的。WebRTC 没有 URL，它的"地址"是 ICE candidate——IP:port 组合，藏在 SDP 文本里。

### 11.3.1 完整地址清单

```
+----- +------------------------------------+------------+----------------------+
| #    | 地址                               | 协议        | 谁提供/谁配置        |
+------+------------------------------------+------------+----------------------+
| 1    | wss://your-backend/api/v1/         | WebSocket  | 你配置（后端地址）    |
|      |   voice-live/ws?token=JWT          | (TCP)      |                      |
+------+------------------------------------+------------+----------------------+
| 2    | https://your-project.services.     | HTTPS ->   | 你配置（Azure endpoint|
|      |   ai.azure.com                     | SDK 内部   | + API Key/Entra）     |
|      |                                    | 转 WS      |                      |
+------+------------------------------------+------------+----------------------+
| 3    | stun:relay1.communication.         | STUN       | Azure 动态返回        |
|      |   azure.com:3478                   | (UDP)      | （session.updated）   |
+------+------------------------------------+------------+----------------------+
| 4    | turn:relay1.communication.         | TURN       | Azure 动态返回        |
|      |   azure.com:3478                   | (UDP/TCP/  | + 临时凭据            |
|      |                                    |  TLS)      |                      |
+------+------------------------------------+------------+----------------------+
| 5    | 203.0.113.50:49170                 | SRTP/DTLS  | ICE 协商动态发现      |
|      | （Azure Avatar 的实际 IP:port，    | (UDP)      | 嵌在 SDP 中           |
|      |   每次连接都不同）                  |            | 你永远不会直接看到    |
+------+------------------------------------+------------+----------------------+
```

你配置的 vs Azure 动态提供的：

```
你配置的（写在代码/环境变量里的，1个）：
  Azure AI Foundry endpoint: https://your-project.services.ai.azure.com
  -> 后端 Python SDK 用这一个地址搞定一切

Azure 动态返回的（运行时自动下发的，4个）：
  (1) STUN 服务器地址（探路用）
  (2) TURN 服务器地址（中继用）
  (3) Azure Avatar 的 ICE candidates（WebRTC 对端地址）
  (4) Azure Avatar 的 SDP（媒体能力描述）

  -> 这些都不需要你配置，Azure 在 session.updated 事件中自动下发
```

### 11.3.2 WebRTC 的"地址"长什么样？

**WebRTC 没有 URL，它的地址是 SDP 文本里的 candidate 行：**

```
WebSocket 的地址：
  wss://your-backend.com/api/v1/voice-live/ws?token=xxx
  ^ 一个完整的 URL，人类可读，你写在代码里

WebRTC 的地址：
  不是 URL！而是 SDP 文本里的 candidate 行：

  a=candidate:1 1 udp 2122260223 192.168.1.100 54321 typ host
  a=candidate:2 1 udp 1686052607 203.0.113.5 12345 typ srflx raddr 192.168.1.100 rport 54321
  a=candidate:3 1 udp 41885695 52.176.xxx.xxx 3478 typ relay raddr 203.0.113.5 rport 12345

  ^ 这是机器协商出来的，你不会手写这些，浏览器自动生成
```

SDP candidate 各字段拆解：

```
a=candidate:3 1 udp 41885695 52.176.xxx.xxx 3478 typ relay
             |  |  |     |        |           |       |
             |  |  |     |        |           |       +- 类型: relay(TURN中继)
             |  |  |     |        |           +- 端口: 3478
             |  |  |     |        +- IP: 52.176.xxx.xxx (TURN 服务器的公网IP)
             |  |  |     +- 优先级: 41885695 (relay 优先级最低)
             |  |  +- 协议: UDP
             |  +- 组件: 1 (RTP)
             +- candidate 编号

对比三种 candidate 的优先级：
  host (直连)  : 优先级 2122260223  <- 最高，首选
  srflx (STUN) : 优先级 1686052607  <- 中等
  relay (TURN)  : 优先级 41885695   <- 最低，兜底

  ICE 会从高优先级开始尝试，都不行才用 relay
```

### 11.3.3 WebRTC 的通信形式 vs WebSocket 的通信形式

```
WebSocket 通信形式：
  +---------------------------------------------+
  | 请求: ws.send(JSON.stringify({              |
  |   type: "input_audio_buffer.append",        |
  |   audio: "base64编码的音频..."               |
  | }))                                         |
  |                                             |
  | 响应: ws.onmessage -> JSON 解析              |
  | { type: "response.audio_transcript.delta",  |
  |   delta: "你好..." }                         |
  |                                             |
  | 格式: JSON 文本帧 / 二进制帧                  |
  | 传输: TCP 有序可靠                            |
  | 控制: 你发什么，对方就收什么                   |
  +---------------------------------------------+

WebRTC 通信形式：
  +---------------------------------------------+
  | 没有"发送"和"接收"API！                       |
  |                                             |
  | 连接建立后，媒体流自动流动：                   |
  |   pc.ontrack = (event) => {                 |
  |     video.srcObject = event.streams[0];     |
  |   }                                         |
  |   // 视频帧自动解码、自动渲染到 <video> 标签   |
  |   // 你不需要手动"读取"每一帧                  |
  |                                             |
  | 格式: RTP 包（20-1400 字节的 UDP 数据报）     |
  |       每个包 = RTP头(12字节) + 载荷(编码数据)  |
  | 传输: UDP 无序可丢包                          |
  | 控制: 浏览器+操作系统自动处理，你碰不到原始包  |
  +---------------------------------------------+
```

### 11.3.4 RTP 包内部结构

以下内容了解即可，你永远不会直接操作这些数据包：

```
+----------------------------------------------+
|              一个 RTP 视频包                   |
+----------------------------------------------+
| UDP 头 (8 bytes)                              |
|   src port: 49170, dst port: 54321            |
+----------------------------------------------+
| DTLS 加密层                                   |
|   (整个 RTP 包被 SRTP 加密，中间人看到乱码)    |
+----------------------------------------------+
| RTP 头 (12 bytes)                             |
|   版本: 2                                     |
|   载荷类型: 96 (H.264)                        |
|   序列号: 34521 (用于排序和检测丢包)            |
|   时间戳: 5765400 (用于音视频同步)              |
|   SSRC: 0x1A2B3C4D (流的唯一标识)              |
+----------------------------------------------+
| H.264 载荷 (~1000 bytes)                      |
|   一个视频帧的一部分（大帧会分成多个 RTP 包）   |
+----------------------------------------------+

浏览器收到后：
  -> SRTP 解密
  -> RTP 头解析（排序、丢包检测）
  -> H.264 载荷送入硬件解码器
  -> 解码后的帧渲染到 <video> 元素
  -> 全自动，你的 JS 代码完全不介入
```

---

## 11.4 完整通信架构全景图

把前面所有内容汇总，以下是 Azure Voice Live 完整通信架构的全景图：

```
+------------------------------------------------------------------------+
|                    Azure Voice Live 完整通信架构                        |
+------------------------------------------------------------------------+
|                                                                        |
|  浏览器                 后端 FastAPI              Azure Cloud           |
|  +------+              +----------+              +--------------+      |
|  |      |---- (1) ---->|          |---- (2) ---->| Voice Live   |      |
|  |      |  WebSocket   |          |  Python SDK  | API          |      |
|  |      |  wss://后端   |          |  https://    |              |      |
|  |      |  /api/v1/    |          |  foundry     | -> Hosted    |      |
|  |      |  voice-live  |          |  endpoint    |    Agent     |      |
|  |      |  /ws         |          |              |    (STT+LLM+ |      |
|  |      |<-------------|<---------|<-------------|     TTS)     |      |
|  |      |  JSON 文本    |  SDK 事件 |  session.*   |              |      |
|  |      |  + base64音频 |          |  response.*  |              |      |
|  |      |              |          |              +------+-------+      |
|  |      |              +----------+                     |              |
|  |      |                                               |              |
|  |      |           session.updated 包含：               |              |
|  |      |<----------  (3) STUN 地址 --------------------+              |
|  |      |<----------  (4) TURN 地址 + 临时凭据                         |
|  |      |<----------  SDP Answer (含 (5) Azure 的 ICE candidates)     |
|  |      |                                                              |
|  |      |              +--------------------------------+              |
|  |      |=== (5) =====>|        Azure Avatar 服务        |              |
|  |      |  WebRTC      |  IP:port 由 ICE 协商动态决定    |              |
|  |      |  SRTP/DTLS   |  不是一个固定 URL               |              |
|  |      |  over UDP    |  可能直连，也可能经 (4) TURN 中继|              |
|  |      |<=============|  H.264 视频 + Opus 音频         |              |
|  |      |              +--------------------------------+              |
|  +------+                                                              |
|                                                                        |
|  地址总结：                                                             |
|  (1) wss://your-backend/api/v1/voice-live/ws   （你配置）              |
|  (2) https://xxx.services.ai.azure.com         （你配置）              |
|  (3) stun:relay1.communication.azure.com:3478  （Azure 返回）         |
|  (4) turn:relay1.communication.azure.com:3478  （Azure 返回 + 临时凭据）|
|  (5) 动态 IP:port（ICE 协商，嵌在 SDP candidate 中）                  |
|                                                                        |
+------------------------------------------------------------------------+
```

> **总结**：你只需配置 1 个地址（Azure AI Foundry endpoint），Azure 会在运行时动态下发 STUN/TURN 服务器地址和 WebRTC 所需的 ICE candidates。WebRTC 没有 URL——它的"地址"是嵌在 SDP 文本中的 IP:port 组合，由 ICE 协商自动发现，每次连接都可能不同。WebRTC 的通信是 RTP 包在 UDP 上流动，浏览器自动处理编解码和渲染，你的 JS 代码只需绑定 `<video>` 元素即可。上图中的 "Voice Live API" 最终路由到同一个 Hosted Agent（与文本会话共享），细节见 [01-architecture.md](./01-architecture.md) 的双路径架构。

---

## 11.5 TURN 中继器在 Voice Live 中的引入流程

中继器（TURN）的引入是全自动的，它是 ICE 框架的一部分，你不需要手动决定"要不要用中继器"——ICE 会自动探测并选择最优路径。

### 11.5.1 准备阶段：获取 TURN 凭据

准备阶段在 WebSocket 信令通道上完成：

```
+-----------------------------------------------------------------------+
| 准备阶段：获取 TURN 凭据（在 WebSocket 信令通道上完成）                  |
+-----------------------------------------------------------------------+
|                                                                       |
|  Step 1: 后端用 API Key/Entra 凭据连接 Azure Voice Live SDK           |
|    backend -> Azure: azure.ai.voicelive.aio.connect(                  |
|                         endpoint=endpoint,                            |
|                         credential=credential,                        |
|                         agent_name=agent_name,                        |
|                         project_name=project_name,                    |
|                         avatar_config=AvatarConfig(...))               |
|    （SDK 1.3.0 GA 起，agent_name=/project_name= 为扁平化 kwargs，      |
|     取代旧版 AgentSessionConfig/agent_config 嵌套 dict）              |
|                                                                       |
|  Step 2: Azure 创建 session，返回 session.updated 事件                |
|    Azure -> backend -> 浏览器:                                        |
|    {                                                                  |
|      type: "session.updated",                                         |
|      session: {                                                       |
|        avatar: {                                                      |
|          ice_servers: [                                                |
|            {                                                          |
|              urls: "turn:relay1.communication.azure.com:3478",         |
|              username: "临时用户名",     <- TURN 凭据                  |
|              credential: "临时密码"      <- 几分钟后过期               |
|            },                                                         |
|            {                                                          |
|              urls: "stun:relay1.communication.azure.com:3478"          |
|            }                                                          |
|          ]                                                            |
|        }                                                              |
|      }                                                                |
|    }                                                                  |
|                                                                       |
|  -> 至此，浏览器拿到了 TURN/STUN 服务器地址和临时凭据                 |
|  -> 注意：这一步不是"请求中继器"，而是 Azure 主动下发配置             |
|                                                                       |
+-----------------------------------------------------------------------+
```

### 11.5.2 运行阶段：ICE 自动探路

运行阶段由浏览器的 ICE Agent 自动完成，决定是否使用 TURN 中继：

```
+-----------------------------------------------------------------------+
| 运行阶段：ICE 自动探路，决定是否使用 TURN 中继                          |
+-----------------------------------------------------------------------+
|                                                                       |
|  Step 3: 浏览器创建 RTCPeerConnection，传入 ICE servers               |
|    const pc = new RTCPeerConnection({                                 |
|      iceServers: [                                                    |
|        { urls: "turn:...", username: "...", credential: "..." },       |
|        { urls: "stun:..." }                                           |
|      ]                                                                |
|    });                                                                |
|                                                                       |
|  Step 4: 浏览器调用 createOffer()，触发 ICE gathering                  |
|    -> 浏览器的 ICE Agent 同时探测三种路径：                            |
|                                                                       |
|    +--- host candidate ------ 本地 IP 直连（很可能失败）               |
|    +--- srflx candidate ---- 通过 STUN 探测公网地址，尝试 NAT 穿透    |
|    +--- relay candidate ---- 连接 TURN 服务器，用凭据认证，分配中继地址|
|                                                                       |
|  Step 5: TURN 分配中继地址                                            |
|    浏览器 -> TURN: Allocate Request (带凭据)                          |
|    TURN -> 浏览器: Allocate Response (relay address = TURN-IP:port)   |
|                                                                       |
|  Step 6: 所有 candidate 收集完毕，打包进 SDP Offer                    |
|    SDP 内容：                                                         |
|    a=candidate:1 1 udp 2122260223 192.168.1.100 54321 typ host       |
|    a=candidate:2 1 udp 1686052607 203.0.113.5 12345 typ srflx        |
|    a=candidate:3 1 udp 41885695 TURN-IP 5000 typ relay               |
|                                                                       |
|  Step 7: SDP 交换通过 WebSocket 完成                                  |
|    浏览器 -> (WebSocket) -> 后端 -> (SDK) -> Azure:                   |
|      session.avatar.connect { client_sdp: base64(offer) }            |
|    Azure -> (SDK) -> 后端 -> (WebSocket) -> 浏览器:                   |
|      { server_sdp: base64(answer) }                                  |
|                                                                       |
|  Step 8: ICE connectivity check（连通性检测）                          |
|    -> ICE 按优先级依次尝试每对 candidate pair：                       |
|                                                                       |
|    尝试 1: host <-> host (直连)                                       |
|      -> 大概率失败（跨网络/NAT/防火墙）                               |
|    尝试 2: srflx <-> srflx (STUN 穿透)                                |
|      -> 对称 NAT 下会失败                                            |
|    尝试 3: relay <-> relay (TURN 中继)                                |
|      -> 通过中继地址通信，一定成功                                    |
|                                                                       |
|  Step 9: ICE 选定最优路径                                             |
|    -> 如果直连成功 -> 用直连（延迟最低）                              |
|    -> 如果只有 TURN 成功 -> 用 TURN 中继（兜底）                     |
|    -> iceConnectionState: "connected"                                 |
|                                                                       |
|  Step 10: DTLS 握手 + 媒体流开始                                     |
|    -> 无论是直连还是中继，都要走 DTLS 加密                            |
|    -> H.264 视频 + Opus 音频开始流动                                  |
|                                                                       |
+-----------------------------------------------------------------------+
```

### 11.5.3 关键理解

| 问题 | 答案 |
|------|------|
| 中继器是我主动请求的吗？ | 不是。ICE 自动探路，自动决定是否使用 TURN 中继 |
| TURN 凭据从哪来？ | Azure 在 `session.updated` 中主动下发，不需要你单独请求 |
| 什么时候真正用上 TURN？ | 只有当直连和 STUN 穿透都失败时，ICE 才降级到 TURN |
| 用 TURN 需要改代码吗？ | 不需要！把 ICE servers 传给 `RTCPeerConnection` 就行，剩下全自动 |
| 企业防火墙下一定走 TURN？ | 大概率。严格防火墙封 UDP，STUN 穿透失败，ICE 自动选 TURN |

> **一句话**：TURN 中继器的引入是"声明式"的——你告诉 WebRTC "这里有个 TURN 可以用"（通过 iceServers 配置），ICE 自动决定要不要用。你不需要写任何"连接 TURN"的代码。

---

## 11.6 Realtime 模型的音频去哪了？—— 延迟真相与加速方案

很多开发者在选型时会有这样的预期："用 `gpt-4o-realtime` 这类 realtime 模型，它能同时输出文本和音频，响应应该比传统的 `文本 → LLM → TTS` 方案快很多吧？"

**答案是：在 Voice Live API 中，没有快多少。** 理解这一点，对于正确设定客户的性能预期至关重要。

### 11.6.1 Realtime 模型的音频被丢弃了

这是一个容易被忽略的关键事实：在 Voice Live API 的管线中，realtime 模型生成的音频模态**被丢弃**，只取文本输出：

```
┌─────────────── Voice Live API 内部编排 ───────────────────┐
│                                                            │
│  用户语音                                                   │
│     │                                                      │
│     ▼                                                      │
│  realtime model (gpt-4o-realtime, 经 Hosted Agent 编排)     │
│     │                                                      │
│     ├── text output  ──→ ✅ 被使用 ──→ Azure Speech Service │
│     │                                        │             │
│     └── audio output ──→ ❌ 被丢弃            │             │
│                                        ┌─────┴─────┐      │
│                                        ▼           ▼      │
│                                   TTS 音频    Viseme 数据   │
│                                   (给用户听)  (驱动唇形)    │
└────────────────────────────────────────────────────────────┘
```

### 11.6.2 为什么要丢弃？三个原因

| 原因 | 说明 |
|------|------|
| **Avatar 需要 Viseme** | 数字人的唇形动画需要音素级别的 viseme 时间轴数据。只有 Azure Speech Service 能产出 viseme 流，realtime 模型的原生音频不包含这个数据。**这是最根本的原因。** |
| **声音品质与一致性** | `speech_out` 配置中的 `voice_name`（如 `zh-CN-XiaoxiaoMultilingualNeural`）走的是 Azure 精调过的神经语音模型，音色、韵律、情感表达远优于 realtime 模型的内置合成语音 |
| **语音风格可控** | 可以配置 `style`（cheerful / professional）、`pitch`、`rate` 等参数，实现不同 HCP 角色的差异化声音。realtime 模型的原生音频不支持这种细粒度控制 |

> **类比**：就像餐厅的主厨（realtime 模型）顺手做了一份沙拉（音频），但甜品师（Azure Speech Service）做出来的更精致，而且只有甜品师能在盘子上画出客户要求的花纹（viseme）。所以主厨的沙拉只好倒掉。

### 11.6.3 延迟对比：到底差多少？

#### 带 Avatar（数字人）模式 —— Voice Live API

```
传统方案（非 realtime 模型）:
  用户说话 ──→ 独立ASR ──→ 文本 ──→ 普通LLM ──→ 文本 ──→ TTS ──→ 音频+Viseme
  │           ~500ms          │     ~800ms         │    ~300ms
  └──── 总感知延迟 ≈ 1600ms+ ─────────────────────────────────────┘

Voice Live + realtime 模型:
  用户说话 ──→ realtime model(音频直入,内置VAD) ──→ 文本 ──→ TTS ──→ 音频+Viseme
  │                  ~300-500ms                         │    ~300ms
  └──── 总感知延迟 ≈ 600-800ms ────────────────────────────────────┘
```

**对比结论：**

| 环节 | 传统方案 | Voice Live + Realtime | 差异 |
|------|---------|----------------------|------|
| 语音活动检测 (VAD) | 独立 VAD 模块，需等静音超时 | 模型内置 VAD，实时判断 | **省 200-400ms** |
| 语音 → 理解 (ASR) | 独立 STT 服务，~500ms | 模型直接理解音频，跳过 ASR | **省 ~500ms** |
| 文本生成 (LLM) | 标准推理，TTFT ~800ms | 对话优化，TTFT ~300ms | **省 ~500ms** |
| 文本 → 语音 (TTS) | Azure Speech，~300ms | Azure Speech，~300ms | **一样！** |
| **总计** | **~1600ms+** | **~600-800ms** | **省 ~800ms** |

> 注意：**TTS 这一段延迟完全相同**。Realtime 模型省下来的时间全部在输入端（VAD + ASR）和理解端（LLM 推理），不在输出端（TTS）。

### 11.6.4 不需要 Avatar 时 —— 可以跳过 TTS，再快 300ms

如果业务场景**不需要数字人**（只要语音对话，没有虚拟形象），可以直接使用 realtime 模型的原生音频输出，彻底绕过 Azure Speech Service 的 TTS 环节：

```
无 Avatar 模式（直接用 realtime 原生音频）:
  用户说话 ──→ realtime model ──→ 文本 + 音频同时输出
  │               ~300-500ms         │
  └──── 总感知延迟 ≈ 300-500ms ──────┘
```

**因为不需要 viseme 数据，就不需要 Azure Speech Service，就可以直接用 realtime 模型的原生音频。**

#### 三种方案的完整对比

| 方案 | 延迟 | Avatar | 语音品质 | 适用场景 |
|------|------|--------|---------|---------|
| **A. 传统管线** | ~1600ms+ | ❌ 不支持 | 可选任意 TTS 声音 | 对延迟不敏感的文本聊天 + 语音播报 |
| **B. Voice Live + Realtime + Avatar** | ~600-800ms | ✅ 支持 | Azure 神经语音（高品质） | 数字人面对面训练（本项目默认方案） |
| **C. Realtime 原生音频（无 Avatar）** | ~300-500ms | ❌ 不支持 | realtime 内置语音（品质一般） | 纯语音对话，追求极致低延迟 |

```
延迟对比（越短越好）:

方案A 传统管线    ████████████████████████████████  ~1600ms
方案B VL+Avatar   ████████████████                  ~700ms    省 ~56%
方案C 无Avatar     ██████████                        ~400ms    省 ~75%

                  0    200   400   600   800  1000  1200  1400  1600ms
```

### 11.6.5 客户觉得慢怎么办？—— 分级加速策略

当客户反馈"数字人回复太慢"时，按以下优先级逐步优化：

#### 第一级：优化现有管线（不改架构）

| 手段 | 预计收益 | 实现难度 |
|------|---------|---------|
| 启用 TTS streaming（流式合成） | 减少 ~100-150ms | 低 — 配置 `speech_out.streaming: true` |
| 优化 system prompt 长度 | 减少 LLM TTFT ~50-100ms | 低 — 精简指令 |
| 使用更快的 realtime 模型（gpt-4o-mini-realtime） | 减少 LLM ~100-200ms | 低 — 改模型配置 |
| 地域就近部署（选离用户近的 Azure region） | 减少网络 RTT ~50-100ms | 中 — 需要多区域部署 |

#### 第二级：前端感知优化（不改后端）

| 手段 | 预计收益 | 原理 |
|------|---------|------|
| 打字机效果显示文本 | 感知延迟降低 ~300ms | 文本先于音频到达，用打字机效果让用户先"看到"回复（详见 [14-production-operations.md](./14-production-operations.md) 的文字语音同步一节） |
| 思考动画 / 加载提示 | 心理感知改善 | 数字人"点头思考"动画让等待不那么枯燥 |
| 预热连接 | 首次响应快 ~200ms | 页面加载时就建立 WebSocket + WebRTC 连接，而不是用户点"开始"才连接 |

#### 第三级：降级方案（牺牲 Avatar 换速度）

如果上述优化后客户仍不满意，可以提供**纯语音模式**作为降级选项：

```
┌─────────────────────────────────────────────────────┐
│            前端模式切换（让用户自己选）                  │
│                                                      │
│  ┌──────────────────┐    ┌──────────────────┐       │
│  │  🎭 数字人模式     │    │  🎤 纯语音模式    │       │
│  │  （默认）          │    │  （低延迟）       │       │
│  │                   │    │                   │      │
│  │  延迟: ~700ms     │    │  延迟: ~400ms     │      │
│  │  有虚拟形象       │    │  无虚拟形象       │       │
│  │  高品质语音       │    │  标准语音         │       │
│  │  Avatar+WebRTC    │    │  仅 WebSocket     │      │
│  └──────────────────┘    └──────────────────┘       │
└─────────────────────────────────────────────────────┘
```

实现方式：

- **数字人模式（方案 B）**：当前架构不变，Voice Live API + Avatar + Azure Speech TTS，均通过 Hosted Agent 编排
- **纯语音模式（方案 C）**：不启用 avatar modality，直接使用 realtime 模型的原生音频输出，跳过 TTS 环节。前端不建立 WebRTC 连接，只通过 WebSocket 接收音频

```typescript
// 前端模式切换示例
function createVoiceLiveConfig(mode: 'avatar' | 'voice-only') {
  if (mode === 'avatar') {
    return {
      modalities: ['text', 'audio', 'avatar'],
      speech_out: {
        voice_name: 'zh-CN-XiaoxiaoMultilingualNeural',
        streaming: true,
      },
      avatar: {
        character: 'lisa',
        style: 'casual-sitting',
      },
    };
  } else {
    // 纯语音模式：不配置 speech_out 和 avatar
    // realtime 模型直接输出音频，跳过 TTS
    return {
      modalities: ['text', 'audio'],
      // 不配置 speech_out → Voice Live 直接使用 realtime 模型的原生音频
      // 不配置 avatar → 不建立 WebRTC 连接
    };
  }
}
```

#### 第四级：架构升级（大投入）

| 方案 | 延迟目标 | 代价 |
|------|---------|------|
| 自建 TTS + Viseme 管线 | ~500ms | 需要自己实现 viseme 生成，技术难度极高 |
| 预生成常用回复 | 首句 ~100ms | 需要维护"常见开场白"库，牺牲灵活性 |
| Edge 部署 realtime 模型 | ~200-300ms | 需要 Azure Edge Zone，成本极高 |

### 11.6.6 决策总结

```
客户反馈"太慢了"
    │
    ├─ 先量化：到底是多少 ms？用 getStats() 和日志确认
    │          （参考 14-production-operations.md 远程诊断一节）
    │
    ├─ < 1s？ → 第一级 + 第二级优化，大部分客户可接受
    │
    ├─ 仍不满意？ → 提供"纯语音模式"降级开关（第三级）
    │              无 Avatar，延迟降至 ~400ms
    │
    └─ 极端要求 < 300ms？ → 第四级，需评估 ROI
```

> **给技术决策者的建议**：不要一开始就承诺"realtime 模型 = 实时响应"。在有 Avatar 的场景下，TTS 是绕不开的瓶颈。正确的沟通方式是告知客户"数字人模式约 0.7 秒响应，纯语音模式约 0.4 秒"，让客户基于业务需求做选择，而不是事后被"怎么这么慢"的反馈搞得措手不及。

---

## 11.7 SDK 与 api-version 参考（本次刷新新增）

以下信息与后端实际配置对齐（`backend/app/config.py` / `backend/pyproject.toml`），供排查版本相关问题时参考：

| 项 | 值 | 来源 |
|----|-----|------|
| api-version | `2026-07-15`（GA） | `settings.voice_live_api_version`，`backend/app/config.py` |
| SDK 依赖 | `azure-ai-voicelive[aiohttp]==1.3.0b1`（临时固定；GA 1.3.0 尚未发布至 PyPI，截至 2026-07-19） | `backend/pyproject.toml` |
| connect() 签名（本次刷新起） | `connect(endpoint=..., credential=..., agent_name=..., project_name=..., avatar_config=...)`（扁平化 kwargs，取代旧版嵌套 `AgentSessionConfig`/`agent_config` dict） | Azure Voice Live SDK 1.3.0b1+ |
| 认证路径 | Entra ID 优先，API Key 为 fallback（D-01） | `backend/app/services/voice_live_websocket.py` |

一旦 SDK GA 1.3.0 正式登陆 PyPI，需要同步更新此表和 `pyproject.toml` 的实际 pin，避免本参考页与代码再次产生分歧。

---

> 返回 [文档目录](./00-index.md) | 相关：[01-architecture.md](./01-architecture.md) · [09-websocket-webrtc-protocol.md](./09-websocket-webrtc-protocol.md) · [14-production-operations.md](./14-production-operations.md)
