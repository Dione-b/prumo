from __future__ import annotations

import pathlib

LICENSE_BLOCK = """# Copyright (C) 2026 Dione Bastos
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

# Raiz do repositório: o diretório onde este script está
ROOT = pathlib.Path(__file__).resolve().parent


def should_skip(path: pathlib.Path) -> bool:
    """
    Limita o escopo *dentro* do repo e evita diretórios de ambiente/IDE.
    """
    # Garante que o path está dentro de ROOT
    try:
        path.relative_to(ROOT)
    except ValueError:
        return True

    parts = set(path.parts)

    # Ignorar ambientes/artefatos
    skip_dirs = {
        ".git",
        ".venv",
        ".env",
        ".cursor",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
    }
    if any(d in parts for d in skip_dirs):
        return True

    return False


def file_already_has_license(text: str) -> bool:
    return (
        "GNU Affero General Public License" in text
        or "This program is free software:" in text
    )


def add_header_to_file(path: pathlib.Path) -> None:
    text = path.read_text(encoding="utf-8")
    if file_already_has_license(text):
        return

    lines = text.splitlines(keepends=True)

    # Preserva shebang na primeira linha, se existir
    if lines and lines[0].startswith("#!"):
        new_text = (
            lines[0]
            + "\n"
            + LICENSE_BLOCK
            + "\n"
            + "".join(lines[1:])
        )
    else:
        new_text = LICENSE_BLOCK + "\n\n" + text

    path.write_text(new_text, encoding="utf-8")
    print(f"Updated: {path.relative_to(ROOT)}")


def main() -> None:
    # Opcional: restrinja ainda mais o escopo se quiser
    # for base in ["app", "tests", "graph_worker"]:
    #     for path in (ROOT / base).rglob("*.py"):

    for path in ROOT.rglob("*.py"):
        if should_skip(path):
            continue
        add_header_to_file(path)


if __name__ == "__main__":
    main()