"""Enhanced mock adapter with personality-based template responses."""

import random
from collections.abc import AsyncIterator

from app.services.agents.base import (
    BaseCoachingAdapter,
    CoachEvent,
    CoachEventType,
    CoachRequest,
)

# Template responses organized by personality type and conversation phase
PERSONALITY_TEMPLATES: dict[str, dict[str, list[str]]] = {
    "skeptical": {
        "opening": [
            "我今天很忙。{product}怎么样？",
            "我之前听说过{product}，但目前看到的东西还不够说服我。",
            "我不容易被市场材料说服。请讲吧。",
        ],
        "middle": [
            "这个说法很有意思。你有硬数据吗？",
            "我见过类似的说法。{product}有什么不同？",
            "我的患者目前治疗效果很好。为什么要换？",
            "数据在纸面上看起来不错。真实世界数据呢？",
            "我需要先看头对头比较数据。",
        ],
        "closing": [
            "我会看看数据，但我仍然持怀疑态度。",
            "把发表的研究发给我。我会审查的。",
            "感谢您的认真介绍，但我需要更多证据才会改变我的做法。",
        ],
    },
    "friendly": {
        "opening": [
            "你好！其实我一直对{product}很好奇。",
            "欢迎！我喜欢了解新的选择。跟我说说{product}吧。",
            "很高兴认识你。我愿意听听{product}的情况。",
        ],
        "middle": [
            "有意思！跟我多说说临床试验的情况。",
            "{product}跟我目前在用的相比怎么样？",
            "我的患者可能会受益。安全性怎么样？",
            "说得好。有些患者确实在现有方案上有困难。",
            "疗效数据听起来很有前景。长期结果呢？",
        ],
        "closing": [
            "谢谢。我很有兴趣在一些患者身上试试{product}。",
            "我会考虑在下一个合适的患者上使用{product}。能留些资料吗？",
            "非常有收获。期待了解更多。",
        ],
    },
    "busy": {
        "opening": [
            "我只有几分钟时间。{product}怎么样？",
            "说快点。{product}是什么？",
            "我在两个患者之间。关于{product}请简短说。",
        ],
        "middle": [
            "说重点。",
            "那底线是什么？",
            "快说，关键好处是什么？",
            "我没时间听细节。总结一下？",
            "下一个要点，请。",
        ],
        "closing": [
            "好的，我得走了。把资料留下。",
            "知道了。我以后再看。",
            "时间到了。把要点发邮件给我。",
        ],
    },
    "analytical": {
        "opening": [
            "让我们从数据驱动的角度来讨论{product}。",
            "我注重循证医学。跟我说说{product}吧。",
            "我想了解{product}背后的数字。临床试验显示什么？",
        ],
        "middle": [
            "主要终点的P值是多少？",
            "跟标准治疗相比，NNT是多少？",
            "置信区间呢？有临床意义吗？",
            "研究设计：双盲、随机对照？",
            "效应量跟现有选择比怎么样？",
        ],
        "closing": [
            "统计学上很有意思。我会审查文献的。",
            "把研究方案和结果发给我分析。",
            "数据不错。让我在得出结论之前再看看。",
        ],
    },
    "cautious": {
        "opening": [
            "我对新疗法很谨慎。安全性怎么样？",
            "患者安全是我的首要考虑。我们来讨论{product}的风险。",
            "先跟我说说{product}的不良反应。",
        ],
        "middle": [
            "药物相互作用怎么样？我的患者吃很多药。",
            "有什么上市后安全信号我应该知道的吗？",
            "我担心给稳定的患者换药。",
            "长期安全性数据呢？这些患者需要多年的治疗。",
            "有什么禁忌症我需要注意的吗？",
        ],
        "closing": [
            "我会先从低风险患者谨慎开始。",
            "我需要仔细考虑。患者安全第一。",
            "我会在考虑改变我的实践之前先审查安全性数据。",
        ],
    },
}

# Coaching hint templates
COACHING_HINTS: list[dict[str, str]] = [
    {
        "content": "Try to provide more detailed responses with supporting data.",
        "dimension": "scientific_info",
    },
    {
        "content": "Address the concern before presenting counter-evidence.",
        "dimension": "objection_handling",
    },
    {
        "content": "Good opportunity to deliver a key message.",
        "dimension": "key_message",
    },
    {
        "content": "Adapt your style to match the HCP's preferences.",
        "dimension": "communication",
    },
    {
        "content": "Discuss the mechanism of action for deeper knowledge.",
        "dimension": "product_knowledge",
    },
]


class MockCoachingAdapter(BaseCoachingAdapter):
    """Mock adapter for development and testing without AI credentials.

    Provides personality-based template responses with conversation phase
    awareness (opening, middle, closing). Yields word chunks for simulated
    streaming and occasional coaching hints.
    """

    name = "mock"

    async def execute(self, request: CoachRequest) -> AsyncIterator[CoachEvent]:
        """Execute a mock coaching interaction."""
        # Fall back to simple response if no HCP profile
        if request.hcp_profile is None:
            yield CoachEvent(
                type=CoachEventType.TEXT,
                content=(
                    "[Mock HCP Response] Thank you for your "
                    "presentation about the treatment. I have "
                    "some concerns about the side effects "
                    "you mentioned. Could you elaborate on "
                    "the long-term safety data?"
                ),
            )
            yield CoachEvent(
                type=CoachEventType.SUGGESTION,
                content=("Try to address safety concerns with specific clinical trial data."),
                metadata={"dimension": "objection_handling"},
            )
            yield CoachEvent(type=CoachEventType.DONE, content="")
            return

        personality = request.hcp_profile.get("personality_type", "friendly")
        product = self._extract_product(request.scenario_context)

        # Determine conversation phase
        phase = self._determine_phase(request.message)

        # Select and personalize response
        response = self._select_response(personality, phase, product)

        # Yield response in word chunks (2-3 words) for streaming
        words = response.split()
        chunk_size = random.randint(2, 3)
        for i in range(0, len(words), chunk_size):
            chunk = " ".join(words[i : i + chunk_size])
            if i + chunk_size < len(words):
                chunk += " "
            yield CoachEvent(type=CoachEventType.TEXT, content=chunk)

        # Occasionally yield a coaching hint (30% chance)
        if random.random() < 0.3:
            hint = random.choice(COACHING_HINTS)
            yield CoachEvent(
                type=CoachEventType.SUGGESTION,
                content=hint["content"],
                metadata={"dimension": hint["dimension"]},
            )

        yield CoachEvent(type=CoachEventType.DONE, content="")

    async def is_available(self) -> bool:
        return True

    async def get_version(self) -> str | None:
        return "mock-2.0"

    def _extract_product(self, scenario_context: str) -> str:
        """Extract product name from scenario context."""
        for line in scenario_context.split("\n"):
            if "Product under discussion:" in line or "presenting about:" in line:
                return line.split(":", 1)[1].strip()
        return "the product"

    def _determine_phase(self, message: str) -> str:
        """Determine conversation phase from message characteristics."""
        lower_msg = message.lower()
        opening_indicators = [
            "hello",
            "hi ",
            "good morning",
            "good afternoon",
            "nice to meet",
            "introduce",
            "i'd like to talk",
            "i'm here to discuss",
            "你好",
            "您好",
            "早上好",
            "下午好",
            "很高兴认识",
            "初次见面",
            "我来介绍",
            "我想跟您聊聊",
        ]
        closing_indicators = [
            "thank you for your time",
            "in summary",
            "to conclude",
            "any final",
            "before i go",
            "last question",
            "wrap up",
            "anything else",
            "感谢您的时间",
            "总结一下",
            "最后",
            "总的来说",
            "我先告辞",
            "还有其他",
            "就到这里",
        ]

        if any(ind in lower_msg for ind in opening_indicators):
            return "opening"
        if any(ind in lower_msg for ind in closing_indicators):
            return "closing"
        return "middle"

    def _select_response(self, personality: str, phase: str, product: str) -> str:
        """Select a personality-appropriate response."""
        templates = PERSONALITY_TEMPLATES.get(personality, PERSONALITY_TEMPLATES["friendly"])
        phase_templates = templates.get(phase, templates["middle"])
        response = random.choice(phase_templates)
        return response.replace("{product}", product)
