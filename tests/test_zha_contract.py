"""Contract test: guards against ZHA's internal API changing underneath us.

Not a test of our own code: this only asserts that the private ZHA/zha
internals we rely on (undocumented, not a public API) still look the way
we expect. A failure here means an upstream ZHA change, not a bug in this
integration.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import homeassistant
from zha.application.gateway import Gateway
from zha.zigbee.device import Device

# zha/helpers.py is parsed from source rather than imported: importing it
# runs homeassistant/components/zha/__init__.py, which eagerly pulls in
# ZHA's own dependencies (Hardware, Supervisor, USB, ...) that have
# nothing to do with what's being checked here.
_HELPERS_PATH = Path(homeassistant.__file__).parent / "components" / "zha" / "helpers.py"


def _helpers_module_ast() -> ast.Module:
    """Parse zha/helpers.py's source without importing it."""
    return ast.parse(_HELPERS_PATH.read_text())


def test_signal_add_entities_unchanged() -> None:
    """SIGNAL_ADD_ENTITIES is the dispatcher signal we listen for new devices on."""
    tree = _helpers_module_ast()
    assigned = {
        target.id: node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    signal_node = assigned.get("SIGNAL_ADD_ENTITIES")
    assert signal_node is not None, "SIGNAL_ADD_ENTITIES no longer defined"
    assert ast.literal_eval(signal_node) == "zha_add_entities"


def test_get_zha_gateway_proxy_defined() -> None:
    """get_zha_gateway_proxy must still be defined as a top-level function."""
    tree = _helpers_module_ast()
    names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "get_zha_gateway_proxy" in names


def test_device_exposes_available_and_last_seen() -> None:
    """Device.available and Device.last_seen must still exist as properties."""
    assert isinstance(inspect.getattr_static(Device, "available"), property)
    assert isinstance(inspect.getattr_static(Device, "last_seen"), property)


def test_gateway_exposes_devices() -> None:
    """Gateway.devices must still exist as a property."""
    assert isinstance(inspect.getattr_static(Gateway, "devices"), property)
