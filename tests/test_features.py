import unittest

from feature_registry import FEATURES, get_feature


class FeatureRegistryTests(unittest.TestCase):
    def test_every_feature_has_dashboard_metadata(self):
        for feature in FEATURES:
            self.assertTrue(feature.category)
            self.assertTrue(feature.title_key)
            self.assertTrue(feature.description_key)
            self.assertTrue(feature.icon)
            self.assertTrue(all(permission.isidentifier() for permission in feature.required_bot_permissions))
            self.assertIs(get_feature(feature.id), feature)

    def test_required_fields_are_declared_in_the_module_fields(self):
        for feature in FEATURES:
            self.assertTrue(set(feature.required_fields).issubset(feature.fields))
