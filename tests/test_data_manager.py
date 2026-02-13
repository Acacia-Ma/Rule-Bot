import asyncio
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

# Add repo root to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src.data_manager import DataManager


def _build_config(data_dir: str, interval: float = 0.05) -> SimpleNamespace:
    return SimpleNamespace(
        DATA_DIR=data_dir,
        GEOSITE_CACHE_SIZE=32,
        GEOSITE_CACHE_TTL=60,
        DATA_UPDATE_INTERVAL=interval,
        GEOIP_URLS=[],
        CN_IPV4_URLS=[],
        GEOSITE_URL="",
    )


class TestDataManagerScheduling(unittest.IsolatedAsyncioTestCase):
    async def test_scheduler_runs_and_stops_cleanly(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = _build_config(temp_dir, interval=0.05)
            manager = DataManager(config)

            update_called = asyncio.Event()

            async def _fake_update():
                update_called.set()

            with patch.object(manager, "_download_initial_data", AsyncMock()):
                with patch.object(manager, "_update_data", AsyncMock(side_effect=_fake_update)):
                    await manager.initialize()
                    await asyncio.wait_for(update_called.wait(), timeout=0.5)
                    self.assertIsNotNone(manager._scheduler_task)
                    self.assertFalse(manager._scheduler_task.done())

                    await manager.close()
                    self.assertIsNone(manager._scheduler_task)

    async def test_session_lifecycle(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = _build_config(temp_dir, interval=3600)
            manager = DataManager(config)

            session1 = await manager._get_session()
            session2 = await manager._get_session()

            self.assertIs(session1, session2)
            self.assertFalse(session1.closed)

            await manager.close()
            self.assertTrue(session1.closed)
            self.assertIsNone(manager._session)


if __name__ == "__main__":
    unittest.main()
