"""Deterministic, file-aware caches for cheap Streamlit reruns."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import streamlit as st

from .application_tracker import TRACKER_PATH, load_application_tracker
from .capability_graph import CAPABILITY_GRAPH_PATH, load_capability_graph
from .evidence_profile import EVIDENCE_PROFILE_PATH, load_evidence_profile
from .generate_dashboard import load_application_packages


def _file_signature(path: Path) -> tuple[bool, int, int]:
    """Return a cheap cache key that changes whenever a source file changes."""
    try:
        stat = path.stat()
    except OSError:
        return False, 0, 0
    return True, stat.st_mtime_ns, stat.st_size


def _evidence_signature(root: Path) -> tuple[tuple[bool, int, int], ...]:
    return (
        _file_signature(root / EVIDENCE_PROFILE_PATH),
        _file_signature(root / "config" / "evidence_cards.yml"),
    )


def _tree_signature(root: Path, relative_directories: tuple[str, ...]) -> str:
    """Hash file metadata without reading stable dashboard source contents."""
    digest = hashlib.sha256()
    for relative in relative_directories:
        directory = root / relative
        if not directory.is_dir():
            digest.update(f"{relative}:missing".encode("utf-8"))
            continue
        for path in sorted(value for value in directory.rglob("*") if value.is_file()):
            exists, mtime_ns, size = _file_signature(path)
            digest.update(
                f"{path.relative_to(root)}:{int(exists)}:{mtime_ns}:{size}\n".encode("utf-8")
            )
    return digest.hexdigest()


@st.cache_data(show_spinner=False)
def _cached_evidence_profile(
    root_value: str,
    source_signature: tuple[tuple[bool, int, int], ...],
) -> dict[str, Any]:
    del source_signature
    return load_evidence_profile(Path(root_value))


@st.cache_data(show_spinner=False)
def _cached_capability_graph(
    root_value: str,
    evidence_signature: tuple[tuple[bool, int, int], ...],
    graph_signature: tuple[bool, int, int],
) -> dict[str, Any]:
    del evidence_signature, graph_signature
    root = Path(root_value)
    profile = load_cached_evidence_profile(root)
    return load_capability_graph(root, profile)


@st.cache_data(show_spinner=False)
def _cached_application_tracker(
    root_value: str,
    tracker_signature: tuple[bool, int, int],
) -> list[dict[str, Any]]:
    del tracker_signature
    return load_application_tracker(Path(root_value))


@st.cache_data(show_spinner=False)
def _cached_application_packages(
    root_value: str,
    tracker_signature: tuple[bool, int, int],
    source_signature: str,
) -> dict[str, Any]:
    del tracker_signature, source_signature
    return load_application_packages(Path(root_value))


def load_cached_evidence_profile(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root).resolve()
    return _cached_evidence_profile(str(root), _evidence_signature(root))


def load_cached_capability_graph(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root).resolve()
    return _cached_capability_graph(
        str(root),
        _evidence_signature(root),
        _file_signature(root / CAPABILITY_GRAPH_PATH),
    )


def load_cached_application_tracker(project_root: str | Path) -> list[dict[str, Any]]:
    root = Path(project_root).resolve()
    return _cached_application_tracker(
        str(root), _file_signature(root / TRACKER_PATH)
    )


def load_cached_application_packages(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root).resolve()
    return _cached_application_packages(
        str(root),
        _file_signature(root / TRACKER_PATH),
        _tree_signature(root, ("jobs", "exports")),
    )


def invalidate_evidence_caches() -> None:
    """Invalidate evidence and its true dependent, the capability graph."""
    _cached_evidence_profile.clear()
    _cached_capability_graph.clear()


def invalidate_capability_cache() -> None:
    _cached_capability_graph.clear()


def invalidate_tracker_cache() -> None:
    _cached_application_tracker.clear()
    _cached_application_packages.clear()


def invalidate_package_cache() -> None:
    _cached_application_packages.clear()
