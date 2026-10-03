# SPDX-License-Identifier: MIT
import os
import plistlib
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stub import StubInstaller


class CopyAdminUsersTests(unittest.TestCase):
    def make_installer(self, preboot, vgid):
        installer = StubInstaller(None, None, None)
        installer.pb_vgid = os.path.join(preboot, vgid)
        installer.chflags = Mock()
        return installer

    def write_admin_users(self, preboot, vgid, user="admin"):
        path = os.path.join(
            preboot, vgid, "var/db/AdminUserRecoveryInfo.plist"
        )
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fd:
            plistlib.dump(
                {
                    user: {
                        "GeneratedUID": "00000000-0000-0000-0000-000000000000",
                        "RealName": "Admin User",
                    }
                },
                fd,
            )
        return path

    def test_source_may_already_be_the_target_in_recovery(self):
        with tempfile.TemporaryDirectory() as preboot:
            vgid = "A-VOLUME-GROUP"
            admin_users = self.write_admin_users(preboot, vgid)
            installer = self.make_installer(preboot, vgid)
            cur_os = SimpleNamespace(preboot=preboot, vgid=vgid)

            installer.copy_admin_users(cur_os)

            installer.chflags.assert_has_calls(
                [
                    call("noschg", admin_users),
                    call("schg", admin_users),
                ]
            )
            self.assertEqual(
                installer.stub_info["admin_users"]["admin"]["real_name"],
                "Admin User",
            )

    def test_different_source_is_still_copied(self):
        with tempfile.TemporaryDirectory() as root:
            source_preboot = os.path.join(root, "source")
            target_preboot = os.path.join(root, "target")
            vgid = "A-VOLUME-GROUP"
            self.write_admin_users(source_preboot, vgid, user="source-admin")
            target = self.write_admin_users(target_preboot, vgid, user="old-admin")
            installer = self.make_installer(target_preboot, vgid)
            cur_os = SimpleNamespace(preboot=source_preboot, vgid=vgid)

            installer.copy_admin_users(cur_os)

            with open(target, "rb") as fd:
                copied = plistlib.load(fd)
            self.assertEqual(list(copied), ["source-admin"])


if __name__ == "__main__":
    unittest.main()
