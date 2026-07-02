from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app.core.model_settings import initialize_model_settings, update_model_settings


class ModelSettingsTest(unittest.TestCase):
    def test_initialize_and_update_keep_quality_evaluator(self) -> None:
        defaults = {
            "OPENAI_API_KEY": "",
            "OPENAI_BASE_URL": "https://api.deepseek.com",
            "LLM_MODEL": "deepseek-chat",
            "QA_QUALITY_EVALUATOR": "lexical_overlap_v1",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            settings_path = Path(temp_dir) / "model_settings.json"
            with patch("backend.app.services.model_settings.MODEL_SETTINGS_PATH", settings_path), patch.dict(
                "backend.app.services.model_settings.MODEL_SETTINGS_DEFAULTS",
                defaults,
                clear=True,
            ):
                initialized = initialize_model_settings()
                self.assertEqual(initialized["QA_QUALITY_EVALUATOR"], "lexical_overlap_v1")
                self.assertTrue(settings_path.exists())

                after_update = update_model_settings({"OPENAI_API_KEY": "test-key"})
                self.assertEqual(after_update["OPENAI_API_KEY"], "test-key")
                self.assertEqual(after_update["QA_QUALITY_EVALUATOR"], "lexical_overlap_v1")

                payload = json.loads(settings_path.read_text(encoding="utf-8"))
                self.assertEqual(payload["OPENAI_API_KEY"], "test-key")
                self.assertEqual(payload["QA_QUALITY_EVALUATOR"], "lexical_overlap_v1")

                after_switch = update_model_settings({"QA_QUALITY_EVALUATOR": "custom_eval"})
                self.assertEqual(after_switch["QA_QUALITY_EVALUATOR"], "custom_eval")
                self.assertEqual(after_switch["OPENAI_API_KEY"], "test-key")


if __name__ == "__main__":
    unittest.main()
