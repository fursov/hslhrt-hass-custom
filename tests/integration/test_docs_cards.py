"""Validate user-facing dashboard YAML and templates against Home Assistant.

Core dashboard cards are rendered with HA's real template helpers. Frontend-only
cards (ha-map-card, auto-entities, Browser Mod) are checked structurally.
"""

import re
from pathlib import Path

import pytest
import yaml

from homeassistant.helpers.template import Template

ROOT = Path(__file__).resolve().parents[2]
ENTITY = "sensor.eestinmalmintie_e4971_all"


def documented_cards() -> list[dict]:
    guide = (ROOT / "docs" / "dashboard-examples.md").read_text(
        encoding="utf-8"
    )
    blocks = re.findall(r"```yaml\n(.*?)\n```", guide, re.DOTALL)
    assert len(blocks) == 4  # Four current sensor/dashboard examples.
    return [yaml.safe_load(block) for block in blocks]


def custom_map_examples() -> tuple[dict, dict]:
    """Read the two cooperating cards from the published map guide."""
    guide = (ROOT / "docs" / "custom-map.md").read_text(encoding="utf-8")
    yaml_blocks = re.findall(r"```yaml\n(.*?)\n```", guide, re.DOTALL)
    assert len(yaml_blocks) == 2
    dynamic_map, stop_popup = [yaml.safe_load(block) for block in yaml_blocks]
    return dynamic_map, stop_popup


def test_documented_native_cards_are_valid_yaml():
    cards = documented_cards()
    assert all(isinstance(card, dict) for card in cards)
    assert all(card["type"] in {"entities", "markdown"} for card in cards)
    assert sum(card["type"] == "entities" for card in cards) == 2
    assert sum(card["type"] == "markdown" for card in cards) == 2
    allowed_attributes = {"hfp_connected", "selected_journeys"}
    for card in cards:
        for row in card.get("entities", []):
            if row.get("type") == "attribute":
                assert row["attribute"] in allowed_attributes
                assert row["entity"].startswith(ENTITY)


def test_custom_map_and_browser_mod_popup_config():
    """Test actual demonstrated options, not an unrelated default Map card."""
    map_card, popup = custom_map_examples()
    assert map_card["type"] == "custom:auto-entities"
    assert map_card["card_param"] == "entities"
    assert map_card["show_empty"] is True
    assert map_card["card"]["type"] == "custom:map-card"
    assert map_card["card"]["cluster_markers"] is False
    assert map_card["card"]["card_size"] == 7

    include = map_card["filter"]["include"]
    assert [entry["attributes"]["source"] for entry in include] == [
        "hslhrt_stops", "hslhrt"
    ]
    stops, vehicles = (entry["options"] for entry in include)
    assert stops["display"] == "icon"
    assert stops["icon"] == "mdi:circle"
    assert stops["size"] == 20
    assert stops["color"] == "#58B8E8"
    assert stops["z_index_offset"] == 1
    assert vehicles["display"] == "attribute"
    assert vehicles["attribute"] == "marker_label"
    assert vehicles["size"] == 42
    assert vehicles["color"] == "#2196F3"
    assert vehicles["z_index_offset"] == 100
    assert stops["tap_action"] == {"action": "more-info"}
    assert vehicles["tap_action"] == {"action": "more-info"}

    assert popup["type"] == "custom:popup-card"
    assert len(popup["target"]["entity_id"]) == 2
    assert all(
        entity.startswith("geo_location.hslhrt_stop_")
        for entity in popup["target"]["entity_id"]
    )
    assert popup["popup_card_all_views"] is True
    assert popup["adaptive"] is False
    assert popup["adaptive_allow_mode_change"] is False
    assert popup["card"]["type"] == "markdown"
    content = popup["card"]["content"]
    assert "more_info.entityId" in content
    assert "upcoming_departures_count" in content
    assert "next_departure_" in content


@pytest.mark.asyncio
async def test_browser_mod_stop_popup_renders_multiple_stops(hass):
    """Emulate Browser Mod's entityId substitution before HA template render."""
    _map, popup = custom_map_examples()
    content = popup["card"]["content"]
    stops = (
        ("geo_location.hslhrt_stop_demo1", "Kamppi", "H1234"),
        ("geo_location.hslhrt_stop_demo2", "Hakaniemi", "H5678"),
    )
    for entity, name, code in stops:
        hass.states.async_set(
            entity,
            "0",
            {
                "stop_name": name,
                "stop_code": code,
                "upcoming_departures_count": 2,
                "next_departure_1": "12:31 · 530 → Matinkylä",
                "next_departure_2": "12:38 · 7 → Pasila",
            },
        )
        actual = content.replace("more_info.entityId", entity)
        rendered = Template(actual, hass).async_render(parse_result=False)
        assert f"### {name} ({code})" in rendered
        assert "| 1 | 12:31 · 530 → Matinkylä |" in rendered
        assert "| 2 | 12:38 · 7 → Pasila |" in rendered
        assert "Нет ближайших отправлений" not in rendered


@pytest.mark.asyncio
async def test_browser_mod_stop_popup_handles_no_departures(hass):
    """When zero departures are present, the popup shows a friendly message."""
    _map, popup = custom_map_examples()
    entity = "geo_location.hslhrt_stop_no_departures"
    hass.states.async_set(
        entity, "0",
        {"stop_name": "Kamppi", "stop_code": "H1234",
         "upcoming_departures_count": 0},
    )
    actual = popup["card"]["content"].replace("more_info.entityId", entity)
    rendered = Template(actual, hass).async_render(parse_result=False)
    assert "### Kamppi (H1234)" in rendered
    assert "Нет ближайших отправлений." in rendered
    assert "12:31" not in rendered


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


def test_legacy_examples_are_removed_from_current_guides():
    """Obsolete UI screenshots and examples should not return to the docs."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    dashboard = (ROOT / "docs" / "dashboard-examples.md").read_text(
        encoding="utf-8"
    )
    assert (ROOT / "docs" / "legacy-ui-examples.md").exists() is False
    assert "legacy-ui-examples" not in readme
    assert "# Dashboard examples" in dashboard
    assert "docs/dashboard-examples.md" in readme
    assert "```yaml\nplatform: template" not in dashboard
    assert "timedelta.seconds" not in dashboard
    assert "Template Sensor for next 4 routes" not in dashboard
    for name in (
        "ui-option-1.jpg", "ui-option-2.jpg", "ui-option-3.jpg",
        "ui-option-4.jpg", "stop-options.png",
    ):
        assert not (ROOT / "resources" / "images" / name).exists()


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
