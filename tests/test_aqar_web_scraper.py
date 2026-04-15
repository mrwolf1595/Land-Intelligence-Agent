import unittest

from sources.aqar.scraper import _parse_card


class _FakeImg:
  def __init__(self, src: str):
    self._src = src

  def get(self, key, default=None):
    if key == "src":
      return self._src
    return default


class _FakeTag:
  def __init__(self, href: str, text: str, img_src: str):
    self._href = href
    self._text = text
    self._img = _FakeImg(img_src)

  def get(self, key, default=None):
    if key == "href":
      return self._href
    return default

  def get_text(self, separator=" ", strip=True):
    return self._text

  def find(self, name):
    if name == "img":
      return self._img
    return None


class TestAqarWebScraper(unittest.TestCase):
    def test_parse_card_extracts_core_fields(self):
        card = _FakeTag(
            href="/أراضي-للبيع/جدة/شمال-جدة/النزهة/ارض-للبيع-123456",
            text="أرض للبيع في النزهة 1,250,000 § 500 م²",
            img_src="https://img.example/test.jpg",
        )

        parsed = _parse_card(card)

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["listing_id"], "123456")
        self.assertEqual(parsed["city"], "جدة")
        self.assertEqual(parsed["district"], "النزهة")
        self.assertEqual(parsed["price"], 1250000.0)
        self.assertEqual(parsed["area_sqm"], 500.0)
        self.assertTrue(parsed["img_src"].startswith("https://img.example"))


if __name__ == "__main__":
    unittest.main()
