# -*- coding: utf-8 -*-
"""Test script for Smart Pattern Builder UI."""

import sys
from PySide6.QtWidgets import QApplication

from ramses_ingest.smart_pattern_dialog import SmartPatternDialog


def main():
    """Launch the Smart Pattern Builder dialog for testing."""
    app = QApplication(sys.argv)

    # Create and show the dialog
    dlg = SmartPatternDialog()

    # Pre-populate with sample data
    samples = [
        "A077C013_230614_RO9S.mov",
        "A081C011_230615_RO9S_1.mov",
        "A027C009_230512_RO9S_A.mov",
        "A016C013_230509_RO9S_B.mov"
    ]

    dlg.sample_edit.setPlainText("\n".join(samples))
    dlg._on_samples_changed()

    # Show dialog
    result = dlg.exec()

    if result:
        pattern = dlg.get_final_regex()
        print(f"\nGenerated Pattern: {pattern}")
    else:
        print("\nDialog cancelled")

    return 0


if __name__ == "__main__":
    sys.exit(main())
