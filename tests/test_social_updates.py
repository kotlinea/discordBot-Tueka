import unittest

from cryptography.fernet import Fernet

from cogs.social_updates import SocialUpdatesCog
from social_crypto import SocialTokenCipher


class SocialUpdateTests(unittest.TestCase):
    def test_template_replaces_only_supported_variables(self):
        text = SocialUpdatesCog.render_template("{account}: {title} {unknown}", {"account": "Tueka", "title": "Live"})
        self.assertEqual(text, "Tueka: Live {unknown}")

    def test_template_is_bounded(self):
        self.assertLessEqual(len(SocialUpdatesCog.render_template("x" * 3000, {})), 1900)

    def test_oauth_tokens_are_encrypted_at_the_storage_boundary(self):
        cipher = SocialTokenCipher(Fernet.generate_key().decode("ascii"))
        encrypted = cipher.encrypt("secret-token")
        self.assertNotEqual(encrypted, "secret-token")
        self.assertEqual(cipher.decrypt(encrypted), "secret-token")
