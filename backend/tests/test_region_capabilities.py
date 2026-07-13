"""Tests for region capabilities lookup module."""

from app.services.region_capabilities import (
    ALL_SERVICE_NAMES,
    AVATAR_REGIONS,
    LAST_VERIFIED,
    VOICE_LIVE_REGIONS,
    get_region_capabilities,
)


class TestGetRegionCapabilities:
    """Tests for get_region_capabilities function."""

    def test_get_region_capabilities_eastus2(self):
        """eastus2 has avatar and voice live available."""
        result = get_region_capabilities("eastus2")
        assert result["region"] == "eastus2"
        services = result["services"]

        # Avatar should be available in eastus2
        assert services["azure_avatar"]["available"] is True

        # Voice Live should be available with agent mode
        assert services["azure_voice_live"]["available"] is True
        assert "Agent and Model modes" in services["azure_voice_live"]["note"]

        # OpenAI is unrestricted
        assert services["azure_openai"]["available"] is True

    def test_get_region_capabilities_westus(self):
        """westus has voice live but not avatar."""
        result = get_region_capabilities("westus")
        services = result["services"]

        # westus is NOT in AVATAR_REGIONS
        assert services["azure_avatar"]["available"] is False

        # westus IS in VOICE_LIVE_REGIONS
        assert services["azure_voice_live"]["available"] is True

    def test_get_region_capabilities_unknown(self):
        """Unknown region: unrestricted services available, restricted unavailable."""
        result = get_region_capabilities("unknown-region")
        services = result["services"]

        # Unrestricted services always available
        assert services["azure_openai"]["available"] is True
        assert services["azure_speech_stt"]["available"] is True
        assert services["azure_content"]["available"] is True

        # Restricted services unavailable in unknown region
        assert services["azure_avatar"]["available"] is False
        assert services["azure_voice_live"]["available"] is False

    def test_get_region_capabilities_case_insensitive(self):
        """Case-insensitive region matching."""
        result_lower = get_region_capabilities("eastus2")
        result_mixed = get_region_capabilities("EastUS2")

        # Both should return same availability
        for service_name in ALL_SERVICE_NAMES:
            assert (
                result_lower["services"][service_name]["available"]
                == result_mixed["services"][service_name]["available"]
            ), f"Mismatch for {service_name}"

    def test_all_service_names_in_result(self):
        """All 8 services are present in result."""
        result = get_region_capabilities("eastus2")
        services = result["services"]
        assert len(services) == 8
        for name in ALL_SERVICE_NAMES:
            assert name in services, f"Missing service: {name}"

    def test_voice_live_not_available_note(self):
        """Unsupported region gets 'Not available' note for voice live."""
        result = get_region_capabilities("antarcticanorth")
        assert "Not available" in result["services"]["azure_voice_live"]["note"]

    def test_avatar_not_available_shows_regions(self):
        """Unsupported avatar region shows available regions hint."""
        result = get_region_capabilities("westus")
        note = result["services"]["azure_avatar"]["note"]
        assert "Available in" in note

    def test_preserves_original_region_string(self):
        """Result includes original region string, not lowered."""
        result = get_region_capabilities("SwedenCentral")
        assert result["region"] == "SwedenCentral"

    def test_whitespace_trimmed(self):
        """Leading/trailing whitespace is trimmed."""
        result = get_region_capabilities("  eastus2  ")
        assert result["services"]["azure_avatar"]["available"] is True


class TestRegionConstants:
    """Tests for region constant sets."""

    def test_avatar_regions_count(self):
        """AVATAR_REGIONS has exactly 7 entries."""
        assert len(AVATAR_REGIONS) == 7

    def test_voice_live_regions_count(self):
        """VOICE_LIVE_REGIONS has at least 20 entries."""
        assert len(VOICE_LIVE_REGIONS) >= 20

    def test_last_verified_date_exists(self):
        """LAST_VERIFIED is a non-empty string."""
        assert isinstance(LAST_VERIFIED, str)
        assert len(LAST_VERIFIED) > 0

    def test_swedencentral_in_all_region_sets(self):
        """swedencentral supports all region-restricted services."""
        assert "swedencentral" in AVATAR_REGIONS
        assert "swedencentral" in VOICE_LIVE_REGIONS

    def test_all_service_names_count(self):
        """ALL_SERVICE_NAMES has 8 entries."""
        assert len(ALL_SERVICE_NAMES) == 8
