# -*- coding: utf-8 -*-
"""Cleanup script to remove malformed (MISSING) Ramses database entries."""

import sys
import os

# Add lib/ to path
_lib = os.path.join(os.path.dirname(__file__), "lib")
if _lib not in sys.path:
    sys.path.insert(0, _lib)

def cleanup_db():
    try:
        from ramses import Ramses
        from ramses.daemon_interface import RamDaemonInterface
        ram = Ramses.instance()
        daemon = RamDaemonInterface.instance()
        
        if not ram.online():
            print("ERROR: Ramses Daemon is offline.")
            return

        project = ram.project()
        if not project:
            print("ERROR: No project currently active in Ramses.")
            return

        print(f"CLEANING PROJECT: {project.name()}")
        print("-" * 40)

        # 1. Collect bad shots
        to_delete_shots = []
        for shot in project.shots():
            data = shot.data()
            # If missing project link or folder, it's malformed
            if not data.get("project") or data.get("folderPath") == "MISSING" or not data.get("folderPath"):
                to_delete_shots.append(shot)

        # 2. Collect bad sequences
        to_delete_seqs = []
        for seq in project.sequences():
            data = seq.data()
            if not data.get("project") or data.get("folderPath") == "MISSING" or not data.get("folderPath"):
                to_delete_seqs.append(seq)

        print(f"Found {len(to_delete_shots)} malformed shots to delete.")
        print(f"Found {len(to_delete_seqs)} malformed sequences to delete.")

        # Low-level delete via private __post if available
        for shot in to_delete_shots:
            print(f"  Deleting shot: {shot.shortName()} ({shot.uuid()})")
            daemon._RamDaemonInterface__post(("delete", ("uuid", shot.uuid()), ("type", "RamShot")))

        for seq in to_delete_seqs:
            print(f"  Deleting sequence: {seq.shortName()} ({seq.uuid()})")
            daemon._RamDaemonInterface__post(("delete", ("uuid", seq.uuid()), ("type", "RamSequence")))

        print("\nCleanup complete.")

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")

if __name__ == "__main__":
    cleanup_db()