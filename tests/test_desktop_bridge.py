"""Regression guard for Windows pywebview infinite JS API introspection."""
import inspect
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mv_server import DesktopApi

class DesktopBridgeTests(unittest.TestCase):
    def test_native_window_is_private_and_bridge_surface_is_methods_only(self):
        # Native window must never be a PUBLIC property on a js_api object.
        # Older code used self.window; pywebview walked window.native and froze.
        api = DesktopApi()
        native = object()
        api._window = native
        self.assertIs(api._window, native)
        self.assertFalse(hasattr(api, 'window'))
        exposed = {name: getattr(api, name) for name in dir(api)
                   if not name.startswith('_')}
        self.assertEqual(set(exposed), {'pick_folder', 'pick_imdb', 'pick_backup'})
        self.assertTrue(all(callable(value) for value in exposed.values()))
        self.assertTrue(all(not inspect.signature(value).parameters for value in exposed.values()))

if __name__ == '__main__':
    unittest.main()
