# -*- coding: utf-8 -*-
"""Debug script to inspect Ramses database entries and USER info."""

import sys
import os
import json

# Add lib/ to path
_lib = os.path.join(os.path.dirname(__file__), "lib")
if _lib not in sys.path:
    sys.path.insert(0, _lib)

def debug_db():
    try:
        from ramses import Ramses
        ram = Ramses.instance()
        
        if not ram.online():
            print("ERROR: Ramses Daemon is offline.")
            return

        print("--- DAEMON PING ---")
        ping_data = ram.daemonInterface().ping()
        print(json.dumps(ping_data, indent=2))
        
        user = ram.user()
        if user:
            print(f"\n--- USER INFO ---")
            print(f"UUID: {user.uuid()}")
            print(f"Name: {user.name()}")
            print(f"Data: {user.data()}")
        else:
            print("\n--- USER: NOT LOGGED IN ---")

        project = ram.project()
        if not project:
            print("ERROR: No project currently active in Ramses.")
            return

        print(f"\n--- PROJECT: {project.name()} ({project.shortName()}) ---")
        print(f"UUID: {project.uuid()}")
        print("-" * 40)

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")

if __name__ == "__main__":
    debug_db()
