import json
import unittest
from pathlib import Path


class VercelConfigTests(unittest.TestCase):
    def test_fastapi_root_entrypoint_does_not_use_api_directory_function_mapping(self):
        config = json.loads(Path("vercel.json").read_text(encoding="utf-8"))
        self.assertNotIn("functions", config)
        self.assertEqual(config.get("framework"), "fastapi")


if __name__ == "__main__":
    unittest.main()
