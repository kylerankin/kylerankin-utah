"""Every dconf section in 08-dakota-extension-defaults must match a shipped schema path.

`08-dakota-extension-defaults` sets defaults for shell extensions that compile
their own GSettings schemas. GNOME reads a schema's declared `path`, not the
extension's folder name (the UUID), so a section header only takes effect when
it equals the `path=` of a schema the extension actually ships. A header that
points at a path no schema declares is silently ignored: the key falls back to
the extension's own compiled default, so the value written here does nothing.

The headers here use the short schema path (for example
`org/gnome/shell/extensions/tilingshell`), never the UUID folder name (for
example `tilingshell@ferrarodomenico.com`). This guard reads every
`.gschema.xml` the extensions ship, collects the `path=` each one declares, and
asserts that every section header matches one of them. A future schema whose
`path=` is moved or renamed -- or a header typed at a path nothing compiles --
fails here instead of shipping a setting that never applies.
"""
import configparser
import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
DCONF = ROOT / "system_files/shared/etc/dconf/db/distro.d/08-dakota-extension-defaults"
EXTENSIONS = ROOT / "system_files/shared/usr/share/gnome-shell/extensions"
PATH_ATTR = re.compile(r'path="([^"]+)"')


def _normalize(path):
    # A schema path is "/org/gnome/shell/extensions/tilingshell/"; a dconf
    # section header is "org/gnome/shell/extensions/tilingshell". Drop the
    # surrounding slashes on both sides so they compare equal.
    return path.strip("/")


class DakotaExtensionDefaultsTests(unittest.TestCase):
    def test_every_section_header_matches_a_shipped_schema_path(self):
        if not EXTENSIONS.is_dir():
            self.skipTest("extensions directory not checked out")

        schemas = sorted(EXTENSIONS.rglob("*.gschema.xml"))
        if not schemas:
            self.skipTest("extension submodules not initialized")

        declared = {}
        for schema in schemas:
            text = schema.read_text(encoding="utf-8")
            for match in PATH_ATTR.findall(text):
                key = _normalize(match)
                # blur-my-shell declares several sub-paths in one file; keep the
                # folder name that owns each path for a helpful failure message.
                declared.setdefault(key, schema.relative_to(EXTENSIONS).parent.name)

        config = configparser.ConfigParser()
        config.read(DCONF)

        for section in config.sections():
            with self.subTest(section=section):
                self.assertIn(
                    section,
                    declared,
                    (
                        f"section '{section}' matches no schema path the shipped "
                        f"extensions declare; the keys under it are ignored and the "
                        f"extension uses its own compiled default"
                    ),
                )


if __name__ == "__main__":
    unittest.main()
