"""Keep HTTP composition separate from domain handlers and application globals."""
import ast
import unittest
from pathlib import Path


class ApiArchitectureTests(unittest.TestCase):
    def test_api_entrypoint_only_composes_routers(self):
        path = Path(__file__).resolve().parents[1] / 'dashboard' / 'api_v1.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        self.assertFalse(any(isinstance(node, ast.AsyncFunctionDef) for node in ast.walk(tree)))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                self.assertEqual(node.func.attr, 'include_router' if node.func.value.id == 'router' else 'create_router')

    def test_api_modules_do_not_import_application_or_create_global_dependencies(self):
        root = Path(__file__).resolve().parents[1] / 'dashboard' / 'api'
        for path in root.glob('*.py'):
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                modules = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module or ''] if isinstance(node, ast.ImportFrom) else []
                for module in modules:
                    self.assertNotIn(module, {'dashboard.app', 'dashboard.api_v1', 'app', 'config'}, str(path))
            for node in tree.body:
                if isinstance(node, (ast.Assign, ast.AnnAssign)):
                    self.assertFalse(any(isinstance(child, ast.Call) for child in ast.walk(node)), str(path))
