from __future__ import annotations

import unittest

from test_brain_helpers import build_test_core

from terrygpt.brain.model_manager import ModelManager


class ModelManagerTests(unittest.TestCase):
    def test_refresh_persists_model_metadata(self) -> None:
        temp, core = build_test_core()
        try:
            core.initialize()
            manager = ModelManager(core.module("database"), core.module("ai_provider_registry"))  # type: ignore[arg-type]
            models = manager.refresh()
        finally:
            temp.cleanup()

        self.assertEqual(models[0].model_name, "fake-model")
        self.assertEqual(models[0].parameter_size, "1B")
        self.assertEqual(models[0].quantization, "Q4")
        self.assertEqual(models[0].context_length, 4096)


if __name__ == "__main__":
    unittest.main()

