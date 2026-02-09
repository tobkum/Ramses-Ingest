# -*- coding: utf-8 -*-
"""Ramses Ingest — Footage ingestion tool for the Ramses pipeline."""

__version__ = "0.1.0"

# --- CRITICAL PATCH: Thread-Safe Ramses Daemon ---
# The Ramses API is not thread-safe by default. Since we run ingest in parallel threads,
# we must lock the socket communication to prevent race conditions/corruption.
try:
    import threading
    from ramses.daemon_interface import RamDaemonInterface

    # Only patch if not already patched (e.g. by another tool)
    # Check class-level patching or instance-level lock
    _daemon_instance = RamDaemonInterface.instance()
    
    if not hasattr(_daemon_instance, "_lock"):
        _daemon_instance._lock = threading.Lock()

        # We need to wrap the CLASS method to catch all new instances/usage
        # referring to the singleton's lock.
        _original_post = getattr(RamDaemonInterface, "_RamDaemonInterface__post")

        def _patched_post(self, query, bufsize=0):
            # Ensure the instance has a lock (in case it's a new instance/reset)
            if not hasattr(self, "_lock"):
                self._lock = threading.Lock()
            
            with self._lock:
                return _original_post(self, query, bufsize)

        setattr(RamDaemonInterface, "_RamDaemonInterface__post", _patched_post)

except (ImportError, AttributeError):
    pass  # Ramses API not present or incompatible version

