# -*- coding: utf-8 -*-
"""Path normalization utilities for cross-platform consistency.

All paths in the pipeline should use forward slashes internally for:
- Database storage (Ramses daemon)
- Cache keys
- String comparisons
- JSON serialization

Use these utilities instead of os.path.join() and os.path.normpath() directly.
"""

from __future__ import annotations

import os
from pathlib import Path


def normalize_path(p: str | Path) -> str:
    """Convert path to forward slashes for internal consistency.

    Args:
        p: File path (string or Path object)

    Returns:
        Normalized path with forward slashes (e.g., "C:/Projects/Shot/v001")

    Examples:
        >>> normalize_path("C:\\Projects\\Shot\\v001")
        'C:/Projects/Shot/v001'
        >>> normalize_path(Path("C:/Projects/Shot/v001"))
        'C:/Projects/Shot/v001'
    """
    return str(Path(p)).replace("\\", "/")


def join_normalized(*parts: str | Path) -> str:
    """Join path components and normalize to forward slashes.

    Args:
        *parts: Path components to join

    Returns:
        Joined path with forward slashes

    Examples:
        >>> join_normalized("C:/Projects", "PROJ", "05-SHOTS", "SH010")
        'C:/Projects/PROJ/05-SHOTS/SH010'
    """
    return normalize_path(os.path.join(*[str(p) for p in parts]))


def validate_path_within_root(path: str | Path, root: str | Path) -> bool:
    """Validate that path is within root directory (prevents path traversal).

    Args:
        path: Path to validate
        root: Root directory that should contain the path

    Returns:
        True if path is within root, False otherwise

    Examples:
        >>> validate_path_within_root("C:/Projects/PROJ/shot", "C:/Projects")
        True
        >>> validate_path_within_root("C:/Projects/../etc/passwd", "C:/Projects")
        False
    """
    try:
        resolved_path = Path(path).resolve()
        resolved_root = Path(root).resolve()
        resolved_path.relative_to(resolved_root)
        return True
    except (ValueError, OSError):
        return False


def get_relative_path(path: str | Path, base: str | Path) -> str:
    """Get relative path from base, normalized to forward slashes.

    Args:
        path: Full path
        base: Base directory

    Returns:
        Relative path with forward slashes

    Raises:
        ValueError: If path is not relative to base
    """
    return normalize_path(Path(path).relative_to(base))
