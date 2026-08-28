"""Functional tests for the ZHA Connectivity Sensor integration.

Kept in its own subdirectory, with its own conftest.py, so pytest doesn't
load pytest-homeassistant-custom-component's fixtures when only running
test_zha_contract.py. That check deliberately avoids needing them.
"""
