import ast
import json
from pathlib import Path
import unittest

from features.registry import FEATURES


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


class DocumentationTests(unittest.TestCase):
    def test_documented_maturity_is_generated_from_the_registry(self):
        values=json.loads((DOCS/'reference/feature-maturity.json').read_text(encoding='utf-8'))
        self.assertEqual(values,{feature.id:feature.maturity for feature in FEATURES})
        for feature in FEATURES:
            relative=feature.docs_path.removeprefix('/docs/')
            for prefix in ('','en/'):
                page=DOCS/f'{prefix}{relative}.md'
                self.assertIn(f'feature_id: {feature.id}',page.read_text(encoding='utf-8'))

    def test_every_feature_has_a_canonical_japanese_page(self):
        for feature in FEATURES:
            relative = feature.docs_path.removeprefix("/docs/")
            page = DOCS / f"{relative}.md"
            self.assertTrue(page.exists(), f"Missing documentation for {feature.id}: {page}")
            text = page.read_text(encoding="utf-8")
            self.assertIn(f"feature_id: {feature.id}", text)

    def test_feature_documentation_paths_are_unique(self):
        paths = [feature.docs_path for feature in FEATURES]
        self.assertEqual(len(paths), len(set(paths)))

    def test_every_example_environment_variable_is_documented(self):
        reference_path = ROOT / 'handbook/operator/environment.md'
        if not reference_path.exists():
            self.assertFalse((DOCS / 'reference/environment.md').exists())
            return  # Private handbook is intentionally not shipped in runtime images.
        reference = reference_path.read_text(encoding="utf-8")
        keys = []
        for line in (ROOT / "deploy/app.env.example").read_text(encoding="utf-8").splitlines():
            if line and not line.startswith("#") and "=" in line:
                keys.append(line.split("=", 1)[0])
        missing = [key for key in keys if f"`{key}`" not in reference]
        self.assertEqual(missing, [])

    def test_configure_template_covers_runtime_configuration_reads(self):
        from deploy.env_template import TEMPLATE, parse
        keys = set(parse(TEMPLATE.read_text(encoding='utf-8'), TEMPLATE))
        # These are selected by the launcher or test harness, not app.env settings.
        managed = {'TUEKA_ENV_FILE', 'TUEKA_SERVICE', 'TUEKA_TEST_DATABASE_URL'}
        missing = set()
        paths = [*ROOT.glob('*.py')]
        for directory in ('dashboard', 'database', 'runtime', 'observability', 'cogs', 'social', 'ticketing'):
            paths.extend((ROOT / directory).rglob('*.py'))
        for path in paths:
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.args:
                    owner = ast.unparse(node.func.value)
                    if (owner, node.func.attr) not in {('os', 'getenv'), ('os.environ', 'get')}:
                        continue
                    key = node.args[0]
                    if isinstance(key, ast.Constant) and isinstance(key.value, str) and key.value not in keys | managed:
                        missing.add(key.value)
        self.assertEqual(missing, set(), 'Add new application settings to deploy/app.env.example')

    def test_application_commands_are_present_in_reference(self):
        reference = (DOCS / "reference" / "commands.md").read_text(encoding="utf-8")
        names: set[str] = set()
        for path in (ROOT / "cogs").glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for decorator in node.decorator_list:
                    call = decorator if isinstance(decorator, ast.Call) else None
                    target = call.func if call else decorator
                    if not isinstance(target, ast.Attribute) or target.attr != "command":
                        continue
                    name = node.name
                    if call:
                        for keyword in call.keywords:
                            if keyword.arg == "name" and isinstance(keyword.value, ast.Constant):
                                name = str(keyword.value.value)
                    names.add(name)
        missing = [name for name in sorted(names) if name not in reference]
        self.assertEqual(missing, [])

    def test_public_docs_and_swagger_do_not_share_a_route(self):
        source = (ROOT / "dashboard" / "app.py").read_text(encoding="utf-8")
        self.assertIn('docs_url="/api/docs"', source)
        self.assertIn('openapi_url="/api/openapi.json"', source)
        self.assertIn('app.mount("/docs"', source)

    def test_public_docs_have_english_parity_and_no_private_pages(self):
        for page in DOCS.rglob('*.md'):
            relative = page.relative_to(DOCS)
            if relative.parts[0] in ('en', 'node_modules', '.vitepress'):
                continue
            self.assertTrue((DOCS / 'en' / relative).exists(), str(relative))
            self.assertNotIn('handbook/', page.read_text(encoding='utf-8'))
        for relative in ('operations', 'reference/environment.md', 'reference/architecture.md',
                         'reference/api.md', 'reference/extending.md', 'social/worker.md',
                         'EXECUTION_PLAN.md', 'PROGRESS0910.md', 'TESTING.md', 'inventory', 'en/operations.md'):
            self.assertFalse((DOCS / relative).exists(), relative)

    def test_no_document_contains_example_secrets(self):
        forbidden = ("DISCORD_TOKEN=", "SESSION_SECRET=", "PRIVATE KEY-----", "Authorization: Bot ")
        for page in DOCS.rglob("*.md"):
            text = page.read_text(encoding="utf-8")
            for marker in forbidden:
                self.assertNotIn(marker, text, f"Secret-like marker in {page}")


if __name__ == "__main__":
    unittest.main()
