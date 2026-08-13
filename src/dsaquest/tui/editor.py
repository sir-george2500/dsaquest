"""The C++ editor widget.

Textual's ``TextArea`` ships fifteen tree-sitter grammars and **C++ is not one
of them**, so ``TextArea(language="cpp")`` raises ``LanguageDoesNotExist``. In a
C++ trainer that is not a cosmetic problem: it took down every screen that
offered a code editor.

So the grammar is registered explicitly from ``tree-sitter-cpp``, and every step
of that is allowed to fail quietly. A missing grammar, an incompatible query
file, a tree-sitter version that rejects a predicate — none of these should stop
someone practising. They lose colour, not the exercise.
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
        import pathlib

        import tree_sitter
        import tree_sitter_cpp
    except ImportError:
        return None

    try:
        language = tree_sitter.Language(tree_sitter_cpp.language())
        query = pathlib.Path(tree_sitter_cpp.__file__).parent / "queries" / "highlights.scm"
        if not query.is_file():
            matches = list(pathlib.Path(tree_sitter_cpp.__file__).parent.rglob("highlights.scm"))
            if not matches:
                return None
            query = matches[0]
        return language, query.read_text(encoding="utf-8")
    except Exception:
        return None


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
