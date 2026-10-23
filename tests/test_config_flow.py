"""Config flow tests with a stub Home Assistant framework and mocked Digitransit."""

import asyncio
import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

INTEGRATION = Path(__file__).resolve().parents[1] / "custom_components" / "hslhrt"


class FakeConfigFlow:
    """Expose the small Home Assistant flow contract under test."""

    def __init_subclass__(cls, **kwargs):
        return super().__init_subclass__()

    def async_show_form(self, **kwargs):
        return {"type": "form", **kwargs}

    def async_create_entry(self, **kwargs):
        return {"type": "create_entry", **kwargs}

    def async_abort(self, **kwargs):
        return {"type": "abort", **kwargs}

    async def async_set_unique_id(self, uid):
        self.unique_id = uid

    def _abort_if_unique_id_configured(self):
        if getattr(self, "already_configured", False):
            raise ValueError("already configured")

    def _get_reauth_entry(self):
        return self.entry

    def _get_reconfigure_entry(self):
        return self.entry

    def _abort_if_unique_id_mismatch(self):
        return None

    def async_update_reload_and_abort(self, entry, **kwargs):
        return {"type": "update", "entry": entry, **kwargs}


class FakeOptionsFlow(FakeConfigFlow):
    pass


STOPS = [
    {"name": "Töölöntori", "code": "H0209", "gtfsId": "HSL:1"},
    {"name": "Töölöntori", "code": "H0210", "gtfsId": "HSL:2"},
]


@pytest.fixture
def flow_module(monkeypatch):
    """Load the actual config flow with minimal Home Assistant service stubs."""
    import voluptuous

    pkg = sys.modules.setdefault("hslhrt", types.ModuleType("hslhrt"))
    pkg.__path__ = [str(INTEGRATION)]

    ha = types.ModuleType("homeassistant")
    ha.__path__ = []
    entries = types.ModuleType("homeassistant.config_entries")
    entries.ConfigFlow = FakeConfigFlow
    entries.OptionsFlow = FakeOptionsFlow
    core = types.ModuleType("homeassistant.core")
    core.callback = lambda fn: fn
    helpers = types.ModuleType("homeassistant.helpers")
    helpers.__path__ = []
    aio = types.ModuleType("homeassistant.helpers.aiohttp_client")
    aio.async_get_clientsession = lambda hass: None
    sel = types.ModuleType("homeassistant.helpers.selector")

    class SelectSelectorMode:
        DROPDOWN = "dropdown"

    class SelectSelectorConfig:
        def __init__(self, **kwargs):
            self.options = kwargs["options"]
            self.multiple = kwargs.get("multiple", False)
            self.mode = kwargs.get("mode")

    class SelectOptionDict(dict):
        def __init__(self, *, value, label):
            super().__init__(value=value, label=label)

    class SelectSelector:
        def __init__(self, conf):
            self.conf = conf

        def __call__(self, value):
            return value

    sel.SelectOptionDict = SelectOptionDict
    sel.SelectSelector = SelectSelector
    sel.SelectSelectorConfig = SelectSelectorConfig
    sel.SelectSelectorMode = SelectSelectorMode
    ha.config_entries = entries
    for name, mod in (
        ("homeassistant", ha),
        ("homeassistant.config_entries", entries),
        ("homeassistant.core", core),
        ("homeassistant.helpers", helpers),
        ("homeassistant.helpers.aiohttp_client", aio),
        ("homeassistant.helpers.selector", sel),
    ):
        monkeypatch.setitem(sys.modules, name, mod)

    spec = importlib.util.spec_from_file_location(
        "hslhrt.config_flow", INTEGRATION / "config_flow.py"
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)

    class FakeClient:
        def __init__(self, session, api_key):
            self.api_key = api_key

        async def search_stops(self, name):
            return STOPS if name.lower() == "töölöntori" else []

        async def search_stop_by_code(self, code):
            results = {
                "E4971": {"gtfsId": "HSL:3", "code": "E4971"},
                "E4972": {"gtfsId": "HSL:4", "code": "E4972"},
            }
            return results.get(code.upper())

        async def get_stop_info(self, gtfs):
            code_stops = [
                {"name": "Eestinmalmintie", "code": "E4971", "gtfsId": "HSL:3"},
                {"name": "Eestinmalmintie", "code": "E4972", "gtfsId": "HSL:4"},
            ]
            item = next(
                (s for s in STOPS + code_stops if s["gtfsId"] == gtfs), None
            )
            if item is None:
                return None
            return {**item, "patterns": [
                {"headsign": "West", "route": {"shortName": "8"}},
                {"headsign": "East", "route": {"shortName": "2"}},
            ]}

    monkeypatch.setattr(module, "DigitransitClient", FakeClient)
    return module


def user_input(name="Töölöntori", route="ALL", destination="ALL"):
    return {
        "user_name_code": name,
        "route": route,
        "destination": destination,
        "api_key": "SECRET",
    }


def new_flow(module):
    flow = module.HSLHRTConfigFlowHandler()
    flow.hass = SimpleNamespace()
    return flow


def test_ambiguous_stop_selection_preserves_selected_stop(flow_module):
    flow = new_flow(flow_module)
    result = asyncio.run(flow.async_step_user(user_input()))
    assert result["step_id"] == "select_stop"
    # Both platforms can be identified by their public code and GTFS ID.
    schema = result["data_schema"]
    selector = next(iter(schema.schema.values()))
    labels = [item["label"] for item in selector.conf.options]
    assert "H0209" in labels[0] and "HSL:1" in labels[0]
    assert "H0210" in labels[1] and "HSL:2" in labels[1]

    chosen = asyncio.run(flow.async_step_select_stop({"selected_stop": "HSL:2"}))
    assert chosen["type"] == "create_entry"
    assert chosen["data"]["stop_gtfs"] == "HSL:2"
    assert chosen["data"]["api_key"] == "SECRET"
    assert flow.unique_id == "HSL:2 ALL"


def test_exact_public_stop_code_skips_picker(flow_module, monkeypatch):
    module = flow_module
    class CodeClient(module.DigitransitClient):
        async def search_stops(self, name):
            raise AssertionError("Stop codes must not use the name query")

        async def search_stop_by_code(self, code):
            return {"gtfsId": "HSL:2", "code": "H0210"}
    monkeypatch.setattr(module, "DigitransitClient", CodeClient)
    flow = new_flow(module)
    result = asyncio.run(flow.async_step_user(user_input("H0210", "8")))
    assert result["type"] == "create_entry"
    assert result["data"]["stop_gtfs"] == "HSL:2"
    assert flow.unique_id == "HSL:2 8"


def test_unknown_stop_id_cannot_be_injected(flow_module):
    flow = new_flow(flow_module)
    asyncio.run(flow.async_step_user(user_input()))
    result = asyncio.run(flow.async_step_select_stop({"selected_stop": "HSL:999"}))
    assert result["type"] == "form"
    assert result["errors"]["base"] == "invalid_name_code"


def test_non_matching_route_shows_error_and_does_not_create_entry(flow_module):
    flow = new_flow(flow_module)
    asyncio.run(flow.async_step_user(user_input(route="999")))
    result = asyncio.run(flow.async_step_select_stop({"selected_stop": "HSL:1"}))
    assert result["type"] == "form"
    assert result["errors"]["base"] == "invalid_route"


def test_options_default_preserves_old_route_and_unique_id(flow_module):
    entry = SimpleNamespace(
        data={
            "stop_gtfs": "HSL:1", "route": "8", "destination": "ALL",
            "api_key": "SECRET",
        },
        options={},
        unique_id="HSL:1 8",
    )
    flow = flow_module.HSLHRTOptionsFlow()
    flow.config_entry = entry
    flow.hass = SimpleNamespace()
    result = asyncio.run(flow.async_step_init())
    assert result["type"] == "form"
    schema = result["data_schema"]
    keys = {key.schema: key.default() for key in schema.schema}
    assert keys["routes_filter"] == ["8"]
    assert keys["scan_interval"] == 1
    assert entry.unique_id == "HSL:1 8"

    result = asyncio.run(flow.async_step_init({
        "routes_filter": ["2", "8"],
        "destination_filter": "ALL",
        "scan_interval": 5,
    }))
    assert result["type"] == "create_entry"
    assert result["data"]["routes_filter"] == ["2", "8"]
    assert result["data"]["scan_interval"] == 5
    assert entry.data["route"] == "8"
    assert entry.unique_id == "HSL:1 8"


def test_options_reject_unknown_route(flow_module):
    entry = SimpleNamespace(
        data={"stop_gtfs": "HSL:1", "route": "ALL", "destination": "ALL",
              "api_key": "SECRET"},
        options={},
    )
    flow = flow_module.HSLHRTOptionsFlow()
    flow.config_entry = entry
    flow.hass = SimpleNamespace()
    asyncio.run(flow.async_step_init())
    result = asyncio.run(flow.async_step_init({
        "routes_filter": ["999"], "destination_filter": "ALL",
        "scan_interval": 3,
    }))
    assert result["type"] == "form"
    assert result["errors"]["routes_filter"] == "invalid_route"


def test_reauth_preserves_unique_id_and_options(flow_module):
    entry = SimpleNamespace(
        unique_id="HSL:1 8",
        options={"routes_filter": ["8"], "scan_interval": 5},
        data={"stop_gtfs": "HSL:1", "api_key": "OLD"},
    )
    flow = new_flow(flow_module)
    flow.entry = entry
    result = asyncio.run(
        flow.async_step_reauth_confirm({"api_key": "NEW"})
    )
    assert result["type"] == "update"
    assert result["data_updates"] == {"api_key": "NEW"}
    assert entry.options == {"routes_filter": ["8"], "scan_interval": 5}


@pytest.mark.parametrize(
    ("stop_code", "expected_gtfs"),
    [("E4971", "HSL:3"), ("e4972", "HSL:4")],
)
def test_public_stop_code_resolves_without_name_search(
    flow_module, monkeypatch, stop_code, expected_gtfs
):
    """Direct public code entry must resolve the specified side of the road."""
    base_client = flow_module.DigitransitClient

    class ExactCodeClient(base_client):
        async def search_stops(self, name):
            raise AssertionError("Public codes must not use name-based search")

    monkeypatch.setattr(flow_module, "DigitransitClient", ExactCodeClient)
    flow = new_flow(flow_module)
    result = asyncio.run(flow.async_step_user(user_input(stop_code)))
    assert result["type"] == "create_entry"
    assert result["data"]["stop_gtfs"] == expected_gtfs
    assert result["data"]["stop_code"] == stop_code.upper()
    assert flow.unique_id == f"{expected_gtfs} ALL"


def test_public_code_not_found_does_not_fall_back_to_other_stop(flow_module):
    flow = new_flow(flow_module)
    result = asyncio.run(flow.async_step_user(user_input("E4973")))
    assert result["type"] == "form"
    assert result["errors"]["user_name_code"] == "invalid_name_code"


def test_public_stop_code_is_verified_against_routing_details(
    flow_module, monkeypatch
):
    base_client = flow_module.DigitransitClient

    class MismatchedClient(base_client):
        async def search_stop_by_code(self, code):
            return {"gtfsId": "HSL:4", "code": "E4971"}

    monkeypatch.setattr(flow_module, "DigitransitClient", MismatchedClient)
    flow = new_flow(flow_module)
    result = asyncio.run(flow.async_step_user(user_input("E4971")))
    assert result["type"] == "form"
    assert result["errors"]["base"] == "invalid_name_code"
    assert getattr(flow, "unique_id", None) is None


def test_name_search_still_disambiguates_both_eestinmalmintie_platforms(
    flow_module, monkeypatch
):
    base_client = flow_module.DigitransitClient

    class StopNameClient(base_client):
        async def search_stops(self, name):
            return [
                {"gtfsId": "HSL:3", "name": name, "code": "E4971"},
                {"gtfsId": "HSL:4", "name": name, "code": "E4972"},
            ]

    monkeypatch.setattr(flow_module, "DigitransitClient", StopNameClient)
    flow = new_flow(flow_module)
    result = asyncio.run(flow.async_step_user(user_input("Eestinmalmintie")))
    assert result["type"] == "form"
    assert result["step_id"] == "select_stop"
    chosen = asyncio.run(flow.async_step_select_stop({"selected_stop": "HSL:4"}))
    assert chosen["type"] == "create_entry"
    assert chosen["data"]["stop_code"] == "E4972"



def test_compact_hfp_options_preserve_integer_storage(flow_module):
    """A dropdown emits strings; stored HFP settings remain integers."""
    entry = SimpleNamespace(
        data={"stop_gtfs": "HSL:1", "route": "8", "destination": "ALL",
              "api_key": "SECRET"},
        options={
            "track_vehicles": True,
            "tracking_horizon_minutes": 45,
            "tracking_per_route": 3,
        },
        unique_id="HSL:1 8",
    )
    flow = flow_module.HSLHRTOptionsFlow()
    flow.config_entry = entry
    flow.hass = SimpleNamespace()
    first = asyncio.run(flow.async_step_init())
    fields = {key.schema: (key.default(), value)
              for key, value in first["data_schema"].schema.items()}
    for name, value, choices in (
        ("tracking_horizon_minutes", "45", ["15", "30", "45", "60", "90"]),
        ("tracking_per_route", "3", ["1", "2", "3", "4", "5"]),
    ):
        default, selector = fields[name]
        assert default == value
        assert selector.conf.mode == "dropdown"
        assert selector.conf.options == choices

    result = asyncio.run(flow.async_step_init({
        "routes_filter": ["8"],
        "destination_filter": "ALL",
        "scan_interval": 5,
        "track_vehicles": True,
        "tracking_horizon_minutes": "60",
        "tracking_per_route": "4",
    }))
    assert result["type"] == "create_entry"
    assert result["data"]["tracking_horizon_minutes"] == 60
    assert result["data"]["tracking_per_route"] == 4
    assert type(result["data"]["tracking_horizon_minutes"]) is int
    assert type(result["data"]["tracking_per_route"]) is int
    assert result["data"]["track_vehicles"] is True
    assert entry.unique_id == "HSL:1 8"


def test_hfp_options_reject_invalid_dropdown_values(flow_module):
    """Unknown dropdown choices must never become MQTT configuration."""
    entry = SimpleNamespace(
        data={"stop_gtfs": "HSL:1", "route": "ALL", "destination": "ALL",
              "api_key": "SECRET"},
        options={},
    )
    flow = flow_module.HSLHRTOptionsFlow()
    flow.config_entry = entry
    flow.hass = SimpleNamespace()
    asyncio.run(flow.async_step_init())
    result = asyncio.run(flow.async_step_init({
        "routes_filter": [],
        "destination_filter": "ALL",
        "scan_interval": 1,
        "tracking_horizon_minutes": "999",
        "tracking_per_route": "0",
    }))
    assert result["type"] == "form"
    assert result["errors"] == {
        "tracking_horizon_minutes": "invalid_selection",
        "tracking_per_route": "invalid_selection",
    }
