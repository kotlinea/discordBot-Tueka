"""The image dispatcher must preserve command arguments and process ownership."""
import unittest
import asyncio
import signal
from unittest.mock import patch

from runtime.__main__ import COMMANDS, main
from runtime.lifecycle import run


class RuntimeTests(unittest.TestCase):
    def test_dispatch_executes_each_entry_point(self):
        for name, command in COMMANDS.items():
            with self.subTest(name=name), patch('sys.argv', ['tueka', name, '--help']), patch('os.execvp') as execute:
                main()
                execute.assert_called_once_with('python', [*command, '--help'])

    def test_unknown_command_fails_without_starting_process(self):
        with patch('sys.argv', ['tueka', 'unknown']), patch('os.execvp') as execute:
            with self.assertRaises(SystemExit) as error:
                main()
            self.assertEqual(error.exception.code, 2)
            execute.assert_not_called()

    def test_sigterm_cancels_service_and_closes_resources(self):
        cleaned = []
        previous = signal.getsignal(signal.SIGTERM)

        async def service():
            try:
                signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
                await asyncio.sleep(60)
            finally:
                cleaned.append(True)

        with patch('runtime.lifecycle.close_pools') as close:
            run(service)
            close.assert_called_once()
        self.assertEqual(cleaned, [True])
        self.assertIs(signal.getsignal(signal.SIGTERM), previous)

    def test_service_failure_is_not_reported_as_clean_shutdown(self):
        async def service():
            raise RuntimeError('service failed')

        with patch('runtime.lifecycle.close_pools') as close:
            with self.assertRaisesRegex(RuntimeError, 'service failed'):
                run(service)
            close.assert_called_once()
