"""Focused tests for the plan catalog generator and validator."""
import tempfile
import unittest
from pathlib import Path

from otto.checks import local_links


class CatalogTests(unittest.TestCase):
    def test_relative_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'plans').mkdir()
            (root / 'README.md').write_text('[ok](plans/) and [missing](absent.md)\n')
            self.assertEqual(len(local_links(root, Path('README.md'))), 1)
