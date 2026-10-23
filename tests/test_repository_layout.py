"""Repository layout and metadata smoke tests (no Home Assistant runtime required)."""

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components" / "hslhrt"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_one_hacs_integration_in_standard_layout():
    assert [path.name for path in (ROOT / "custom_components").iterdir() if path.is_dir()] == [
        "hslhrt"
    ]
    for filename in (
        "__init__.py",
        "config_flow.py",
        "const.py",
        "sensor.py",
        "manifest.json",
        "strings.json",
        "client.py",
        "schedule.py",
        "configuration.py",
        "hfp.py",
        "geo_location.py",
        "vehicle.py",
        "translations/en.json",
        "translations/fi.json",
    ):
        assert (INTEGRATION / filename).is_file(), filename
    for filename in ("__init__.py", "config_flow.py", "const.py", "sensor.py", "manifest.json", "strings.json"):
        assert not (ROOT / filename).exists(), filename


def test_manifest_metadata_and_version():
    manifest = load_json(INTEGRATION / "manifest.json")
    assert manifest["domain"] == "hslhrt"
    assert list(manifest) == [
        "domain",
        "name",
        *sorted(key for key in manifest if key not in ("domain", "name")),
    ]
    assert manifest["version"] == "0.8.1"
    assert manifest["config_flow"] is True
    assert manifest["documentation"].startswith("https://github.com/fursov/")
    assert manifest["issue_tracker"].startswith("https://github.com/fursov/")
    assert manifest["codeowners"] == ["@fursov"]
    assert manifest["requirements"] == ["paho-mqtt>=2.1.0"]


def test_hacs_metadata():
    hacs = load_json(ROOT / "hacs.json")
    assert hacs["name"] == "Helsinki Regional Transport"
    assert hacs["country"] == "FI"
    assert hacs["homeassistant"] == "2026.10.2"
    requirements = (ROOT / "requirements-ha-tests.txt").read_text(encoding="utf-8")
    pinned = re.search(r"^homeassistant==([0-9.]+)$", requirements, re.MULTILINE)
    assert pinned is not None
    # Never advertise a minimum HA version older than the tested baseline.
    assert hacs["homeassistant"] == pinned.group(1)
    assert "content_in_root" not in hacs or hacs["content_in_root"] is False


def test_translations_match_source_strings():
    assert load_json(INTEGRATION / "strings.json") == load_json(
        INTEGRATION / "translations" / "en.json"
    )


def test_finnish_translation_has_complete_english_key_coverage():
    """No config/option/abort/error labels should silently fall back to English."""
    source = load_json(INTEGRATION / "translations" / "en.json")
    translated = load_json(INTEGRATION / "translations" / "fi.json")

    def keys(data: dict, prefix: str = "") -> set[str]:
        result = set()
        for key, value in data.items():
            path = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                result |= keys(value, path)
            else:
                assert isinstance(value, str) and value.strip(), path
                result.add(path)
        return result

    assert keys(translated) == keys(source)
    assert translated["config"]["step"]["select_stop"]["data"]["selected_stop"] == (
        "Pysäkki"
    )
    assert translated["options"]["step"]["init"]["data"]["track_vehicles"] != (
        source["options"]["step"]["init"]["data"]["track_vehicles"]
    )


def test_config_entry_only_schema_declared():
    source = (INTEGRATION / "__init__.py").read_text(encoding="utf-8")
    assert "CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)" in source


def test_python_sources_parse():
    for source in INTEGRATION.rglob("*.py"):
        ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
