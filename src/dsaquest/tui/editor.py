"""The C++ editor widget.

Textual's ``TextArea`` ships fifteen tree-sitter grammars and **C++ is not one
of them**, so ``TextArea(language="cpp")`` raises ``LanguageDoesNotExist``. In a
C++ trainer that is not a cosmetic problem: it took down every screen that
offered a code editor.

So the grammar is registered explicitly from ``tree-sitter-cpp``, and every step
of that is allowed to fail quietly. A missing grammar, an incompatible query
file, a tree-sitter version that rejects a predicate — none of these should stop
someone practising. They lose colour, not the exercise.

The highlight query needs both packages. ``tree-sitter-cpp``'s
``highlights.scm`` is a *delta* over ``tree-sitter-c``'s — seventy lines
covering ``class``, ``namespace``, ``template``, ``auto`` and little else. On
its own it captures **nothing** in ordinary code: no types, no keywords, no
numbers, no comments. Measured on ``int main() { int a[3]; ... }``, the C++
query alone produced 0 captures and the two concatenated produced 31. Without
the C base the editor is monochrome while still reporting itself as
syntax-aware, which is the worst of both.
"""

from __future__ import annotations

from functools import cache

from textual.widgets import TextArea

LANGUAGE = "cpp"


@cache
def _cpp_grammar() -> tuple[object, str] | None:
    """The tree-sitter C++ language and its highlight query, or None.

    Cached because building the grammar and reading the query file on every
    editor mount is wasted work, and because a failure will keep failing.
    """
    try:
        import tree_sitter
        import tree_sitter_cpp
    except ImportError:
        return None

    try:
        language = tree_sitter.Language(tree_sitter_cpp.language())
    except Exception:
        return None

    # C first, then the C++ delta on top. If the C base is missing we still
    # register what we have: partial colour beats none, and the editor works
    # either way.
    sources = []
    try:
        import tree_sitter_c

        sources.append(_highlights_of(tree_sitter_c))
    except Exception:
        pass
    sources.append(_highlights_of(tree_sitter_cpp))

    query = "\n".join(part for part in sources if part)
    return (language, query) if query else None


def _highlights_of(module: object) -> str:
    """A grammar package's highlights.scm, or empty if it does not ship one."""
    import pathlib

    try:
        root = pathlib.Path(module.__file__).parent  # type: ignore[attr-defined]
    except Exception:
        return ""
    path = root / "queries" / "highlights.scm"
    if not path.is_file():
        matches = sorted(root.rglob("highlights.scm"))
        if not matches:
            return ""
        path = matches[0]
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def cpp_highlighting_available() -> bool:
    return _cpp_grammar() is not None


def code_editor(
    text: str = "",
    *,
    id: str | None = None,
    show_line_numbers: bool = True,
    read_only: bool = False,
) -> TextArea:
    """A TextArea that highlights C++ when it can, and works regardless."""
    area = TextArea(
        text,
        id=id,
        show_line_numbers=show_line_numbers,
        tab_behavior="indent",
        read_only=read_only,
    )

    grammar = _cpp_grammar()
    if grammar is None:
        return area

    language, highlights = grammar
    try:
        area.register_language(LANGUAGE, language, highlights)
        area.language = LANGUAGE
    except Exception:
        # Colour is a nicety. Losing it must never cost the exercise.
        area.language = None
    return area
