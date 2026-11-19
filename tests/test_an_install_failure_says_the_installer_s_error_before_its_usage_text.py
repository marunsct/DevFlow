"""An install that failed says the installer's own error line, not only the end of its output.

Measured on one PHP run: `composer install` rejected a package name in the manifest - one error line - and then printed
its usage text, so the 600 characters the defect kept were the usage text ("[--prefer-source] [--dry-run] ...") and the
fixer saw no error at all; a fix round was spent before a later one found the manifest.
"""
from __future__ import annotations

from app.stacks import contract, pack_named

ERROR = ('  [InvalidArgumentException]\n'
         '  Could not parse version constraint for "Monolog/Monolog": the name does not match the regex pattern\n')
USAGE = "\n".join(f"  install [--prefer-source] [--dry-run] [--dev] [--no-dev] option-{n}" for n in range(40))


class _Failing:
    def __call__(self, argv, category, working_directory):
        return {"returncode": 1, "stdout": "", "stderr": ERROR + "\n" + USAGE}


def test_the_installer_s_error_line_is_in_the_note(tmp_path):
    contract.write(tmp_path, pack_named("node-library"), "shop", "Shop")
    (tmp_path / "shop").mkdir()
    (tmp_path / "shop" / "package.json").write_text('{"name": "shop", "dependencies": {"left-pad": "1.3.0"}}\n')

    notes = contract.install_if_the_manifests_changed(tmp_path, _Failing())

    assert notes and contract.INSTALL_FAILED in notes[0]
    assert "Could not parse version constraint" in notes[0]
    assert notes[0].index("Could not parse") < 900, "kept within what a defect keeps"
