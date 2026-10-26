"""Regression checks for Home Assistant event-loop callback registration."""

import ast
from pathlib import Path


def test_hfp_periodic_maintenance_is_registered_as_ha_callback():
    """A bare lambda runs in HA's executor and must not create asyncio tasks."""
    source = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "hslhrt"
        / "hfp.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    manager = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "HFPManager"
    )
    maintenance = next(
        node for node in manager.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_on_maintenance_timer"
    )
    assert any(
        isinstance(decorator, ast.Name) and decorator.id == "callback"
        for decorator in maintenance.decorator_list
    )
    start = next(
        node for node in manager.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "async_start"
    )
    timer = next(
        node for node in ast.walk(start)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "async_track_time_interval"
    )
    assert isinstance(timer.args[1], ast.Attribute)
    assert timer.args[1].attr == "_on_maintenance_timer"
    assert not any(isinstance(node, ast.Lambda) for node in ast.walk(timer))
