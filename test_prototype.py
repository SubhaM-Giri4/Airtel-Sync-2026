import unittest

import server


class PrototypeLogicTests(unittest.TestCase):
    def test_dashboard_uses_supplied_synthetic_leads(self):
        dashboard = server.make_dashboard()
        self.assertEqual(dashboard["lead_count"], 5000)
        self.assertEqual(dashboard["activated_count"], 368)
        self.assertEqual([stage["count"] for stage in dashboard["stages"]], [5000, 3406, 1974, 861, 588, 368])
        self.assertEqual(dashboard["acquisition_cost"], 15053)

    def test_recommendation_is_eligible_and_catalogue_priced(self):
        quote = server.recommend({
            "segment": "professional",
            "city_tier": 2,
            "employees": 6,
            "sites": 1,
        })
        ids = {item["product_id"] for item in quote["products"]}
        self.assertIn("P02", ids)
        self.assertNotIn("P12", ids)
        self.assertEqual(quote["monthly_min"], sum(item["monthly_min"] for item in quote["products"]))
        self.assertEqual(quote["monthly_max"], sum(item["monthly_max"] for item in quote["products"]))

    def test_registry_lookup_requires_consent_and_masks_identifier(self):
        identifier = next(iter(server.GSTIN_REGISTRY))
        with self.assertRaises(ValueError):
            server.lookup_registry({"type": "gstin", "identifier": identifier})
        result = server.lookup_registry({"type": "gstin", "identifier": identifier, "consent": True})
        self.assertTrue(result["found"])
        self.assertNotIn(identifier, result["masked_identifier"])

    def test_recommendation_rejects_unknown_segment(self):
        with self.assertRaises(ValueError):
            server.recommend({"segment": "unknown", "city_tier": 1, "employees": 1, "sites": 1})


if __name__ == "__main__":
    unittest.main()
