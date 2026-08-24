"""Проверка целостности документации.

Проверяет, что документация не «дрейфует» от кода и остаётся консистентной:

1. Ровно один README.md — в docs/, в корне репозитория README нет.
2. Все относительные ссылки в .md-файлах указывают на существующие файлы.
3. docs/index.md покрывает все файлы docs/ (каждый документ упомянут в индексе).

Точка входа: `make docs-check` или `uv run python scripts/check_docs.py`.
При любых проблемах печатает список и завершается с ненулевым кодом.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
README = "README.md"

# Ссылки вида [текст](путь) или [текст](путь "заголовок")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
# Исключаем внешние и якорные ссылки
SKIP_PREFIXES = ("http://", "https://", "mailto:", "#", "ftp://")


def _md_files() -> list[Path]:
    """Все markdown-файлы репозитория (кроме docs/, который обрабатываем отдельно)."""
    files: list[Path] = []
    for path in ROOT.rglob("*.md"):
        if ".git" in path.parts or ".venv" in path.parts:
            continue
        files.append(path)
    return files


def _relative_links(md: Path) -> list[Path]:
    """Относительные пути, на которые ссылается markdown-файл."""
    targets: list[Path] = []
    for match in LINK_RE.finditer(md.read_text(encoding="utf-8")):
        link = match.group(1).strip()
        if link.startswith(SKIP_PREFIXES):
            continue
        # Отбрасываем фрагмент-якорь и параметры
        link = link.split("#")[0].split(" ")[0]
        if not link:
            continue
        targets.append((md.parent / link).resolve())
    return targets


def check_links() -> list[str]:
    """Все относительные ссылки должны указывать на существующие файлы."""
    errors: list[str] = []
    for md in _md_files():
        for target in _relative_links(md):
            if not target.exists():
                rel = target.relative_to(ROOT)
                errors.append(f"{md.relative_to(ROOT)}: битая ссылка -> {rel}")
    return errors


def check_single_readme() -> list[str]:
    """Ровно один README.md — в docs/, в корне README нет.

    README.md внутри пакетов (packages/*/README.md) не в счёт: это readme
    отдельных uv-пакетов, ссылающиеся на них из packages/*/pyproject.toml.
    """
    errors: list[str] = []
    if (ROOT / README).exists():
        errors.append("README.md должен лежать в docs/, а не в корне репозитория")
    if not (DOCS / README).exists():
        errors.append(f"docs/{README} не существует — перенеси README в docs/")
    return errors


def check_index_covers_docs() -> list[str]:
    """docs/index.md должен упоминать каждый файл docs/."""
    errors: list[str] = []
    index = DOCS / "index.md"
    if not index.exists():
        return ["docs/index.md не существует — создай навигационный индекс"]
    index_text = index.read_text(encoding="utf-8")
    for doc in sorted(DOCS.glob("*.md")):
        if doc.name not in index_text:
            errors.append(f"docs/index.md не упоминает {doc.name}")
    return errors


def main() -> None:
    checks = [check_links, check_single_readme, check_index_covers_docs]
    errors: list[str] = []
    for check in checks:
        errors.extend(check())

    if errors:
        print("Документация требует внимания:")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)
    print(
        "Документация в порядке: ссылки валидны, README один, индекс покрывает все файлы."
    )


if __name__ == "__main__":
    main()
