"""Regression tests for importing HSL HRT with modern Home Assistant APIs.

pytest only installs the integration's HTTP dependencies, so fake the HA module
surface while explicitly *not* exposing the obsolete homeassistant.core.Config.
"""

import asyncio
import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "hslhrt"


def test_integration_imports_without_homeassistant_core_config(monkeypatch):
    """Old import from homeassistant.core must fail in this environment."""
    package = sys.modules.get("hslhrt")
    if package is None:
        package = types.ModuleType("hslhrt")
        package.__path__ = [str(ROOT)]
        monkeypatch.setitem(sys.modules, "hslhrt", package)

    homeassistant = types.ModuleType("homeassistant")
    homeassistant.__path__ = []
    core = types.ModuleType("homeassistant.core")
    exceptions = types.ModuleType("homeassistant.exceptions")
    helpers = types.ModuleType("homeassistant.helpers")
    helpers.__path__ = []
    config_validation = types.ModuleType("homeassistant.helpers.config_validation")
    aiohttp_client = types.ModuleType("homeassistant.helpers.aiohttp_client")
    helper_typing = types.ModuleType("homeassistant.helpers.typing")
    update_coordinator = types.ModuleType("homeassistant.helpers.update_coordinator")

    class HomeAssistant:
        pass

    class ConfigEntryAuthFailed(Exception):
        pass

    class DataUpdateCoordinator:
        pass

    class UpdateFailed(Exception):
        pass

    core.HomeAssistant = HomeAssistant
    core.callback = lambda func: func
    # Intentionally do NOT define core.Config.
    helper_typing.ConfigType = dict
    exceptions.ConfigEntryAuthFailed = ConfigEntryAuthFailed
    config_validation.config_entry_only_config_schema = lambda domain: {"domain": domain}
    aiohttp_client.async_get_clientsession = lambda hass: None
    update_coordinator.DataUpdateCoordinator = DataUpdateCoordinator
    update_coordinator.UpdateFailed = UpdateFailed

    for name, module in (
        ("homeassistant", homeassistant),
        ("homeassistant.core", core),
        ("homeassistant.exceptions", exceptions),
        ("homeassistant.helpers", helpers),
        ("homeassistant.helpers.config_validation", config_validation),
        ("homeassistant.helpers.aiohttp_client", aiohttp_client),
        ("homeassistant.helpers.typing", helper_typing),
        ("homeassistant.helpers.update_coordinator", update_coordinator),
    ):
        monkeypatch.setitem(sys.modules, name, module)

    spec = importlib.util.spec_from_file_location(
        "hslhrt._entrypoint_regression_test", ROOT / "__init__.py"
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)

    assert module.async_setup.__annotations__["config"] is dict
    assert module.CONFIG_SCHEMA == {"domain": "hslhrt"}
    hass = SimpleNamespace(data={})
    assert asyncio.run(module.async_setup(hass, {})) is True
    assert hass.data == {"hslhrt": {}}
