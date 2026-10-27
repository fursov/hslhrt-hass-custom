"""Exercise configuration and options flows through HA's real flow managers."""

from unittest.mock import AsyncMock

import pytest

from homeassistant.data_entry_flow import FlowResultType, InvalidData

from custom_components.hslhrt.const import DOMAIN


@pytest.mark.asyncio
async def test_config_flow_selects_correct_stop(hass, mock_digitransit):
    """A name matching opposite-side platforms must expose a real selector."""
    first = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert first["type"] is FlowResultType.FORM
    assert first["step_id"] == "user"

    selection = await hass.config_entries.flow.async_configure(
        first["flow_id"],
        user_input={
            "user_name_code": "Example",
            "route": "ALL",
            "destination": "ALL",
            "api_key": "TEST-KEY",
        },
    )
    assert selection["type"] is FlowResultType.FORM
    assert selection["step_id"] == "select_stop"

    result = await hass.config_entries.flow.async_configure(
        selection["flow_id"], user_input={"selected_stop": "HSL:1000"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["stop_gtfs"] == "HSL:1000"
    assert result["data"]["stop_code"] == "E4971"


@pytest.mark.asyncio
async def test_public_stop_code_flow_skips_picker(hass, mock_digitransit):
    """A precise E4971 code must not accidentally select E4972."""
    start = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        start["flow_id"],
        user_input={
            "user_name_code": "E4971",
            "route": "8",
            "destination": "ALL",
            "api_key": "TEST-KEY",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["stop_gtfs"] == "HSL:1000"


@pytest.mark.asyncio
async def test_options_flow_persists_filter_without_changing_unique_id(
    hass, make_entry, mock_digitransit
):
    """The real HA OptionsFlow manager should retain legacy entry identity."""
    entry = make_entry()
    entry.add_to_hass(hass)
    before = entry.unique_id

    first = await hass.config_entries.options.async_init(entry.entry_id)
    assert first["type"] is FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        first["flow_id"],
        user_input={
            "routes_filter": ["2", "8"],
            "destination_filter": "ALL",
            "scan_interval": 5,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.unique_id == before
    assert entry.options["routes_filter"] == ["2", "8"]
    assert entry.options["scan_interval"] == 5



@pytest.mark.asyncio
async def test_compact_hfp_options_use_real_ha_dropdown_and_store_ints(
    hass, make_entry, mock_digitransit
):
    """SelectSelector's string values must not change persisted HFP types."""
    from homeassistant.helpers.selector import SelectSelector, SelectSelectorMode

    entry = make_entry(options={
        "track_vehicles": True,
        "tracking_horizon_minutes": 45,
        "tracking_per_route": 3,
    })
    entry.add_to_hass(hass)
    first = await hass.config_entries.options.async_init(entry.entry_id)
    assert first["type"] is FlowResultType.FORM
    fields = {
        key.schema: (key.default(), validator)
        for key, validator in first["data_schema"].schema.items()
    }
    for field, old_value, expected_options in (
        ("tracking_horizon_minutes", "45", ["15", "30", "45", "60", "90"]),
        ("tracking_per_route", "3", ["1", "2", "3", "4", "5"]),
        ("map_stop_departures", "5", [str(i) for i in range(1, 11)]),
    ):
        default, validator = fields[field]
        assert default == old_value
        assert isinstance(validator, SelectSelector)
        assert validator.config["mode"] == SelectSelectorMode.DROPDOWN
        assert validator.config["options"] == expected_options

    result = await hass.config_entries.options.async_configure(
        first["flow_id"],
        user_input={
            "routes_filter": ["8"],
            "destination_filter": "ALL",
            "scan_interval": 5,
            "track_vehicles": True,
            "tracking_horizon_minutes": "60",
            "tracking_per_route": "4",
            "map_stop_departures": "7",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["tracking_horizon_minutes"] == 60
    assert entry.options["tracking_per_route"] == 4
    assert entry.options["map_stop_departures"] == 7
    assert type(entry.options["map_stop_departures"]) is int
    assert type(entry.options["tracking_horizon_minutes"]) is int
    assert type(entry.options["tracking_per_route"]) is int
    assert entry.unique_id == "HSL:1000 8"



@pytest.mark.asyncio
async def test_stop_map_departure_options_validate_and_default(
    hass, make_entry, mock_digitransit
):
    """Old entries default to five departures; invalid new values are rejected."""
    entry = make_entry()
    entry.add_to_hass(hass)
    first = await hass.config_entries.options.async_init(entry.entry_id)
    assert first["type"] is FlowResultType.FORM
    fields = {
        key.schema: key.default()
        for key in first["data_schema"].schema
    }
    assert fields["map_stop_departures"] == "5"

    # The real HA flow manager rejects values not allowed by the selector
    # before invoking our async_step_init validation.
    with pytest.raises(InvalidData, match="map_stop_departures"):
        await hass.config_entries.options.async_configure(
            first["flow_id"],
            user_input={
                "routes_filter": ["8"],
                "destination_filter": "ALL",
                "scan_interval": 5,
                "map_stop_departures": "11",
            },
        )
    assert entry.options == {}

    saved = await hass.config_entries.options.async_configure(
        first["flow_id"],
        user_input={
            "routes_filter": ["8"],
            "destination_filter": "ALL",
            "scan_interval": 5,
            "map_stop_departures": "3",
        },
    )
    assert saved["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["map_stop_departures"] == 3
    assert entry.unique_id == "HSL:1000 8"


@pytest.mark.asyncio
@pytest.mark.parametrize("route_value", ["8, 2", "8 2", "8,2", "2,8  2"])
async def test_initial_multi_route_setup_uses_one_canonical_entry(
    hass, mock_digitransit, route_value
):
    """Multiple text separators produce one stable config entry/unique ID."""
    initial = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        initial["flow_id"],
        user_input={
            "user_name_code": "E4971",
            "route": route_value,
            "destination": "ALL",
            "api_key": "TEST-KEY",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["route"] == "2,8"
    assert result["result"].unique_id == "HSL:1000 2,8"
    assert result["result"].title.endswith("2,8")
    assert result["result"].options == {}

    # Existing dropdown options must automatically preselect all routes.
    options = await hass.config_entries.options.async_init(
        result["result"].entry_id
    )
    assert options["type"] is FlowResultType.FORM
    fields = {
        field.schema: field.default()
        for field in options["data_schema"].schema
    }
    assert fields["routes_filter"] == ["2", "8"]


@pytest.mark.asyncio
@pytest.mark.parametrize("route_value", ["8,missing", "2 999", "ALL,8", "all 2", ",,"])
async def test_initial_multi_route_setup_rejects_unavailable_or_mixed_all(
    hass, mock_digitransit, route_value
):
    """Reject invalid setup input rather than partially configuring routes."""
    initial = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        initial["flow_id"],
        user_input={
            "user_name_code": "E4971",
            "route": route_value,
            "destination": "ALL",
            "api_key": "TEST-KEY",
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"].get("base") == "invalid_route" or (
        result["errors"].get("route") == "invalid_route"
    )
