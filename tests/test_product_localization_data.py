import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCALE_PATH = ROOT / "web" / "product-translations.pt-BR.json"
KNOWN_BLOCKED_IDS = {
    "6ae3371e733eece885451242",
    "6a4f9e24a8d17b681650ce19",
    "6ad192cd02296012a32a5c67",
    "6a47257cc35868edfeb4b3a3",
    "6ace53119be1aad20b05f20b",
    "6accf60c73ae2c508579fe66",
    "6ae10f7c6eef632a1c1cfd1b",
}


class ProductLocalizationDataTests(unittest.TestCase):
    def test_muse_video_durations_are_shown_as_seconds_not_years(self):
        locale = json.loads(LOCALE_PATH.read_text(encoding="utf-8"))
        for product_id in (
            "6ad65a621d313c71fe80820d",
            "6ad65a851d313c71fe808a94",
            "6ad65aa71d313c71fe80912f",
        ):
            description = locale["translations"][product_id]["description"]
            with self.subTest(product_id=product_id):
                for duration in ("10 s", "20 s", "30 s", "60 s"):
                    self.assertIn(duration, description)
                self.assertNotRegex(description, re.compile(r"Anos\s+(?:20|30|60)\b", re.I))

    def test_pt_br_file_covers_every_source_item_or_explicitly_suppresses_it(self):
        locale = json.loads(LOCALE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(locale["locale"], "pt-BR")
        source_ids = set(locale["source_product_ids"])
        translations = locale["translations"]
        translated_ids = set(translations)
        hidden_ids = set(locale["hidden_product_ids"])
        unchanged_ids = set(locale["unchanged_product_ids"])

        source_urls = locale["source_urls"]
        self.assertEqual(set(source_urls), translated_ids)
        self.assertEqual(len(source_ids), 128)
        self.assertEqual(len(translated_ids), 75)
        self.assertEqual(len(unchanged_ids), 53)
        self.assertEqual(len(hidden_ids), 0)
        self.assertEqual(source_ids, translated_ids | unchanged_ids | hidden_ids)
        self.assertFalse(translated_ids & unchanged_ids)
        self.assertTrue(KNOWN_BLOCKED_IDS <= unchanged_ids)
        for product_id, copy in translations.items():
            with self.subTest(product_id=product_id):
                self.assertTrue(copy["name"].strip())
                self.assertTrue(copy["description"].strip())
                self.assertEqual(
                    source_urls[product_id],
                    re.findall(r"https?://[^\s<>\]\[)\"`]+", copy["description"], re.I),
                )
                self.assertNotRegex(copy["description"], re.compile(r"mail\s*\|\s*pass|refresh[_ ]?token|2fa\.live|oauth2 live account", re.I))


if __name__ == "__main__":
    unittest.main()
