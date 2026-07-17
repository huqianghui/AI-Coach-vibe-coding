"""Tests for the enhanced MockCoachingAdapter: personality templates, phase detection, streaming."""

import random

from app.services.agents.adapters.mock import (
    COACHING_HINTS,
    PERSONALITY_TEMPLATES,
    MockCoachingAdapter,
)
from app.services.agents.base import CoachEventType, CoachRequest


class TestExtractProduct:
    """Tests for _extract_product helper."""

    async def test_extracts_product_from_context(self):
        adapter = MockCoachingAdapter()
        context = (
            "# Scenario Context\nProduct under discussion: Brukinsa\nTherapeutic area: Hematology"
        )
        product = adapter._extract_product(context)
        assert product == "Brukinsa"

    async def test_returns_default_when_no_product(self):
        adapter = MockCoachingAdapter()
        product = adapter._extract_product("No product info here")
        assert product == "the product"

    async def test_extracts_from_multiline_context(self):
        adapter = MockCoachingAdapter()
        context = (
            "# HCP Identity\nYou are Dr. Zhang.\n\n"
            "# Scenario Context\n"
            "Product under discussion: Tislelizumab\n"
            "Therapeutic area: Oncology"
        )
        product = adapter._extract_product(context)
        assert product == "Tislelizumab"

    async def test_extracts_product_from_conference_prompt_context(self):
        adapter = MockCoachingAdapter()
        context = "# Presentation Context\nThe Medical Representative is presenting about: Brukinsa"
        product = adapter._extract_product(context)
        assert product == "Brukinsa"


class TestDeterminePhase:
    """Tests for _determine_phase helper."""

    async def test_opening_indicators(self):
        adapter = MockCoachingAdapter()
        assert adapter._determine_phase("Hello, I'm here to discuss") == "opening"
        assert adapter._determine_phase("Good morning doctor") == "opening"
        assert adapter._determine_phase("Nice to meet you") == "opening"
        assert adapter._determine_phase("I'd like to introduce") == "opening"

    async def test_chinese_opening_indicators(self):
        adapter = MockCoachingAdapter()
        assert adapter._determine_phase("你好") == "opening"
        assert adapter._determine_phase("您好，医生") == "opening"
        assert adapter._determine_phase("早上好") == "opening"
        assert adapter._determine_phase("下午好") == "opening"
        assert adapter._determine_phase("很高兴认识您") == "opening"

    async def test_closing_indicators(self):
        adapter = MockCoachingAdapter()
        assert adapter._determine_phase("Thank you for your time") == "closing"
        assert adapter._determine_phase("In summary, the data shows") == "closing"
        assert adapter._determine_phase("To conclude our discussion") == "closing"
        assert adapter._determine_phase("Before I go, any questions?") == "closing"

    async def test_chinese_closing_indicators(self):
        adapter = MockCoachingAdapter()
        assert adapter._determine_phase("感谢您的时间") == "closing"
        assert adapter._determine_phase("总结一下") == "closing"
        assert adapter._determine_phase("就到这里吧") == "closing"
        assert adapter._determine_phase("还有其他问题吗") == "closing"

    async def test_middle_default(self):
        adapter = MockCoachingAdapter()
        assert adapter._determine_phase("What about the safety data?") == "middle"
        assert adapter._determine_phase("Can you tell me more?") == "middle"
        assert adapter._determine_phase("安全性数据怎么样？") == "middle"


class TestSelectResponse:
    """Tests for _select_response helper."""

    async def test_selects_from_correct_personality(self):
        adapter = MockCoachingAdapter()
        # Set seed for deterministic test
        random.seed(42)
        response = adapter._select_response("skeptical", "middle", "Brukinsa")
        # The response should come from skeptical middle templates
        skeptical_middle = PERSONALITY_TEMPLATES["skeptical"]["middle"]
        expected_responses = [t.replace("{product}", "Brukinsa") for t in skeptical_middle]
        assert response in expected_responses

    async def test_replaces_product_placeholder(self):
        adapter = MockCoachingAdapter()
        random.seed(42)
        response = adapter._select_response("friendly", "opening", "TestDrug")
        assert "{product}" not in response
        # The friendly opening templates all contain {product}
        assert "TestDrug" in response

    async def test_unknown_personality_falls_back_to_friendly(self):
        adapter = MockCoachingAdapter()
        random.seed(42)
        response = adapter._select_response("nonexistent", "middle", "Drug")
        friendly_middle = PERSONALITY_TEMPLATES["friendly"]["middle"]
        expected = [t.replace("{product}", "Drug") for t in friendly_middle]
        assert response in expected


class TestExecuteWithHcpProfile:
    """Tests for execute() with a full HCP profile."""

    async def test_yields_text_and_done_events(self):
        adapter = MockCoachingAdapter()
        random.seed(42)
        request = CoachRequest(
            session_id="test",
            message="Tell me about the clinical data",
            scenario_context="Product under discussion: Brukinsa",
            hcp_profile={
                "personality_type": "friendly",
                "name": "Dr. Zhang",
                "specialty": "Oncology",
            },
        )

        events = []
        async for event in adapter.execute(request):
            events.append(event)

        # Should have at least TEXT chunks and DONE
        assert len(events) >= 2
        assert events[-1].type == CoachEventType.DONE

        # All non-DONE/non-SUGGESTION events should be TEXT
        text_events = [e for e in events if e.type == CoachEventType.TEXT]
        assert len(text_events) >= 1

    async def test_text_chunks_form_complete_response(self):
        adapter = MockCoachingAdapter()
        random.seed(42)
        request = CoachRequest(
            session_id="test",
            message="What about safety?",
            scenario_context="Product under discussion: Drug",
            hcp_profile={"personality_type": "skeptical"},
        )

        full_response = ""
        async for event in adapter.execute(request):
            if event.type == CoachEventType.TEXT:
                full_response += event.content

        assert len(full_response.strip()) > 0


class TestExecuteWithoutHcpProfile:
    """Tests for execute() fallback (no HCP profile)."""

    async def test_yields_three_events_without_profile(self):
        adapter = MockCoachingAdapter()
        request = CoachRequest(
            session_id="test",
            message="Hello",
        )

        events = []
        async for event in adapter.execute(request):
            events.append(event)

        assert len(events) == 3
        assert events[0].type == CoachEventType.TEXT
        assert events[1].type == CoachEventType.SUGGESTION
        assert events[2].type == CoachEventType.DONE

    async def test_fallback_text_contains_mock_prefix(self):
        adapter = MockCoachingAdapter()
        request = CoachRequest(session_id="test", message="Hello")

        events = []
        async for event in adapter.execute(request):
            events.append(event)

        assert "[Mock HCP Response]" in events[0].content

    async def test_fallback_suggestion_has_metadata(self):
        adapter = MockCoachingAdapter()
        request = CoachRequest(session_id="test", message="Hello")

        events = []
        async for event in adapter.execute(request):
            events.append(event)

        suggestion = events[1]
        assert suggestion.metadata is not None
        assert "dimension" in suggestion.metadata


class TestCoachingHints:
    """Tests for coaching hint constants."""

    async def test_hints_have_required_fields(self):
        for hint in COACHING_HINTS:
            assert "content" in hint
            assert "dimension" in hint
            assert isinstance(hint["content"], str)
            assert isinstance(hint["dimension"], str)

    async def test_hints_cover_multiple_dimensions(self):
        dimensions = {hint["dimension"] for hint in COACHING_HINTS}
        assert len(dimensions) >= 3  # At least 3 unique dimensions
