import unittest

from features.registry import FEATURES, get_feature, japanese_copy
from dashboard.icon_registry import ICONS, get_icon


class FeatureRegistryTests(unittest.TestCase):
    def test_every_feature_has_dashboard_metadata(self):
        for feature in FEATURES:
            self.assertTrue(feature.category)
            self.assertTrue(feature.title_key)
            self.assertTrue(feature.description_key)
            self.assertTrue(feature.icon)
            self.assertTrue(feature.docs_path.startswith("/docs/"))
            self.assertIn(feature.icon, ICONS)
            icon = get_icon(feature.icon)
            self.assertTrue(icon.label)
            self.assertTrue(icon.paths)
            self.assertNotIn("<script", icon.paths.lower())
            self.assertNotIn("onload=", icon.paths.lower())
            self.assertTrue(all(permission.isidentifier() for permission in feature.required_bot_permissions))
            self.assertIs(get_feature(feature.id), feature)
            title, description = japanese_copy(feature.id)
            self.assertTrue(title)
            self.assertTrue(description)

    def test_required_fields_are_declared_in_the_module_fields(self):
        for feature in FEATURES:
            self.assertTrue(set(feature.required_fields).issubset(feature.fields))

    def test_documentation_paths_are_unique(self):
        paths = [feature.docs_path for feature in FEATURES]
        self.assertEqual(len(paths), len(set(paths)))

    def test_unknown_icon_is_rejected(self):
        with self.assertRaises(ValueError):
            get_icon("not-an-icon")
