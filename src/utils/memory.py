"""
Memory trimming helpers (Linux/glibc).
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os

from loguru import logger


def _env_bool(key: str, default: bool = True) -> bool:
    raw = os.getenv(key, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


MEMORY_TRIM_ENABLED = _env_bool("MEMORY_TRIM_ENABLED", True)
_LIBC = None
_HAS_MALLOC_TRIM = False

try:
    libc_name = ctypes.util.find_library("c")
    if libc_name:
        _LIBC = ctypes.CDLL(libc_name)
        _HAS_MALLOC_TRIM = hasattr(_LIBC, "malloc_trim")
except Exception:
    _LIBC = None
    _HAS_MALLOC_TRIM = False


def trim_memory(reason: str = "") -> bool:
    if not MEMORY_TRIM_ENABLED:
        return False
    if not _LIBC or not _HAS_MALLOC_TRIM:
        return False
    try:
        result = _LIBC.malloc_trim(0)
        if result and reason:
            logger.debug(f"已触发内存回收: {reason}")
        return bool(result)
    except Exception as e:
        logger.debug(f"触发内存回收失败: {e}")
        return False
