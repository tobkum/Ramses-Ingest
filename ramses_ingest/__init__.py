#-*- coding: utf-8 -*-
"""Ramses Ingest — Footage ingestion tool for the Ramses pipeline."""

__version__ = "0.1.0"

# =============================================================================
# OBSOLETE PATCH REMOVED: Thread-safe daemon (Now in daemon_interface.py)
# =============================================================================
# Upstream Ramses API now includes built-in thread-safe socket communication
# via _socket_lock (daemon_interface.py:87, 629). No patching required.
# =============================================================================
