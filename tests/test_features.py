import unittest

from feature_registry import FEATURES, get_feature


class FeatureRegistryTests(unittest.TestCase):
    def test_every_feature_has_dashboard_metadata(self):
        for feature in FEATURES:
            self.assertTrue(feature.category)
            self.assertTrue(feature.title_key)
            self.assertTrue(feature.description_key)
            self.assertTrue(feature.icon)
            self.assertIs(get_feature(feature.id), feature)
