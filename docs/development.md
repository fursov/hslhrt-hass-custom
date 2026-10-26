# Development and validation

This project supports Home Assistant Core 2026.10.2 (Python 3.14) and newer
supported Core releases, as declared in the integration manifest/HACS metadata.

## Lightweight unit and smoke tests

Use a **separate Python 3.13 environment** without Home Assistant Core:

```sh
python -m pip install pytest ruff aiohttp voluptuous
ruff check .
python -m compileall -q custom_components/hslhrt
python -m pytest -q tests --ignore=tests/integration
```

## Home Assistant integration tests

Use a separate **Python 3.14 environment** with actual Home Assistant:

```sh
python -m pip install -r requirements-ha-tests.txt
python -m pytest -q -p pytest_homeassistant_custom_component tests/integration
```

The suites run in separate Python processes because the lightweight tests
stub Home Assistant modules. CI also runs Hassfest and HACS validation.

## Concurrency and Pyscript safety

- Do not invoke `hass.async_create_task` from executor threads or the
  paho-mqtt worker callbacks. Transfer external-library notifications safely
  to Home Assistant's event loop before touching HA async APIs.
- Decorate synchronous callbacks that must run in the event loop with
  `@callback`; check timer/listener execution contexts and shutdown races.
- Keep blocking network and MQTT operations off the event loop.
- Check thread-safety with regression tests that exercise worker callbacks
  in addition to ordinary unit tests.
- Pyscript rules also apply if related Pyscript automation files are edited:
  no Python generator expressions in Pyscript-executed code; check the AST
  and test in a genuine Pyscript/Home Assistant environment as needed.

Tests against a real Home Assistant/Pyscript installation are still needed
for behavior not covered by the CI fixtures.
