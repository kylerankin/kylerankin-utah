"""`99-privileged.sh` must not escalate from any GDM session.

GDM runs these per-user hooks from greeter and initial-setup sessions
before any real user logs in. Those sessions run as a transient account:
the `gdm-greeter` account, or another `gdm-*` account under `/run/gdm/home`
(GDM 49+ runs initial-setup this way, and its SHELL is not listed in
`/etc/shells`), so `pkexec` logs an error for each one (issues #688, #691).
Privileged hooks stamp once-only completion system-wide, so the greeter and
initial-setup sessions have nothing to do here: the hook must skip them and
let the first real login escalate and run them.

The first half of this file is a static contract check on the hook source.
The second half drives the real hook against stub `id`/`pkexec` binaries to
prove the greeter, an arbitrary `gdm-*` account, and a `/run/gdm/home` HOME
all skip without escalating while a normal user still reaches
`ublue-privileged-setup`.
"""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = (
    ROOT
    / "system_files/shared/usr/share/ublue-os/user-setup.hooks.d"
    / "99-privileged.sh"
)


class PrivilegedHookGdmContractTests(unittest.TestCase):
    def setUp(self):
        self.body = HOOK.read_text()
        self.lines = [
            line.strip()
            for line in self.body.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

    def test_hook_exists(self):
        self.assertTrue(HOOK.is_file())

    def test_still_escalates_to_privileged_setup(self):
        self.assertIn("pkexec /usr/bin/ublue-privileged-setup", self.lines)

    def test_guard_matches_the_gdm_account_pattern(self):
        # Not a single literal name: a `gdm-*` glob also catches the
        # initial-setup transient account GDM 49+ uses (#691).
        self.assertIn("gdm-*", self.body)

    def test_guard_matches_the_gdm_home_pattern(self):
        # A transient account may run with its HOME under /run/gdm/home
        # even when its name is not matched by the id check (#691).
        self.assertIn("/run/gdm/home", self.body)

    def test_guard_runs_before_the_escalation(self):
        self.assertLess(
            self.body.index("gdm-*"),
            self.body.index("pkexec /usr/bin/ublue-privileged-setup"),
        )

    def test_body_failure_aborts(self):
        # `set -e` keeps a failed escalation from falling through silently.
        self.assertIn("set -euo pipefail", self.lines)
        self.assertLess(
            self.lines.index("set -euo pipefail"),
            self.lines.index("pkexec /usr/bin/ublue-privileged-setup"),
        )


class PrivilegedHookGdmBehaviourTests(unittest.TestCase):
    """Drive the real hook with the invoking user and HOME controlled by
    stub `id`/`pkexec` binaries."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.fake = Path(self.tmp.name)
        bin_dir = self.fake / "bin"
        bin_dir.mkdir()

        # `id` stub: report the user under test instead of the host user.
        stub_id = bin_dir / "id"
        stub_id.write_text('#!/usr/bin/env bash\necho "${HOOK_TEST_USER}"\n')
        stub_id.chmod(0o755)

        # `pkexec` stub: record its args so tests can assert whether the
        # hook escalated, then succeed like the real privileged setup.
        pkexec = bin_dir / "pkexec"
        pkexec.write_text(
            "#!/usr/bin/env bash\n"
            'mkdir -p "${HOOK_STATE_DIR}"\n'
            'echo "$@" >> "${HOOK_STATE_DIR}/pkexec_args"\n'
            "exit 0\n"
        )
        pkexec.chmod(0o755)

        self.env = dict(os.environ)
        self.env["PATH"] = f"{bin_dir}:{os.environ['PATH']}"
        self.env["HOOK_STATE_DIR"] = str(self.fake / "state")

    def run_hook(self, user, home="/home/someuser"):
        self.env["HOOK_TEST_USER"] = user
        self.env["HOME"] = home
        return subprocess.run(
            ["bash", str(HOOK)],
            env=self.env,
            capture_output=True,
            text=True,
            check=False,
        )

    def pkexec_calls(self):
        log = self.fake / "state" / "pkexec_args"
        if not log.is_file():
            return []
        return log.read_text().splitlines()

    def test_greeter_skips_without_escalating(self):
        """The gdm-greeter session must exit 0 without invoking pkexec, so
        no /etc/shells error is logged for a session that has no privileged
        work to do anyway."""
        proc = self.run_hook("gdm-greeter")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.pkexec_calls(), [])

    def test_initial_setup_account_skips_without_escalating(self):
        """Another gdm-* transient account (GDM 49+ initial-setup) must also
        skip, not only the literal gdm-greeter name (#691)."""
        proc = self.run_hook("gdm-initial-setup")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.pkexec_calls(), [])

    def test_gdm_home_skips_without_escalating(self):
        """A transient session whose HOME is under /run/gdm/home must skip
        even when its name is not matched by the id check (#691)."""
        proc = self.run_hook("somebody", home="/run/gdm/home/somebody")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.pkexec_calls(), [])

    def test_real_user_still_escalates(self):
        """A normal login must reach ublue-privileged-setup exactly as
        before, or the once-only privileged hooks would never run."""
        proc = self.run_hook("someuser")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.pkexec_calls(), ["/usr/bin/ublue-privileged-setup"])


if __name__ == "__main__":
    unittest.main()
