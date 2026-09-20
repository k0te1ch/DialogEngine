"""aiogram — необязательная зависимость, и это проверяется, а не декларируется."""

import subprocess
import sys

from dialog_engine import __version__

BLOCK_AIOGRAM_AND_IMPORT = """
import sys
from importlib.abc import MetaPathFinder


class Blocker(MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name == "aiogram" or name.startswith("aiogram."):
            raise ImportError("aiogram не установлен (имитация)")
        return None


sys.meta_path.insert(0, Blocker())

import dialog_engine

print(dialog_engine.__version__)
"""


def test_core_package_imports_without_aiogram():
    result = subprocess.run(
        [sys.executable, "-c", BLOCK_AIOGRAM_AND_IMPORT],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == __version__
