import contextlib
import io
import json
import unittest
from unittest.mock import patch

import psycopg
import migrate


class MigrationDiagnosticsTests(unittest.TestCase):
    def test_connection_categories_never_echo_private_error_text(self):
        for message, code in (
            ('password authentication failed', 'database_authentication_failed'),
            ('database "private" does not exist', 'database_missing'),
            ('could not translate host name', 'database_dns_failed'),
            ('connection refused', 'database_connection_refused'),
            ('connection timeout expired', 'database_connection_timeout'),
            ('unknown failure', 'database_connection_failed'),
        ):
            with self.subTest(code=code):
                result = migrate.connection_failure(psycopg.OperationalError(message + ' private-password'))
                self.assertEqual(result[0], code)
                self.assertNotIn('private-password', str(result))

    def test_main_reports_safe_failure_and_nonzero_exit(self):
        output = io.StringIO()
        with patch.object(migrate, 'configure_logging'), patch.object(migrate, 'load_environment'), \
             patch('sys.argv', ['migrate.py']), \
             patch.object(migrate, 'apply', side_effect=psycopg.OperationalError('password authentication failed private-password')), \
             contextlib.redirect_stderr(output), self.assertRaises(SystemExit) as caught:
            migrate.main()
        self.assertEqual(caught.exception.code, 1)
        self.assertEqual(json.loads(output.getvalue())['code'], 'database_authentication_failed')
        self.assertNotIn('private-password', output.getvalue())
