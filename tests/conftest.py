# -*- coding: utf-8 -*-
"""Test isolation: no test may ever reach a live Ramses daemon or client.

Several code paths (register_ramses_objects, update_ramses_status,
connect_ramses) are guarded by ``online()`` checks — on a developer machine
with the Ramses client closed they bail out silently, so a test that forgot
to mock them still passes. But run the same suite while the client is OPEN
(e.g. during a production ingest session) and those tests write real
sequences/shots into the ACTIVE project.

This autouse fixture forces every online check to False and neuters
``connect()`` (which would otherwise launch the client executable). Tests
that need an "online" Ramses must patch at a higher level (e.g.
``patch("ramses.Ramses")`` with their own mock instance), which is unaffected
by these class-attribute patches.
"""

import pytest
from unittest.mock import MagicMock


@pytest.fixture(autouse=True)
def _no_live_ramses(monkeypatch):
    import ramses.ramses as ramses_mod
    import ramses.daemon_interface as daemon_mod

    monkeypatch.setattr(ramses_mod.Ramses, "connect", MagicMock(return_value=False))
    monkeypatch.setattr(ramses_mod.Ramses, "online", MagicMock(return_value=False))
    monkeypatch.setattr(
        daemon_mod.RamDaemonInterface, "online", MagicMock(return_value=False)
    )
    yield
