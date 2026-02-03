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


def trim_memory(reason: str = "") -> bool:
    if not MEMORY_TRIM_ENABLED:
        return False
    try:
        libc_name = ctypes.util.find_library("c")
        if not libc_name:
            return False
        libc = ctypes.CDLL(libc_name)
        if not hasattr(libc, "malloc_trim"):
            return False
        result = libc.malloc_trim(0)
        if result and reason:
            logger.debug(f"已触发内存回收: {reason}")
        return bool(result)
    except Exception as e:
        logger.debug(f"触发内存回收失败: {e}")
        return False
