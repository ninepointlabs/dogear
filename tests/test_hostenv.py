"""AppImage runtime variables are dropped only inside the Dogear AppImage."""

import unittest

from dogear import hostenv


class HostEnvTest(unittest.TestCase):
    def test_appimage_variables_removed(self):
        env = {"DOGEAR_APPIMAGE": "1", "APPIMAGE": "/a/Dogear.AppImage", "APPDIR": "/tmp/.mount",
               "ARGV0": "Dogear.AppImage", "OWD": "/home/u", "PATH": "/usr/bin", "HOME": "/home/u"}
        hostenv.restore(env)
        self.assertEqual(env, {"PATH": "/usr/bin", "HOME": "/home/u"})

    def test_untouched_outside_the_appimage(self):
        # Another AppImage that started Dogear from source: leave its variables.
        env = {"APPIMAGE": "/a/Other.AppImage", "APPDIR": "/tmp/.mount", "PATH": "/usr/bin"}
        hostenv.restore(env)
        self.assertEqual(env, {"APPIMAGE": "/a/Other.AppImage", "APPDIR": "/tmp/.mount", "PATH": "/usr/bin"})


if __name__ == "__main__":
    unittest.main()
