"""Validate the documented dashboard cards against real HA template helpers.

Do not silently publish obsolete or syntactically invalid YAML cards again.
The examples intentionally use a configurable, user-replaceable entity ID.
"""

import re
from pathlib import Path

import pytest
import yaml

from homeassistant.helpers.template import Template

from custom_components.hslhrt.const import (
    ATTR_ARR_TIME,
    ATTR_DEST,
    ATTR_ROUTE,
    ATTR_STOP_CODE,
    ATTR_STOP_NAME,
)

ROOT = Path(__file__).resolve().parents[2]
ENTITY = "sensor.eestinmalmintie_e4971_all"


def documented_cards() -> list[dict]:
    dashboard = (ROOT / "docs" / "dashboard-examples.md").read_text(
        encoding="utf-8"
    )
    yaml_blocks = re.findall(r"```yaml\n(.*?)\n```", dashboard, re.DOTALL)
    assert len(yaml_blocks) == 6  # Six native dashboard examples.
    return [yaml.safe_load(block) for block in yaml_blocks]


def test_all_documented_yaml_cards_parse_and_use_real_ha_schemas():
    cards = documented_cards()
    assert all(isinstance(card, dict) and card.get("type") in
               {"entities", "markdown", "map"} for card in cards)
    assert sum(card["type"] == "map" for card in cards) == 1
    assert sum(card["type"] == "markdown" for card in cards) == 2
    known_attributes = {
        ATTR_STOP_NAME, ATTR_STOP_CODE, ATTR_ROUTE, ATTR_DEST, ATTR_ARR_TIME,
        "hfp_connected", "selected_journeys",
    }
    for card in cards:
        for row in card.get("entities", []):
            if row.get("type") == "attribute":
                assert row["attribute"] in known_attributes
                assert row["entity"].startswith(ENTITY)
    for card in cards:
        if card["type"] == "map":
            assert card["geo_location_sources"] == [
                {
                    "source": "hslhrt",
                    "label_mode": "attribute",
                    "attribute": "marker_label",
                },
                {
                    "source": "hslhrt_stops",
                    "label_mode": "icon",
                },
            ]
            assert card["auto_fit"] is True



def test_optional_custom_map_examples_parse_and_keep_sources_distinct():
    """Catch invalid optional frontend YAML without loading custom cards in CI."""
    guide = (ROOT / "docs" / "custom-map.md").read_text(encoding="utf-8")
    yaml_blocks = re.findall(r"```yaml\n(.*?)\n```", guide, re.DOTALL)
    assert len(yaml_blocks) == 3
    dynamic_map, popup_button, native_map = [
        yaml.safe_load(block) for block in yaml_blocks
    ]
    assert dynamic_map["type"] == "custom:auto-entities"
    assert dynamic_map["card"]["type"] == "custom:map-card"
    assert [
        item["attributes"]["source"]
        for item in dynamic_map["filter"]["include"]
    ] == ["hslhrt", "hslhrt_stops"]
    assert popup_button["type"] == "button"
    popup = popup_button["tap_action"]["browser_mod"]["data"]
    assert popup["content"]["card"]["type"] == "custom:map-card"
    assert native_map["type"] == "map"
    assert [
        item["source"] for item in native_map["geo_location_sources"]
    ] == ["hslhrt", "hslhrt_stops"]


@pytest.mark.asyncio
async def test_documented_markdown_templates_render_with_real_ha(
    hass,
):
    """Modern documented markdown works without extra template sensors."""
    hass.states.async_set(
        ENTITY,
        "533",
        {
            "departures": [
                {
                    "route": "533",
                    "destination": "Helsinki",
                    "arrival_datetime": "2026-10-23T10:31:00+00:00",
                    "realtime": True,
                },
                {
                    "route": "236",
                    "destination": "Espoo",
                    "arrival_datetime": "2026-10-23T10:35:00+00:00",
                    "realtime": False,
                },
            ]
        },
    )
    hass.states.async_set(f"{ENTITY}_minutes_until_arrival", "7")
    markdown = [card for card in documented_cards() if card["type"] == "markdown"]
    for card in markdown:
        rendered = Template(card["content"], hass).async_render(
            parse_result=False
        )
        assert "533" in rendered
        assert "Helsinki" in rendered
        assert "unknown" not in rendered
        assert "No upcoming departures" not in rendered
    assert "7 min" in Template(markdown[0]["content"], hass).async_render(
        parse_result=False
    )
    table = Template(markdown[1]["content"], hass).async_render(
        parse_result=False
    )
    assert "| 533 | Helsinki |" in table
    assert "| 236 | Espoo |" in table
    assert "Realtime" in table and "Scheduled" in table


@pytest.mark.asyncio
async def test_documented_markdown_templates_handle_no_departures(hass):
    """Unknown/unavailable stops must not raise template exceptions."""
    for card in documented_cards():
        if card["type"] == "markdown":
            output = Template(card["content"], hass).async_render(
                parse_result=False
            )
            assert "No upcoming departures" in output


def test_legacy_ui_screenshots_are_not_presented_as_current():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    dashboard = (ROOT / "docs" / "dashboard-examples.md").read_text(
        encoding="utf-8"
    )
    archive = (ROOT / "docs" / "legacy-ui-examples.md").read_text(
        encoding="utf-8"
    )
    assert "# Dashboard examples" in dashboard
    assert "docs/dashboard-examples.md" in readme
    assert "```yaml\nplatform: template" not in dashboard
    assert "timedelta.seconds" not in dashboard
    assert "Template Sensor for next 4 routes" not in dashboard
    for number in range(1, 5):
        name = f"ui-option-{number}.jpg"
        path = ROOT / "resources" / "images" / name
        assert path.is_file() and path.stat().st_size > 1_000
        raw = path.read_bytes()
        assert raw.startswith(bytes((0xFF, 0xD8))) and raw.endswith(bytes((0xFF, 0xD9)))
        assert name in archive and name not in readme
    assert "not" in archive.lower() and "historical" in archive.lower()


@pytest.mark.asyncio
async def test_flow_field_labels_are_available_in_ha_english_translations(hass):
    """Every field in the user screenshots has an actual localized label."""
    from homeassistant.helpers.translation import async_get_translations

    for section, expected in {
        "config": {
            "component.hslhrt.config.step.user.data.user_name_code":
                "Stop name or code",
            "component.hslhrt.config.step.select_stop.data.selected_stop":
                "Stop",
        },
        "options": {
            "component.hslhrt.options.step.init.data.routes_filter":
                "Routes (empty = all)",
            "component.hslhrt.options.step.init.data.track_vehicles":
                "Track GPS positions of upcoming vehicles (HFP)",
            "component.hslhrt.options.step.init.data.tracking_horizon_minutes":
                "GPS tracking lookahead (minutes)",
            "component.hslhrt.options.step.init.data.tracking_per_route":
                "Upcoming trips to track per route",
            "component.hslhrt.options.step.init.data.map_stop_departures":
                "Upcoming departures shown when tapping a map stop",
        },
    }.items():
        translations = await async_get_translations(hass, "en", section, {"hslhrt"})
        for key, expected_label in expected.items():
            assert translations.get(key) == expected_label, key


def test_current_ui_screenshots_exist_and_are_linked():
    """Existing real HA screenshots remain linked from their topic guides."""
    config = (ROOT / "docs" / "configuration.md").read_text(encoding="utf-8")
    dashboard = (ROOT / "docs" / "dashboard-examples.md").read_text(
        encoding="utf-8"
    )
    screenshots = (
        "configure-stop.png",
        "select-stop.png",
        "stop-options-compact.png",
        "sensor-state-history.png",
    )
    for filename in screenshots:
        relative_path = f"resources/images/{filename}"
        guide = dashboard if filename == "sensor-state-history.png" else config
        assert f"](../{relative_path})" in guide
        path = ROOT / relative_path
        assert path.is_file() and path.stat().st_size > 3_000
        assert path.read_bytes().startswith(bytes((0x89, 0x50, 0x4E, 0x47)))
    assert "stop-options.png" not in config
    assert "Compact GPS preferences" in config
    assert "stop-options-compact.png" in config
    archive = (ROOT / "docs" / "legacy-ui-examples.md").read_text(
        encoding="utf-8"
    )
    assert "stop-options.png" in archive
    assert (ROOT / "resources/images/stop-options.png").is_file()
    assert "API key blank" in config
    assert "not a timetable card" in dashboard.lower()



@pytest.mark.asyncio
async def test_finnish_flow_translations_load_in_real_home_assistant(hass):
    """Finnish labels, errors and messages work through HA's backend API."""
    from homeassistant.helpers.translation import async_get_translations

    for section, expected in {
        "config": {
            "component.hslhrt.config.step.user.data.user_name_code":
                "Pysäkin nimi tai tunnus",
            "component.hslhrt.config.step.select_stop.data.selected_stop":
                "Pysäkki",
            "component.hslhrt.config.error.invalid_api_key":
                "Virheellinen Digitransitin API-avain",
            "component.hslhrt.config.abort.already_configured":
                "Pysäkki ja linja on jo määritetty",
        },
        "options": {
            "component.hslhrt.options.step.init.title":
                "Pysäkin asetukset",
            "component.hslhrt.options.step.init.data.routes_filter":
                "Linjat (tyhjä = kaikki)",
            "component.hslhrt.options.step.init.data.tracking_horizon_minutes":
                "GPS-seurannan aikajänne (minuuttia)",
            "component.hslhrt.options.step.init.data.tracking_per_route":
                "Seurattavien vuorojen määrä linjaa kohti",
            "component.hslhrt.options.step.init.data.map_stop_departures":
                "Karttapysäkin seuraavat lähdöt (määrä)",
            "component.hslhrt.options.error.invalid_selection":
                "Valitse jokin luettelon arvoista",
        },
    }.items():
        translated = await async_get_translations(hass, "fi", section, {"hslhrt"})
        for key, label in expected.items():
            assert translated.get(key) == label, key
