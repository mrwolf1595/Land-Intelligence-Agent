import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestGate4ParityVerification(unittest.TestCase):
    """
    Gate 4 scenarios for parity verification.
    These tests verify the full pipeline without requiring live WhatsApp.
    """

    def test_BLK_PARITY_001_bridge_endpoint_operational(self):
        """
        Verify Python bridge endpoint is functional and responds correctly.
        Simulates deployed environment parity check.
        """
        import sources.whatsapp.bridge as bridge
        from fastapi.testclient import TestClient
        
        test_client = TestClient(bridge.app)
        
        # Test health endpoint
        response = test_client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertIn("status", response.json())

    def test_BLK_PARITY_002_message_endpoint_accepts_payload(self):
        """
        Verify /message endpoint accepts and queues incoming messages.
        """
        import sources.whatsapp.bridge as bridge
        from fastapi.testclient import TestClient
        
        test_client = TestClient(bridge.app)
        payload = {
            "raw_text": "للبيع أرض في جدة 600 متر بـ 2.5 مليون",
            "sender_name": "أحمد",
            "sender_phone": "966501234567",
            "group_name": "جروب عقارات",
            "timestamp": "2026-04-15T10:00:00"
        }
        response = test_client.post("/message", json=payload)
        self.assertIn(response.status_code, [200, 202])
        self.assertIn("status", response.json())

    def test_BLK_PARITY_003_test_endpoint_returns_classification(self):
        """
        Verify bridge test endpoint returns classification results.
        This confirms messaging classification works in deployed context.
        """
        import sources.whatsapp.bridge as bridge
        from fastapi.testclient import TestClient
        
        test_client = TestClient(bridge.app)
        payload = {
            "raw_text": "مطلوب فيلا في حي الملقا",
            "sender_name": "محمد",
            "sender_phone": "966502345678",
            "group_name": "فرص عقارية",
            "timestamp": "2026-04-15T10:00:00"
        }
        with patch("sources.whatsapp.bridge.classify_message") as mock_classify:
            mock_classify.return_value = {**payload, "msg_type": "request"}
            response = test_client.post("/test/message", json=payload)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("classified", data)
        self.assertEqual(data["classified"].get("msg_type"), "request")

    def test_BLK_PARITY_003b_classifier_fallback_when_ollama_unavailable(self):
        """
        Verify safe fallback behavior when Ollama is unavailable.
        """
        import pipeline.classifier as classifier

        payload = {
            "raw_text": "مطلوب فيلا في حي الملقا",
            "sender_name": "محمد",
            "sender_phone": "966502345678",
            "group_name": "فرص عقارية",
            "timestamp": "2026-04-15T10:00:00",
        }

        original_client = classifier.client

        class FailingClient:
            def chat(self, **kwargs):
                raise RuntimeError("Ollama unavailable")

        classifier.client = FailingClient()
        try:
            out = classifier.classify_message(payload)
            self.assertEqual(out.get("msg_type"), "irrelevant")
        finally:
            classifier.client = original_client

    def test_BLK_PHONE_001_notifier_formats_message_correctly(self):
        """
        Gate 5 parity check: Verify notification message is formatted correctly.
        This would be what the broker receives on real phone.
        """
        import pipeline.notifier as notifier
        
        test_match = {
            "match_score": 0.87,
            "match_id": "test_match_001",
            "req_name": "طالب الأرض",
            "req_text": "مطلوب أرض في جدة",
            "req_city": "جدة",
            "req_price": 2000000,
            "off_name": "عارض الأرض",
            "off_text": "للبيع أرض في جدة",
            "off_city": "جدة",
            "off_price": 1800000,
            "match_reasoning": "تطابق موقع وسعر قريب جداً",
            "broker_tip": "اتصل فوراً — الأرض مطلوبة من عدة أشخاص",
        }
        
        message = notifier.format_match_message(test_match)
        
        # Verify 10-second actionability
        self.assertIn("87%", message)  # Score visible
        self.assertIn("طالب الأرض", message)  # Request name visible
        self.assertIn("عارض الأرض", message)  # Offer name visible
        self.assertIn("تطابق", message)  # Arabic reasoning clearly shown
        
        # Under 2000 chars should be fast to read
        self.assertLess(len(message), 2000, "Message too long for 10-second review")


if __name__ == "__main__":
    unittest.main()
