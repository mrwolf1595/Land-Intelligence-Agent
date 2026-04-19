import tempfile
import unittest
from pathlib import Path


class TestPhase13BenchmarkContracts(unittest.TestCase):
    def setUp(self):
        import core.database as db
        self.db = db
        self.original_db_path = db.DB_PATH
        self.tmp = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.tmp.name) / "agent.db"
        db.init_db()

    def tearDown(self):
        self.db.DB_PATH = self.original_db_path
        self.tmp.cleanup()

    def test_SCN_BENCH_001_prefer_moj_over_scraped(self):
        from core.database import get_conn
        from pipeline.benchmarks import get_benchmark

        conn = get_conn()
        conn.execute(
            """
            INSERT INTO market_reference_prices
            (city, district, price_per_sqm, source, transaction_date, sample_count, created_at)
            VALUES ('الرياض','العليا',10000,'moj','2026-04-01',10,'2026-04-01T10:00:00')
            """
        )
        conn.execute(
            """
            INSERT INTO price_benchmarks
            (city, district, avg_price_per_sqm, median_price_per_sqm, sample_count, last_updated)
            VALUES ('الرياض','العليا',9000,8900,25,'2026-04-02T09:00:00')
            """
        )
        conn.commit()
        conn.close()

        bench = get_benchmark('الرياض', 'العليا')
        self.assertIsNotNone(bench)
        self.assertEqual(bench['source'], 'moj')
        self.assertEqual(bench['avg'], 10000)

    def test_SCN_BENCH_002_fallback_to_local_moj_when_moj_missing(self):
        from core.database import get_conn
        from pipeline.benchmarks import get_benchmark

        conn = get_conn()
        conn.execute(
            """
            INSERT INTO market_reference_prices
            (city, district, price_per_sqm, source, transaction_date, sample_count, created_at)
            VALUES ('جدة','الروضة',7800,'local_moj','2026-04-05',7,'2026-04-05T08:00:00')
            """
        )
        conn.commit()
        conn.close()

        bench = get_benchmark('جدة', 'الروضة')
        self.assertIsNotNone(bench)
        self.assertEqual(bench['source'], 'local_moj')
        self.assertEqual(bench['avg'], 7800)

    def test_SCN_BENCH_003_fallback_to_scraped_only_with_threshold(self):
        from core.database import get_conn
        from pipeline.benchmarks import get_benchmark

        conn = get_conn()
        # Below threshold, must not be used
        conn.execute(
            """
            INSERT INTO price_benchmarks
            (city, district, avg_price_per_sqm, median_price_per_sqm, sample_count, last_updated)
            VALUES ('الدمام','الشاطئ',6500,6400,4,'2026-04-08T12:00:00')
            """
        )
        conn.commit()
        conn.close()

        bench = get_benchmark('الدمام', 'الشاطئ')
        self.assertIsNone(bench)

    def test_SCN_BENCH_004_expose_provenance_fields(self):
        from core.database import get_conn
        from pipeline.benchmarks import get_benchmark

        conn = get_conn()
        conn.execute(
            """
            INSERT INTO market_reference_prices
            (city, district, price_per_sqm, source, transaction_date, sample_count, created_at)
            VALUES ('مكة','العزيزية',9200,'moj','2026-04-10',11,'2026-04-10T11:00:00')
            """
        )
        conn.commit()
        conn.close()

        bench = get_benchmark('مكة', 'العزيزية')
        self.assertEqual(bench['source'], 'moj')
        self.assertEqual(bench['count'], 11)
        self.assertEqual(bench['as_of'], '2026-04-10')

    def test_SCN_BENCH_006_stale_reference_falls_back_to_scraped(self):
        from core.database import get_conn
        from pipeline.benchmarks import get_benchmark

        conn = get_conn()
        conn.execute(
            """
            INSERT INTO market_reference_prices
            (city, district, price_per_sqm, source, transaction_date, sample_count, created_at)
            VALUES ('الخبر','الحزام',8400,'moj','2020-01-01',10,'2020-01-01T00:00:00')
            """
        )
        conn.execute(
            """
            INSERT INTO price_benchmarks
            (city, district, avg_price_per_sqm, median_price_per_sqm, sample_count, last_updated)
            VALUES ('الخبر','الحزام',7600,7550,12,'2026-04-08T12:00:00')
            """
        )
        conn.commit()
        conn.close()

        bench = get_benchmark('الخبر', 'الحزام')
        self.assertIsNotNone(bench)
        self.assertEqual(bench['source'], 'scraped')
        self.assertEqual(bench['avg'], 7600)


class TestPhase13NotifierTransparency(unittest.TestCase):
    def test_SCN_BENCH_005_notifier_mentions_benchmark_source(self):
        import pipeline.notifier as notifier

        analysis = {
            'location': 'الرياض - العليا',
            'land_area_sqm': 600,
            'asking_price_sar': 4200000,
            'opportunity_score': 8.2,
            'recommended_development': 'apartments',
            'source_url': 'https://example.com/land1',
            'benchmark_source': 'moj',
            'benchmark_sample_count': 12,
            'benchmark_as_of': '2026-04-09',
        }
        financial = {
            'roi_pct': 22,
            'total_investment_sar': 5000000,
            'total_revenue_sar': 6200000,
            'gross_profit_sar': 1200000,
            'timeline_months': 24,
        }

        sent = {}

        def fake_send(_to, message):
            sent['message'] = message
            return True

        original = notifier._send_whatsapp
        notifier._send_whatsapp = fake_send
        try:
            ok = notifier.notify_broker_opportunity(analysis, financial, None)
        finally:
            notifier._send_whatsapp = original

        self.assertTrue(ok)
        msg = sent.get('message', '')
        self.assertIn('مرجعية التسعير', msg)
        self.assertIn('وزارة العدل', msg)
        self.assertIn('حجم العينة', msg)
        self.assertIn('آخر تحديث', msg)


if __name__ == "__main__":
    unittest.main()
