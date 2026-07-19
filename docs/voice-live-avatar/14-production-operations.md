# 14 — 生产环境运维

<!-- merged from README/09-production/README.md, README/09-production/diagnostics.md, README/09-production/scalability.md, README/09-production/text-audio-sync.md -->

> 返回 [文档目录](./00-index.md)

---

将 Voice Live + 数字人 Avatar 方案推向生产环境时，会遇到三类典型的工程挑战：**文字与音频的同步问题**、**高并发场景下的扩容策略**、以及**线上故障的远程诊断能力**。这三个专题环环相扣——同步影响用户体验，扩容影响系统容量，而诊断能力则决定了你能否在出问题时快速定位和修复。

本章包含三个深度专题，每个专题都从实际生产场景出发，给出具体的技术方案和代码实现：

- **[14A. 文字显示与语音播放的同步方案](#14a-文字语音同步)**：WebSocket 的文字和 WebRTC 的音视频走的是两条完全独立的通道，没有共同的时钟基准，导致文字"跑"得比数字人嘴巴快。本专题分析了延迟差距的成因，对比了五种同步方案，并给出了推荐的组合策略——仅需约 30 行代码即可实现感知层面的"基本同步"。
- **[14B. 扩容策略 —— 100 个 MR 同时训练能撑住吗？](#14b-扩容策略)**：WebSocket 代理是典型的 I/O-bound 场景，Python async 恰好是为这种场景设计的。本专题逐项分析了 100 并发的资源开销，定位了真正的瓶颈（网络带宽和 Azure API 配额，而非 CPU），并给出了从 50 用户到 1000+ 用户的分级扩容策略。
- **[14C. 远程诊断 ——"数字人不出来"怎么排查？](#14c-远程诊断)**：用户在生产环境报告"能看到文字，但数字人没有画面"。本专题建立了三层日志体系（前端埋点 + 后端日志 + WebRTC getStats()），给出了完整的诊断流程和决策树，让你在不到现场的情况下精确定位问题环节。

---

## 14A. 文字语音同步

### 问题本质

WebSocket 的文字和 WebRTC 的音视频走的是两条完全独立的通道，没有共同的时钟基准，导致文字"跑"得比数字人嘴巴快。这是 WebSocket + WebRTC 双通道架构下不可避免的同步问题。

### 延迟差距有多大？

要解决同步问题，首先需要理解两条通道的延迟差距从何而来：

```
Azure 同时生成 text token + audio token（经由 Hosted Agent 驱动的 Voice Live 会话）
  │
  ├── 文字路径：text token → JSON → WebSocket → 浏览器渲染
  │   总延迟：~50-100ms
  │
  └── 数字人路径：audio token → TTS 合成 → Avatar 渲染引擎（口型+面部+身体）
      → H.264 编码 → WebRTC 传输 → 浏览器解码 → <video> 渲染
      总延迟：~400-1000ms

差距：文字比数字人嘴巴快 ~300-900ms
用户感受：文字已经显示"半衰期是24小时"，数字人嘴巴还在说"半衰期是..."
```

文字路径只经过 JSON 序列化和 WebSocket 传输，几乎没有计算开销；而数字人路径需要经过 TTS 合成、Avatar 渲染（面部表情、口型动画、身体姿态）、视频编码、WebRTC 传输、浏览器解码等多个环节，累积延迟显著。

### 方案对比

针对这个问题，有五种可选方案，它们在实现复杂度和用户体验之间各有取舍：

```
┌──────────────────┬───────────────┬───────────┬───────────────┬──────────────────┐
│ 方案              │ 实现复杂度     │ 用户体验   │ 适用场景       │ 本项目可行性      │
├──────────────────┼───────────────┼───────────┼───────────────┼──────────────────┤
│ 1. 延迟文字显示   │ ★☆☆           │ ★★★       │ 数字人模式     │ ✅ 推荐           │
│ 2. 打字机效果     │ ★★☆           │ ★★★       │ 所有模式       │ ✅ 推荐           │
│ 3. 音频时间戳对齐 │ ★★★★          │ ★★★★      │ 专业字幕场景   │ ⚠️ 过度设计       │
│ 4. 隐藏文字       │ ★☆☆           │ ★★☆       │ 简单场景       │ ❌ 损失功能       │
│ 5. 双缓冲+标记   │ ★★★           │ ★★★★      │ 高质量场景     │ ✅ 进阶方案       │
└──────────────────┴───────────────┴───────────┴───────────────┴──────────────────┘
```

下面逐一展开每个方案的具体实现。

### 方案 1：延迟文字显示（最简单有效）

核心思路：文字到了先不显示，等一个固定延迟后再渲染，让它和音频"对齐"。

```typescript
// voice-transcript.tsx 中的改动

// 收到 transcript.delta 时，不立即渲染，而是放入延迟队列
const AVATAR_PIPELINE_DELAY = 500; // ms，需要根据实测调整

function onTranscriptDelta(text: string, isAvatarMode: boolean) {
  if (isAvatarMode) {
    // 数字人模式：延迟显示
    setTimeout(() => {
      appendToTranscript(text);
    }, AVATAR_PIPELINE_DELAY);
  } else {
    // 纯语音模式：立即显示（WebSocket 音频和文字延迟差距小）
    appendToTranscript(text);
  }
}
```

```
优点：
  ✅ 实现极简（3 行代码）
  ✅ 效果明显（文字不会大幅领先音频）

缺点：
  ❌ 固定延迟是猜测值，不一定精确
  ❌ 网络波动时可能又不同步
  ❌ 纯语音模式和数字人模式需要不同的延迟值
```

### 方案 2：打字机效果（推荐 + 方案 1 组合使用）

核心思路：文字不是瞬间出现，而是一个字一个字地"打"出来，模拟说话速度。

```typescript
// useTypewriterEffect hook

function useTypewriterEffect(text: string, isAvatarMode: boolean) {
  const [displayed, setDisplayed] = useState("");
  const [queue, setQueue] = useState<string[]>([]);

  // 文字到达时追加到队列
  useEffect(() => {
    if (text) {
      setQueue(prev => [...prev, ...text.split("")]);
    }
  }, [text]);

  // 按速度从队列中取出字符显示
  useEffect(() => {
    if (queue.length === 0) return;

    // 中文 ~4 字/秒（正常语速），英文 ~12 字/秒
    // 数字人模式放慢，纯语音模式加快
    const charDelay = isAvatarMode ? 250 : 80; // ms per character

    const timer = setInterval(() => {
      setQueue(prev => {
        if (prev.length === 0) {
          clearInterval(timer);
          return prev;
        }
        const [next, ...rest] = prev;
        setDisplayed(d => d + next);
        return rest;
      });
    }, charDelay);

    return () => clearInterval(timer);
  }, [queue.length > 0]);

  return displayed;
}
```

```
效果：
  文字一个字一个字出现，视觉上和数字人说话节奏接近
  用户不会感到文字"跑"得太快

优点：
  ✅ 视觉上自然，像"实时字幕"的感觉
  ✅ 不需要知道确切的音频延迟
  ✅ 纯语音模式也能用（调快速度即可）

缺点：
  ❌ 字符速度是估算的，和实际语速不一定精确匹配
  ❌ 如果 AI 一次返回大段文字，队列会堆积
```

### 方案 3：基于音频时间戳的精确对齐（专业方案，为何不采用）

核心思路：利用 WebRTC 的 RTP 时间戳和 WebSocket 的 transcript 事件建立时间映射。

```
原理：
  Azure 在返回 transcript.delta 时，同时返回了对应的文字内容
  Azure 在 WebRTC 音频流中，RTP 包带有时间戳

  如果能建立映射：transcript 第 N 个字 ↔ RTP 时间戳 T
  就能精确地在音频播到时间 T 时，显示第 N 个字

问题：
  Azure Voice Live API 的 transcript.delta 事件目前不包含
  精确的音频时间戳信息（只有文字内容和 response_id）

  要实现精确对齐，需要：
  1. Azure API 返回 word-level timing（目前不支持）
  2. 或者自己做前端 VAD + 音频分析来估算对齐点

  这在当前 API 下是过度设计。
```

虽然这是理论上最精确的方案，但受限于当前 Azure API 的能力，实现成本远高于收益。

### 方案 5：双缓冲 + 音频状态标记（进阶方案）

核心思路：监听 WebRTC 音频轨道的播放状态，根据"数字人是否正在说话"来控制文字释放。

```typescript
// 进阶同步方案：基于音频活动检测

function useSyncedTranscript(audioRef: RefObject<HTMLAudioElement>) {
  const pendingText = useRef<string[]>([]);
  const [visibleText, setVisibleText] = useState("");

  // 监听数字人音频的播放状态
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    // 方法 A：用 AudioContext 分析音量
    const ctx = new AudioContext();
    const source = ctx.createMediaElementSource(audio);
    const analyser = ctx.createAnalyser();
    source.connect(analyser);
    analyser.connect(ctx.destination);

    const dataArray = new Uint8Array(analyser.frequencyBinCount);

    function checkAudioLevel() {
      analyser.getByteFrequencyData(dataArray);
      const avg = dataArray.reduce((a, b) => a + b) / dataArray.length;

      if (avg > 10) {
        // 数字人正在说话 → 释放待显示文字
        if (pendingText.current.length > 0) {
          const chunk = pendingText.current.shift()!;
          setVisibleText(prev => prev + chunk);
        }
      }
      // 数字人没说话 → 暂停释放（等音频跟上）

      requestAnimationFrame(checkAudioLevel);
    }

    checkAudioLevel();
    return () => ctx.close();
  }, []);

  // 文字到达时放入 pending 缓冲
  const addText = useCallback((text: string) => {
    pendingText.current.push(text);
  }, []);

  return { visibleText, addText };
}
```

```
优点：
  ✅ 真正基于音频状态同步，不是猜测延迟
  ✅ 自适应网络波动（音频快就文字快，音频慢就文字慢）

缺点：
  ❌ 实现复杂，需要 AudioContext 分析
  ❌ createMediaElementSource 有跨域限制
  ❌ 分析音量不等于分析"说了什么字"，粒度较粗
```

### 推荐组合

综合实现成本和用户体验，本项目推荐 **方案 1 + 方案 2 的组合**：

```
本项目推荐：方案 1 + 方案 2 的组合

数字人模式：
  1. 收到 transcript.delta → 先延迟 400ms（方案 1）
  2. 延迟后以打字机效果逐字显示（方案 2，~4 字/秒）
  3. 如果 transcript.done 到达时打字机队列还没打完 → 立即显示剩余

纯语音模式：
  1. 无延迟
  2. 打字机效果加速（~12 字/秒）或直接显示

这个组合只需要约 30 行代码，就能让文字显示和数字人说话在感官上"基本同步"。
不追求帧级精确，而是追求用户感知的一致性——这对 MR 培训场景完全够用。
```

### 为什么不追求完美同步？

最后，有必要解释为什么在工程实践中不需要追求帧级精确的音文同步：

```
1. 用户期望管理：
   人类观看"带字幕的视频"时，对字幕提前 0.5 秒是高度宽容的
   （电影字幕经常比对白提前 0.3-0.5 秒，观众完全不觉得不自然）

2. 注意力分配：
   MR 培训时，用户要么看数字人脸（80% 时间），要么看文字（20% 时间）
   极少同时盯着两者比较同步性

3. 投入产出比：
   精确同步需要：word-level timing API + AudioContext 分析 + 复杂状态机
   投入：几天开发 + 长期维护
   收益：从"基本同步"到"完美同步"，用户几乎感知不到差异

4. Azure API 限制：
   当前 Voice Live API 不返回 word-level timing
   没有 API 支持的情况下，前端再怎么努力也只是近似值
```

工程决策的关键在于**投入产出比**——把有限的开发资源投入到用户能感知到差异的地方，而不是追求理论上的完美。

---

## 14B. 扩容策略

### 结论先行

撑得住。WebSocket 代理是典型的 I/O-bound 场景，Python async 恰好是为这种场景设计的。但瓶颈不在 CPU 或协程数量，而在内存管理和 Azure API 配额。

### 工作负载分析

要回答"能不能撑住"的问题，首先需要精确分析每个 MR 训练会话给后端带来的工作负载：

```
每个 MR 训练会话，后端做的事情：

  1. 维护一条 WebSocket 连接（浏览器 → 后端）
  2. 维护一条 Azure SDK 连接（后端 → Azure Voice Live）
  3. 转发 JSON 消息（文字、控制指令）
  4. 转发 base64 编码的音频数据

逐项分析：

┌──────────────────┬──────────────┬───────────────┬───────────────────────┐
│ 操作              │ I/O or CPU？  │ 单次开销       │ 100 并发总开销         │
├──────────────────┼──────────────┼───────────────┼───────────────────────┤
│ WebSocket 连接    │ I/O (网络)   │ ~10KB 内存     │ ~1MB                  │
│ 维持             │              │ 0 CPU（等待中）│ 0 CPU                 │
├──────────────────┼──────────────┼───────────────┼───────────────────────┤
│ Azure SDK 连接   │ I/O (网络)   │ ~50KB 内存     │ ~5MB                  │
│ 维持             │              │ 0 CPU（等待中）│ 0 CPU                 │
├──────────────────┼──────────────┼───────────────┼───────────────────────┤
│ JSON 消息转发     │ I/O 为主     │ ~1KB/消息      │ 100条/秒 → ~100KB/s  │
│ （文字、控制）    │ 极少 CPU     │ JSON 解析极快  │ CPU 忽略不计          │
├──────────────────┼──────────────┼───────────────┼───────────────────────┤
│ 音频数据转发      │ I/O 为主     │ ~16KB/帧       │ 100×50帧/秒           │
│ (base64 PCM16)  │ 少量 CPU     │ 每秒50帧×16KB  │ = ~80MB/s 网络吞吐    │
│                  │ (base64解编码)│ = ~800KB/s/人  │ CPU: base64 编解码    │
├──────────────────┼──────────────┼───────────────┼───────────────────────┤
│ 音频缓冲区       │ 内存          │ ~512KB/人      │ ~50MB                 │
│ (AudioWorklet   │              │ (环形缓冲)     │                       │
│  的数据暂存)     │              │               │                       │
└──────────────────┴──────────────┴───────────────┴───────────────────────┘

总计（100 并发）：
  内存：~60MB（WebSocket + SDK + 缓冲区）→ 远低于典型服务器 4-16GB
  CPU：极低（几乎都在等 I/O）
  网络：~80MB/s 出站（主要是音频转发）→ 这才是真正的瓶颈
```

数据很清楚：100 并发在内存和 CPU 层面完全不是问题，**网络带宽才是真正的瓶颈**。

### 为什么 Python async 适合这个场景？

有人可能会质疑：Python 不是因为 GIL 性能差吗？对于 CPU 密集型任务确实如此，但 WebSocket 代理恰恰是 I/O 密集型任务，这正是 Python asyncio 最擅长的领域：

```
Python asyncio 的核心能力：
  一个线程上跑数千个协程
  每个协程在等 I/O 时自动让出 CPU
  I/O 完成时自动恢复执行

WebSocket 代理的典型循环：

async def proxy_session(browser_ws, azure_sdk):
    async for message in browser_ws:        # ← 等用户发消息（I/O 等待）
        await azure_sdk.send(message)       # ← 转发给 Azure（I/O 等待）

    async for event in azure_sdk:           # ← 等 Azure 返回（I/O 等待）
        await browser_ws.send(event)        # ← 转发给浏览器（I/O 等待）

每一行 await 都是 I/O 等待 → 自动让出 CPU → 其他协程继续执行
100 个会话 = 200 个协程 = 全部在同一个线程上交替执行
99% 的时间都在等 I/O，CPU 几乎空闲
```

### 真正的瓶颈在哪里？

通过上面的分析，我们可以识别出四个潜在瓶颈，按严重程度排序：

#### 瓶颈 1：网络带宽（最可能的瓶颈）

```
┌────────────────────────────────────────────────────────────────┐
│                                                                │
│  每个用户的音频数据：                                            │
│    上行（用户→后端→Azure）：PCM16 24kHz mono = ~48KB/s          │
│    下行（Azure→后端→用户）：PCM16 24kHz mono = ~48KB/s          │
│                           + JSON 消息 ≈ ~5KB/s                 │
│    单用户合计：~100KB/s 双向                                    │
│                                                                │
│  100 用户并发：                                                 │
│    后端总带宽：~10MB/s = ~80Mbps                                │
│    → Azure Container App 默认出站带宽：通常 100-200Mbps          │
│    → 刚好够用，但没有太多余量                                    │
│                                                                │
│  ⚠️ 如果要支持 500+ 并发 → 需要水平扩展（多实例）                │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

#### 瓶颈 2：Azure Voice Live API 配额

```
┌────────────────────────────────────────────────────────────────┐
│                                                                │
│  Azure 对 Voice Live API 有并发限制：                            │
│    - 每个 endpoint 的并发 session 数有上限（查 Azure 文档）       │
│    - 每分钟请求数（RPM）限制                                     │
│    - 每个 subscription 的 TPS 限制                               │
│                                                                │
│  100 个并发 session 可能触发：                                   │
│    - 并发连接上限（需要申请 quota 提升）                          │
│    - Token 用量上限（Hosted Agent 驱动的语音会话计费不低）        │
│                                                                │
│  ✅ 解决方案：                                                   │
│    - 提前联系 Azure 申请 quota 提升                               │
│    - 多个 AI Foundry project 做负载分散                          │
│    - 会话结束后及时释放 SDK 连接                                  │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

#### 瓶颈 3：内存管理（容易被忽视）

```
┌────────────────────────────────────────────────────────────────┐
│                                                                │
│  每个会话需要缓冲音频数据：                                       │
│    - 用户音频上行缓冲：~64KB（AudioWorklet 到 WebSocket 的暂存） │
│    - Azure 响应缓冲：~256KB（SDK 事件队列）                      │
│    - transcript 历史：~10-50KB（整个对话的文字记录）              │
│                                                                │
│  100 并发 × ~400KB/会话 = ~40MB → 完全没问题                    │
│                                                                │
│  ⚠️ 但要注意内存泄漏：                                           │
│    - 会话异常断开后，SDK 连接没有正确关闭                         │
│    - 音频缓冲没有释放                                            │
│    - 事件队列持续增长（消费者断了但生产者还在推）                  │
│                                                                │
│  ✅ 解决方案：                                                   │
│    - try/finally 确保 SDK 连接在任何退出路径都关闭                │
│    - 设置 per-session 超时（如 30 分钟自动断开）                  │
│    - 定期记录内存使用情况（process.memory_info()）                │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

#### 瓶颈 4：base64 编解码的 CPU 开销（通常不是问题）

```
┌────────────────────────────────────────────────────────────────┐
│                                                                │
│  音频数据以 base64 编码在 JSON 中传输                            │
│  每帧需要 base64 decode → 转发 → 可能再 base64 encode           │
│                                                                │
│  Python 的 base64 模块是 C 实现的，性能很好：                     │
│    base64.b64decode(16KB) ≈ 2-5 微秒                           │
│    100 用户 × 50 帧/秒 × 5 微秒 = 25 毫秒/秒 CPU 时间          │
│    → 占单核 CPU 的 2.5% → 完全不是问题                          │
│                                                                │
│  ⚠️ 但如果你做了不必要的操作（如解析/修改音频内容再重新编码），    │
│     CPU 开销会增加。原则：音频数据能原样转发就原样转发。           │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### 扩容策略

根据并发规模的不同，需要采取不同级别的架构策略：

```
┌────────────────┬─────────────┬─────────────────────────────────────┐
│ 并发规模        │ 架构         │ 关键措施                              │
├────────────────┼─────────────┼─────────────────────────────────────┤
│ 1-50 用户      │ 单实例       │ 单个 uvicorn worker 就够               │
│                │             │ 4 workers 有充足余量                   │
├────────────────┼─────────────┼─────────────────────────────────────┤
│ 50-200 用户    │ 单实例       │ uvicorn 4 workers                    │
│                │ 多 worker   │ 申请 Azure API quota 提升              │
│                │             │ 监控内存和网络带宽                      │
├────────────────┼─────────────┼─────────────────────────────────────┤
│ 200-1000 用户  │ 水平扩展     │ 多个 Container App 实例               │
│                │             │ WebSocket 需要 sticky session          │
│                │             │ （同一用户的 WS 始终连到同一实例）       │
│                │             │ Azure Front Door / Application Gateway │
│                │             │ 多个 AI Foundry project 分散 quota      │
├────────────────┼─────────────┼─────────────────────────────────────┤
│ 1000+ 用户     │ 微服务       │ WebSocket 代理独立服务（可独立扩缩容）  │
│                │             │ 业务 API 独立服务                       │
│                │             │ Redis pub/sub 做跨实例事件分发          │
│                │             │ 考虑 Go/Rust 重写 WebSocket 代理层      │
└────────────────┴─────────────┴─────────────────────────────────────┘
```

### WebSocket 的 sticky session 问题

当进行水平扩展时，WebSocket 的有状态特性带来了一个关键问题：

```
WebSocket 连接是有状态的，一旦建立就绑定到特定的后端实例。
如果你用负载均衡器分配请求，需要确保：

  用户 A 的 WebSocket 建立时连到了 实例 1
  → 后续所有 WebSocket 消息都必须路由到 实例 1
  → 这叫 "sticky session" 或 "session affinity"

  如果负载均衡器把某条消息路由到 实例 2
  → 实例 2 上没有这个 WebSocket 连接 → 消息丢失

解决方案：
  1. Azure Container Apps 支持基于 cookie 的 session affinity
  2. 或者前端 WebSocket URL 中直接包含实例标识
  3. 或者用 Redis pub/sub 让所有实例共享消息
     （但这增加了复杂度，100 并发不需要）
```

### 实测基准参考

以下数据可以作为容量规划的参考基准：

```
单个 uvicorn worker（Python 3.11 + FastAPI）的 WebSocket 并发能力：

  轻量消息（纯 JSON 转发）：
    → 可承载 3000-5000 并发 WebSocket 连接
    → 瓶颈在事件循环的文件描述符上限（ulimit）

  重载消息（含 base64 音频转发）：
    → 可承载 500-1000 并发 WebSocket 连接
    → 瓶颈在网络 I/O 和 base64 处理

  4 个 uvicorn workers：
    → 能力 ×4（每个 worker 是独立进程，独立事件循环）
    → 2000-4000 并发 WebSocket 连接

  结论：100 个 MR 并发，单实例 + 4 workers 绰绰有余。
  甚至用 1 个 worker 也大概率够用。
```

### 关键代码模式：确保资源正确释放

高并发场景下，最容易出问题的不是性能，而是资源泄漏。以下是 WebSocket 代理的健壮实现模式：

```python
# backend/app/services/voice_live_websocket.py — WebSocket 代理的健壮实现（示例，字段名与实际实现可能略有差异）

@router.websocket("/ws")
async def voice_live_ws(ws: WebSocket, token: str = Query(...)):
    user = await verify_token(token)
    await ws.accept()

    azure_client = None
    try:
        # 连接 Azure Voice Live SDK（agent_name/project_name 定位 Hosted Agent）
        azure_client = await connect_voice_live(
            endpoint=settings.voice_live_endpoint,
            credential=get_credential(),
            agent_name=settings.hosted_agent_name,
            project_name=settings.foundry_project_name,
        )

        # 双向转发（两个并发任务）
        async with asyncio.TaskGroup() as tg:
            tg.create_task(forward_browser_to_azure(ws, azure_client))
            tg.create_task(forward_azure_to_browser(azure_client, ws))

    except WebSocketDisconnect:
        logger.info("User %s disconnected normally", user.id)
    except Exception as e:
        logger.error("Session error for user %s: %s", user.id, e)
    finally:
        # ⚠️ 关键：无论怎么退出都要清理！
        if azure_client:
            await azure_client.close()       # 关闭 Azure SDK 连接
        try:
            await ws.close()                 # 关闭浏览器 WebSocket
        except Exception:
            pass                             # 可能已经关闭了
        logger.info("Session cleaned up for user %s", user.id)
```

`try/finally` 模式是这段代码的核心：无论会话因为什么原因结束（正常断开、异常错误、网络超时），`finally` 块都会确保 Azure SDK 连接和浏览器 WebSocket 被正确关闭，避免资源泄漏。

### 扩容策略小结

100 并发 MR 训练对 Python async + FastAPI 来说完全不是问题。这是经典的 I/O-bound 工作负载，Python asyncio 恰好为此设计。单实例 4 workers 可以轻松处理。真正的瓶颈在 Azure API 配额和网络带宽上。需要关注的工程问题是资源泄漏（确保每个会话退出时正确关闭所有连接）和内存监控。500+ 并发时才需要考虑水平扩展和 sticky session。

---

## 14C. 远程诊断

### 问题场景

用户在生产环境报告"我能看到文字，但数字人没有画面"。你不在现场，怎么远程诊断？

### 第一原则：这个问题 = "WebSocket 正常，WebRTC 断开"

回到前面章节的结论，能看到文字说明数据通道正常，看不到数字人说明视频通道出了问题：

```
✅ 文字正常 = WebSocket 通道正常
❌ 没有视频 = WebRTC 通道未建立或已断开
❌ 没有音频 = WebRTC Audio Track 未连接（数字人模式下音频走 WebRTC）
```

所以排查方向明确：**WebRTC 建立过程中的哪一步失败了？**

### 日志埋点矩阵

要实现远程诊断，需要在 WebRTC 建立流程的每一步都埋入日志。以下是完整的埋点矩阵：

```
┌──────────────────────────────────────────────────────────────────────┐
│ 完整的日志埋点矩阵（按 WebRTC 建立流程排列）                           │
├────────┬───────────────────────────────┬──────────┬─────────────────┤
│ 阶段    │ 日志内容                       │ 位置      │ 级别             │
├────────┼───────────────────────────────┼──────────┼─────────────────┤
│ 1      │ session.updated 收到，         │ 前端      │ INFO            │
│        │ 是否包含 ice_servers？         │          │                 │
│        │ ice_servers 数量和类型         │          │                 │
├────────┼───────────────────────────────┼──────────┼─────────────────┤
│ 2      │ RTCPeerConnection 创建成功？   │ 前端      │ INFO            │
│        │ iceServers 配置内容            │          │                 │
├────────┼───────────────────────────────┼──────────┼─────────────────┤
│ 3      │ ICE gathering 开始            │ 前端      │ DEBUG           │
│        │ 每个 candidate 的 type+proto  │          │                 │
│        │ gathering 耗时                │          │                 │
│        │ 是否超时（>8s）               │          │                 │
├────────┼───────────────────────────────┼──────────┼─────────────────┤
│ 4      │ SDP Offer 已生成              │ 前端      │ INFO            │
│        │ SDP 中的 candidate 数量       │          │                 │
│        │ SDP 中包含哪些 candidate 类型 │          │                 │
├────────┼───────────────────────────────┼──────────┼─────────────────┤
│ 5      │ session.avatar.connect 已发送 │ 前端+后端 │ INFO            │
│        │ 后端是否成功转发给 Azure SDK  │ 后端      │ INFO            │
├────────┼───────────────────────────────┼──────────┼─────────────────┤
│ 6      │ server_sdp 是否收到？         │ 前端      │ INFO            │
│        │ 收到耗时（从发送到收到）       │          │                 │
│        │ 超时（>15s）则报 WARN        │          │                 │
├────────┼───────────────────────────────┼──────────┼─────────────────┤
│ 7      │ setRemoteDescription 成功？   │ 前端      │ INFO/ERROR      │
│        │ 如果失败，记录错误信息         │          │                 │
├────────┼───────────────────────────────┼──────────┼─────────────────┤
│ 8      │ iceConnectionState 变化       │ 前端      │ INFO            │
│        │ new→checking→connected/failed │          │                 │
│        │ 如果卡在 checking >10s → WARN │          │                 │
├────────┼───────────────────────────────┼──────────┼─────────────────┤
│ 9      │ ontrack 是否触发？            │ 前端      │ INFO            │
│        │ 收到几个 track？什么 kind？   │          │                 │
│        │ video/audio 是否都到了？      │          │                 │
├────────┼───────────────────────────────┼──────────┼─────────────────┤
│ 10     │ <video>.play() 是否成功？     │ 前端      │ INFO/ERROR      │
│        │ 如果 play() 抛异常，记录原因  │          │                 │
│        │ （常见：autoplay policy）     │          │                 │
└────────┴───────────────────────────────┴──────────┴─────────────────┘
```

每个阶段都是 WebRTC 可能失败的环节，缺少任何一个阶段的日志都会导致诊断时出现"盲区"。

### 前端日志实现

以下代码展示了如何在 `use-avatar-stream.ts` 中系统性地埋入诊断日志：

```typescript
// use-avatar-stream.ts — 增强日志版本

function useAvatarStream() {
  const connect = async (iceServers: RTCIceServer[], sendSdp: Function) => {
    // ========== 阶段 1: 检查 ICE servers ==========
    console.info("[Avatar] ICE servers received:", {
      count: iceServers.length,
      types: iceServers.map(s => {
        const url = Array.isArray(s.urls) ? s.urls[0] : s.urls;
        return url?.startsWith("turn:") ? "TURN" : "STUN";
      }),
      hasCredentials: iceServers.some(s => s.username && s.credential),
    });

    if (iceServers.length === 0) {
      console.error("[Avatar] ❌ No ICE servers! Avatar 功能可能未启用");
      reportToBackend("avatar_no_ice_servers", { sessionId });
      return;
    }

    // ========== 阶段 2: 创建 PeerConnection ==========
    const pc = new RTCPeerConnection({
      iceServers,
      bundlePolicy: "max-bundle",
    });
    console.info("[Avatar] PeerConnection created");

    // ========== 阶段 3: 监听 ICE 状态变化 ==========
    const iceStartTime = Date.now();
    let candidateCount = { host: 0, srflx: 0, relay: 0 };

    pc.onicecandidate = (e) => {
      if (e.candidate) {
        const type = e.candidate.type as keyof typeof candidateCount;
        candidateCount[type] = (candidateCount[type] || 0) + 1;
        console.debug("[Avatar] ICE candidate: %s %s",
          e.candidate.type, e.candidate.protocol);
      } else {
        const elapsed = Date.now() - iceStartTime;
        console.info("[Avatar] ICE gathering complete in %dms:", elapsed, candidateCount);

        // ⚠️ 如果没有 relay candidate，企业网可能连不上
        if (candidateCount.relay === 0) {
          console.warn("[Avatar] ⚠️ No relay candidates! 企业防火墙后可能连不上");
          reportToBackend("avatar_no_relay_candidates", { candidateCount, elapsed });
        }
      }
    };

    // ========== 阶段 8: ICE 连接状态跟踪 ==========
    pc.oniceconnectionstatechange = async () => {
      const state = pc.iceConnectionState;
      const elapsed = Date.now() - iceStartTime;
      console.info("[Avatar] ICE state: %s (%dms)", state, elapsed);

      if (state === "failed") {
        console.error("[Avatar] ❌ ICE connection FAILED — WebRTC 无法建立");
        reportToBackend("avatar_ice_failed", {
          elapsed,
          candidateCount,
          // 收集最终的连接统计
          stats: await getConnectionStats(pc),
        });
      }

      if (state === "connected") {
        console.info("[Avatar] ✅ ICE connected! WebRTC 通道已建立");
        reportToBackend("avatar_connected", { elapsed, candidateCount });
      }
    };

    // ========== 阶段 9: Track 接收 ==========
    const tracksReceived = { video: false, audio: false };
    pc.ontrack = (event) => {
      tracksReceived[event.track.kind as "video" | "audio"] = true;
      console.info("[Avatar] Track received: %s (id=%s)",
        event.track.kind, event.track.id);

      // 监听 track 结束/静音
      event.track.onended = () => {
        console.warn("[Avatar] ⚠️ Track ended: %s", event.track.kind);
        reportToBackend("avatar_track_ended", { kind: event.track.kind });
      };
      event.track.onmute = () => {
        console.warn("[Avatar] ⚠️ Track muted: %s", event.track.kind);
      };
      event.track.onunmute = () => {
        console.info("[Avatar] Track unmuted: %s", event.track.kind);
      };

      if (event.track.kind === "video" && videoRef.current) {
        videoRef.current.srcObject = event.streams[0];
        videoRef.current.play()
          .then(() => console.info("[Avatar] ✅ Video playing"))
          .catch((err) => {
            // ========== 阶段 10: play() 失败诊断 ==========
            console.error("[Avatar] ❌ Video play() failed:", err.name, err.message);
            reportToBackend("avatar_play_failed", {
              error: err.name,
              message: err.message,
              // 常见原因：
              // NotAllowedError → autoplay policy（用户没交互过页面）
              // AbortError → srcObject 在 play 前被清空
              // NotSupportedError → 编码不支持
            });
          });
      }
    };

    // ... SDP 交换等后续代码 ...
  };
}

// 上报到后端的通用函数
async function reportToBackend(event: string, data: Record<string, unknown>) {
  try {
    await fetch("/api/v1/diagnostics/avatar", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${getToken()}`,
      },
      body: JSON.stringify({
        event,
        timestamp: new Date().toISOString(),
        userAgent: navigator.userAgent,
        ...data,
      }),
    });
  } catch {
    // 诊断上报失败不应影响主流程
  }
}
```

注意 `reportToBackend` 函数的设计：诊断上报使用 `try/catch` 包裹，确保上报失败不会影响主业务流程。

### 后端诊断日志

后端同样需要在关键环节记录日志，尤其是 Azure SDK 事件的处理过程：

```python
# backend/app/services/voice_live_websocket.py — 后端关键埋点（示例）

@router.websocket("/ws")
async def voice_live_ws(ws: WebSocket, token: str = Query(...)):
    session_id = str(uuid4())
    user = await verify_token(token)

    logger.info("[VL:%s] Session start, user=%s", session_id, user.id)

    try:
        azure_client = await connect_voice_live(
            endpoint=settings.voice_live_endpoint,
            credential=get_credential(),
            agent_name=settings.hosted_agent_name,
            project_name=settings.foundry_project_name,
        )
        logger.info("[VL:%s] Azure SDK connected", session_id)

        async for event in azure_client:
            event_type = event.get("type", "unknown")

            # 关键事件记录
            if event_type == "session.updated":
                ice_servers = event.get("session", {}).get("avatar", {}).get("ice_servers", [])
                logger.info("[VL:%s] session.updated, ice_servers=%d",
                    session_id, len(ice_servers))

                if len(ice_servers) == 0:
                    logger.error("[VL:%s] ❌ No ice_servers in session.updated! "
                        "Avatar 可能未正确配置", session_id)

            elif event_type == "error":
                logger.error("[VL:%s] Azure error: %s", session_id, event)

            # 转发给浏览器
            await ws.send_json(event)

    except WebSocketDisconnect:
        logger.info("[VL:%s] Browser disconnected (normal)", session_id)
    except Exception as e:
        logger.error("[VL:%s] Unexpected error: %s", session_id, e, exc_info=True)
    finally:
        logger.info("[VL:%s] Session end", session_id)
```

后端日志的关键设计原则：每条日志都带有 `session_id` 前缀，便于在大量并发会话中按用户追踪问题。

### WebRTC getStats() API：远程诊断的"X光机"

`pc.getStats()` 是 WebRTC 最强大的诊断工具，返回连接的完整运行时统计信息。掌握这个 API 就等于拥有了远程诊断的"X光机"：

```typescript
// 获取 WebRTC 连接统计信息
async function getConnectionStats(pc: RTCPeerConnection) {
  const stats = await pc.getStats();
  const report: Record<string, unknown> = {};

  stats.forEach((stat) => {
    switch (stat.type) {
      // ========== 1. 候选对（看选了哪条路径） ==========
      case "candidate-pair":
        if (stat.state === "succeeded" || stat.nominated) {
          report.activePair = {
            state: stat.state,
            localCandidateId: stat.localCandidateId,
            remoteCandidateId: stat.remoteCandidateId,
            // 关键指标
            currentRoundTripTime: stat.currentRoundTripTime,  // RTT（秒）
            availableOutgoingBitrate: stat.availableOutgoingBitrate,
            bytesReceived: stat.bytesReceived,
            bytesSent: stat.bytesSent,
          };
        }
        break;

      // ========== 2. 本地候选（看自己的网络出口） ==========
      case "local-candidate":
        if (!report.localCandidates) report.localCandidates = [];
        (report.localCandidates as unknown[]).push({
          type: stat.candidateType,    // "host" / "srflx" / "relay"
          protocol: stat.protocol,     // "udp" / "tcp"
          address: stat.address,       // IP 地址
          port: stat.port,
          relayProtocol: stat.relayProtocol,  // 如果是 relay，用的 udp/tcp/tls
        });
        break;

      // ========== 3. 远端候选（看 Azure 的地址） ==========
      case "remote-candidate":
        if (!report.remoteCandidates) report.remoteCandidates = [];
        (report.remoteCandidates as unknown[]).push({
          type: stat.candidateType,
          protocol: stat.protocol,
          address: stat.address,
          port: stat.port,
        });
        break;

      // ========== 4. 入站视频流（核心诊断数据） ==========
      case "inbound-rtp":
        if (stat.kind === "video") {
          report.videoInbound = {
            framesReceived: stat.framesReceived,     // 收到多少帧
            framesDecoded: stat.framesDecoded,       // 解码了多少帧
            framesDropped: stat.framesDropped,       // 丢弃了多少帧
            frameWidth: stat.frameWidth,             // 视频宽度
            frameHeight: stat.frameHeight,           // 视频高度
            framesPerSecond: stat.framesPerSecond,   // 实时帧率
            bytesReceived: stat.bytesReceived,       // 总接收字节
            packetsReceived: stat.packetsReceived,   // 总接收包数
            packetsLost: stat.packetsLost,           // 丢包数
            jitter: stat.jitter,                     // 抖动（秒）
            // 丢包率计算
            packetLossRate: stat.packetsLost /
              (stat.packetsReceived + stat.packetsLost) * 100,
          };
        }
        if (stat.kind === "audio") {
          report.audioInbound = {
            packetsReceived: stat.packetsReceived,
            packetsLost: stat.packetsLost,
            jitter: stat.jitter,
            bytesReceived: stat.bytesReceived,
          };
        }
        break;

      // ========== 5. 传输层（DTLS 状态） ==========
      case "transport":
        report.transport = {
          dtlsState: stat.dtlsState,          // "connected" = 加密通道正常
          iceState: stat.iceState,             // "connected" = ICE 正常
          selectedCandidatePairChanges: stat.selectedCandidatePairChanges,
          bytesReceived: stat.bytesReceived,
          bytesSent: stat.bytesSent,
        };
        break;
    }
  });

  return report;
}
```

### getStats() 指标解读

采集到统计数据后，需要知道每个指标的含义和正常/异常范围：

```
┌─────────────────────┬────────────────────────────────────────────────┐
│ 指标                 │ 诊断意义                                        │
├─────────────────────┼────────────────────────────────────────────────┤
│ activePair.          │ < 100ms = 优秀（可能是直连）                    │
│ currentRoundTripTime│ 100-300ms = 正常（可能走了 TURN）               │
│                     │ > 500ms = 网络质量差，可能导致口型不同步          │
├─────────────────────┼────────────────────────────────────────────────┤
│ localCandidate.type │ "host" = 直连（最快）                           │
│                     │ "srflx" = STUN 穿透成功                         │
│                     │ "relay" = 走了 TURN 中继                        │
│                     │ → 如果是 relay，检查 relayProtocol               │
│                     │   "udp" = TURN/UDP（性能好）                    │
│                     │   "tcp" = TURN/TCP（UDP 被封了）                │
│                     │   "tls" = TURN/TLS（最后手段）                  │
├─────────────────────┼────────────────────────────────────────────────┤
│ videoInbound.        │ 25-30 = 正常                                   │
│ framesPerSecond     │ 10-20 = 网络波动，体验下降                      │
│                     │ < 5 = 严重问题                                  │
│                     │ 0 = 完全没收到视频帧                             │
├─────────────────────┼────────────────────────────────────────────────┤
│ videoInbound.        │ < 1% = 优秀                                    │
│ packetLossRate      │ 1-5% = 可接受，WebRTC 可以补偿                  │
│                     │ > 5% = 画面会卡顿                               │
│                     │ > 15% = 画面基本不可用                           │
├─────────────────────┼────────────────────────────────────────────────┤
│ videoInbound.        │ framesReceived > 0 但 framesDecoded = 0        │
│ framesDropped       │ → 解码失败（编码格式不支持？硬件加速异常？）      │
│                     │ framesDropped 持续增长                           │
│                     │ → 设备性能不足，来不及解码                       │
├─────────────────────┼────────────────────────────────────────────────┤
│ transport.dtlsState │ "connected" = 正常                              │
│                     │ "failed" = DTLS 握手失败（指纹不匹配？）         │
│                     │ "closed" = 连接已关闭                            │
├─────────────────────┼────────────────────────────────────────────────┤
│ bytesReceived       │ 持续增长 = 数据在流动                            │
│ (transport 级别)    │ 停止增长 = 连接可能已断                          │
│                     │ 始终为 0 = 从未连通过                            │
└─────────────────────┴────────────────────────────────────────────────┘
```

### 定期采集 + 上报机制

诊断不能只依赖问题发生时的快照，还需要持续的统计采集来发现渐进式的性能劣化：

```typescript
// 每 10 秒采集一次 WebRTC 统计，上报到后端
function startStatsReporting(pc: RTCPeerConnection, sessionId: string) {
  const interval = setInterval(async () => {
    if (pc.connectionState === "closed") {
      clearInterval(interval);
      return;
    }

    const stats = await getConnectionStats(pc);

    // 本地打印（用户打开 F12 时能看到）
    console.debug("[Avatar Stats]", stats);

    // 异常检测 + 上报
    const video = stats.videoInbound as any;
    if (video) {
      if (video.framesPerSecond === 0 && video.framesReceived > 0) {
        console.warn("[Avatar] ⚠️ Video stalled: receiving packets but 0 fps");
        reportToBackend("avatar_video_stalled", stats);
      }
      if (video.packetLossRate > 10) {
        console.warn("[Avatar] ⚠️ High packet loss: %.1f%%", video.packetLossRate);
        reportToBackend("avatar_high_packet_loss", stats);
      }
    }

    // 定期上报（采样率降低，避免打爆后端）
    // 每分钟上报一次完整统计
    if (Date.now() % 60000 < 10000) {
      reportToBackend("avatar_periodic_stats", stats);
    }
  }, 10_000);

  return () => clearInterval(interval);
}
```

这段代码实现了两层策略：异常事件（帧率为零、高丢包）立即上报，正常统计则每分钟采样一次以避免给后端带来过大压力。

### 完整的远程诊断流程

当用户报告"数字人不出来"时，按照以下流程逐步排查：

```
用户报告"数字人不出来"
  │
  ▼
Step 1: 检查后端日志
  │ 搜索该用户 session_id 的日志
  │
  ├── session.updated 中没有 ice_servers？
  │   → Azure Avatar 功能未启用，或模型不支持 avatar
  │   → 检查 Azure AI Foundry 中的 modalities 配置
  │
  ├── session.updated 正常？
  │   → 继续看前端日志
  │
  ▼
Step 2: 检查前端诊断上报（/api/v1/diagnostics/avatar）
  │
  ├── avatar_no_ice_servers？
  │   → 同上，Azure 配置问题
  │
  ├── avatar_no_relay_candidates？
  │   → ICE gathering 没收集到 relay candidate
  │   → TURN 服务器不可达（凭据过期？DNS 解析失败？）
  │
  ├── avatar_ice_failed？
  │   → ICE 连通性检测全部失败
  │   → 企业防火墙可能封了 UDP 和非标准端口
  │   → 检查 stats 中的 candidateCount：
  │     如果只有 host，没有 srflx 和 relay → STUN/TURN 都不可达
  │     如果有 relay 但 ICE 仍 failed → TURN 中继也不通（极端网络环境）
  │
  ├── avatar_play_failed + NotAllowedError？
  │   → 浏览器 autoplay policy 阻止了视频播放
  │   → 用户需要先和页面交互（点击按钮）才能播放
  │   → 解决：在"开始对话"按钮的 click 事件中触发 WebRTC 连接
  │
  ├── avatar_connected 但没有 avatar_video_stalled？
  │   → WebRTC 连接成功但没有收到视频帧
  │   → 可能是 Azure Avatar 渲染服务内部问题
  │
  ├── avatar_periodic_stats 显示 framesReceived > 0 但 framesPerSecond = 0？
  │   → 收到了数据但解码失败
  │   → 可能是浏览器不支持该编码格式（极少见）
  │   → 检查用户的浏览器版本
  │
  ▼
Step 3: 如果上述都正常，请用户提供 chrome://webrtc-internals
  │
  └── 这是 Chrome 内置的 WebRTC 详细诊断页面
      用户在浏览器地址栏输入 chrome://webrtc-internals
      → 截图发给你
      → 包含所有 ICE candidate、SDP 原文、连接状态时间线
      → 这是终极诊断工具
```

### chrome://webrtc-internals 能看到什么？

当前端日志和后端日志都无法定位问题时，`chrome://webrtc-internals` 是最后的终极武器：

```
这个页面（Chrome 内置，不需要安装任何东西）显示：

1. 所有 RTCPeerConnection 实例
   → 确认 PC 是否被创建了

2. 完整的 SDP Offer 和 Answer 原文
   → 检查有没有 candidate 行
   → 检查编码格式是否正确（H.264/Opus）
   → 检查 fingerprint 是否存在

3. ICE candidate 收集过程
   → 每个 candidate 的类型、地址、优先级
   → gathering 起止时间

4. ICE 连通性检测的详细日志
   → 每对 candidate pair 的探测结果
   → 哪些成功、哪些失败、选中了哪一对

5. 实时统计图表
   → 接收码率（bytes/sec）
   → 帧率
   → 丢包率
   → RTT

用法：
  让用户在报告问题时，同时打开 chrome://webrtc-internals
  重现问题后，点击页面上的 "Create Dump" 按钮
  把生成的 JSON 文件发给你
  → 包含诊断所需的一切信息
```

### 诊断决策树总结

最后，将完整的诊断流程浓缩为一棵决策树，方便快速查阅：

```
数字人不出来
  │
  ├── 后端有 session.updated + ice_servers？
  │   ├── 没有 → Azure 配置问题（modalities 未含 avatar）
  │   └── 有 ↓
  │
  ├── 前端有 ICE candidates？
  │   ├── 0 个 → ICE servers 配置错误（凭据过期/DNS 失败）
  │   ├── 只有 host → STUN/TURN 不可达（网络问题）
  │   └── 有 relay ↓
  │
  ├── ICE connectionState？
  │   ├── "checking" 卡住 → 所有路径都不通（严格防火墙）
  │   ├── "failed" → 网络完全不可达
  │   └── "connected" ↓
  │
  ├── ontrack 触发了？
  │   ├── 没有 → Azure Avatar 服务端问题（未开始推流）
  │   └── 有 ↓
  │
  ├── framesReceived > 0？
  │   ├── 0 → 媒体流未到达（中间网络问题）
  │   └── > 0 ↓
  │
  ├── video.play() 成功？
  │   ├── NotAllowedError → autoplay policy（需要用户交互）
  │   ├── AbortError → srcObject 被提前清空（竞态条件）
  │   └── 成功 ↓
  │
  └── 视频应该在播放了
      如果用户仍然看不到 → 检查 CSS（opacity? z-index? display?）
```

### 远程诊断小结

远程诊断"数字人不出来"需要三层日志体系：

1. **前端埋点**：WebRTC 状态机的每一步转换
2. **后端日志**：Azure SDK 事件和 session 生命周期
3. **WebRTC getStats()**：定期采集连接质量、丢包率、帧率等运行时指标

配合 `chrome://webrtc-internals` 的 dump 文件，可以在不到现场的情况下精确定位问题环节。关键设计原则：每个可能失败的环节都要有日志，日志要包含足够的上下文（时间戳、候选类型、状态值），异常检测要主动上报而不是等用户反馈。

---

## 本章小结

生产环境运维的三个核心问题——文字语音同步、并发扩容、远程诊断——分别对应"体验优化""容量规划""故障排查"三个不同的运维维度。文字语音同步问题的最佳解法是"延迟显示 + 打字机效果"这种低成本高收益的组合，而不是追求理论完美的时间戳对齐；扩容问题在当前规模下（100 并发）完全在 Python asyncio 的舒适区，真正的瓶颈更可能出现在网络带宽和 Azure API 配额上；远程诊断问题的关键在于提前埋点，覆盖从 ICE 协商到播放的全链路，才能在生产故障发生时快速定位根因，而不是依赖用户的模糊描述。

---

> 返回 [文档目录](./00-index.md) | 相关：[09-websocket-webrtc-protocol.md](./09-websocket-webrtc-protocol.md) · [10-nat-traversal.md](./10-nat-traversal.md) · [12-frontend-deep-dive.md](./12-frontend-deep-dive.md)
