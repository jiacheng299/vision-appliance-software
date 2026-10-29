import importlib.util
from pathlib import Path
import tempfile
import unittest


class LauncherTests(unittest.TestCase):
    def test_linked_worktree_reuses_checkout_runtime(self):
        path = Path(__file__).resolve().parents[2] / 'app.py'
        spec = importlib.util.spec_from_file_location('launcher', path)
        launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(launcher)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            checkout = root / 'checkout'
            worktree = root / 'feature'
            metadata = checkout / '.git/worktrees/feature'
            metadata.mkdir(parents=True)
            worktree.mkdir()
            (worktree / '.git').write_text('gitdir: ' + str(metadata), encoding='utf8')
            self.assertEqual(launcher.runtime_root(worktree), checkout)


if __name__ == '__main__':
    unittest.main()
