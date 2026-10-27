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


def test_shared_vehicle_map_task_schedulers_are_event_loop_callbacks():
    """Never register a vehicle-map reconciler as an executor-thread callback."""
    source = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "hslhrt"
        / "geo_location.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for klass_name, method_name in (
        ("HSLHRTSharedVehicleMap", "schedule_sync"),
        ("HSLHRTMapController", "_schedule_sync"),
    ):
        klass = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == klass_name
        )
        method = next(
            node for node in klass.body
            if isinstance(node, ast.FunctionDef) and node.name == method_name
        )
        assert any(
            isinstance(decorator, ast.Name) and decorator.id == "callback"
            for decorator in method.decorator_list
        )
    # External Paho callbacks in the existing MQTT worker must continue
    # crossing the thread boundary before any map reconciliation.
    hfp = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "hslhrt"
        / "hfp.py"
    ).read_text(encoding="utf-8")
    worker = next(
        node for klass in ast.parse(hfp).body
        if isinstance(klass, ast.ClassDef) and klass.name == "HFPManager"
        for node in klass.body
        if isinstance(node, ast.FunctionDef) and node.name == "_open_worker"
    )
    message = next(
        node for node in worker.body
        if isinstance(node, ast.FunctionDef) and node.name == "on_message"
    )
    assert any(
        isinstance(node, ast.Attribute) and node.attr == "call_soon_threadsafe"
        for node in ast.walk(message)
    )
    assert not any(
        isinstance(node, ast.Attribute) and node.attr == "async_create_task"
        for node in ast.walk(message)
    )
