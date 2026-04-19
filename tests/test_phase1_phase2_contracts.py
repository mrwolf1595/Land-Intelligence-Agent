import tempfile
import unittest
from pathlib import Path


class FakeChatClient:
    def __init__(self, content: str):
        self.content = content

    def chat(self, **kwargs):
        class _Msg:
            def __init__(self, content: str):
                self.content = content

        class _Resp:
            def __init__(self, content: str):
                self.message = _Msg(content)

        return _Resp(self.content)


class TestClassifierContracts(unittest.TestCase):
    def test_short_message_marked_irrelevant(self):
        import pipeline.classifier as classifier

        payload = {"raw_text": "هلا"}
        out = classifier.classify_message(payload)
        self.assertEqual(out["msg_type"], "irrelevant")

    def test_classifier_parses_json_and_sets_fields(self):
        import pipeline.classifier as classifier

        original_client = classifier.client
        classifier.client = FakeChatClient(
            '{"msg_type":"offer","property_type":"أرض","city":"جدة","district":"النرجس","area_sqm":600,"price_sar":2500000,"price_negotiable":true,"description":"عرض أرض","confidence":0.92}'
        )
        try:
            payload = {
                "raw_text": "للبيع أرض في جدة 600 متر",
                "group_name": "g1",
                "sender_phone": "111",
                "sender_name": "Ali",
                "timestamp": "2026-04-15T10:00:00",
            }
            out = classifier.classify_message(payload)
            self.assertEqual(out["msg_type"], "offer")
            self.assertEqual(out["city"], "جدة")
            self.assertIn("message_id", out)
        finally:
            classifier.client = original_client


class TestMatcherContracts(unittest.TestCase):
    def test_run_matching_creates_match_for_high_score_pair(self):
        import core.database as db
        import pipeline.matcher as matcher

        with tempfile.TemporaryDirectory() as tmp:
            original_db_path = db.DB_PATH
            db.DB_PATH = Path(tmp) / "agent.db"
            try:
                db.init_db()
                conn = db.get_conn()
                conn.execute("DELETE FROM matches")
                conn.execute("DELETE FROM messages")
                conn.execute(
                    """
                    INSERT INTO messages (id, group_name, sender_phone, sender_name, raw_text, msg_type, city, price_sar, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                    """,
                    ("req_1", "grp", "100", "Req", "مطلوب أرض في جدة", "request", "جدة", 2000000),
                )
                conn.execute(
                    """
                    INSERT INTO messages (id, group_name, sender_phone, sender_name, raw_text, msg_type, city, price_sar, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                    """,
                    ("off_1", "grp", "200", "Off", "للبيع أرض في جدة", "offer", "جدة", 1800000),
                )
                conn.commit()
                conn.close()

                original_score = matcher._score_match
                matcher._score_match = lambda req, off: {
                    "match_score": 0.9,
                    "reasoning": "تطابق جيد",
                    "broker_tip": "تواصل سريع",
                    "key_gaps": [],
                }
                try:
                    out = matcher.run_matching()
                finally:
                    matcher._score_match = original_score

                self.assertEqual(len(out), 1)
                self.assertEqual(out[0]["request_id"], "req_1")
                self.assertEqual(out[0]["offer_id"], "off_1")
            finally:
                db.DB_PATH = original_db_path


class TestNotifierContracts(unittest.TestCase):
    def test_format_match_message_contains_score_and_fields(self):
        import pipeline.notifier as notifier

        msg = notifier.format_match_message(
            {
                "match_score": 0.81,
                "req_name": "طالب",
                "off_name": "عارض",
                "req_text": "مطلوب أرض",
                "off_text": "للبيع أرض",
                "match_reasoning": "التطابق قوي",
                "match_id": "abcd1234",
            }
        )
        self.assertIn("81%", msg)
        self.assertIn("طالب", msg)
        self.assertIn("عارض", msg)
        self.assertIn("Match ID", msg)


if __name__ == "__main__":
    unittest.main()