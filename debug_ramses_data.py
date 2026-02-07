# -*- coding: utf-8 -*-
"""Debug script to inspect Ramses database entries."""

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

        project = ram.project()
        if not project:
            print("ERROR: No project currently active in Ramses.")
            return

        print(f"--- PROJECT: {project.name()} ({project.shortName()}) ---")
        print(f"UUID: {project.uuid()}")
        print(f"Path: {project.folderPath()}")
        print("-" * 40)

        # Inspect Sequences
        sequences = project.sequences()
        print(f"\nFOUND {len(sequences)} SEQUENCES:")
        for seq in sequences:
            data = seq.data()
            print(f"  [{seq.shortName()}] {seq.name()}")
            print(f"    UUID: {seq.uuid()}")
            print(f"    Project: {data.get('project', 'MISSING')}")
            print(f"    Folder:  {data.get('folderPath', 'MISSING')}")
            print("-" * 20)

        # Inspect Shots
        shots = project.shots()
        print(f"\nFOUND {len(shots)} SHOTS:")
        for shot in shots:
            data = shot.data()
            print(f"  [{shot.shortName()}] {shot.name()}")
            print(f"    UUID:     {shot.uuid()}")
            print(f"    Sequence: {data.get('sequence', 'MISSING')}")
            print(f"    Project:  {data.get('project', 'MISSING')}")
            print(f"    Folder:   {data.get('folderPath', 'MISSING')}")
            print("-" * 20)

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")

if __name__ == "__main__":
    debug_db()