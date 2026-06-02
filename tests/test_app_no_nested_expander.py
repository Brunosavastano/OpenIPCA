"""Guard against the Streamlit 'expanders may not be nested' runtime error.

This bug shipped once because the smoke test only checked that the app *boots*,
not that a page *renders*. A static AST check is CI-safe (needs no data) and
directly encodes the rule: no `with st.expander(...)` may appear inside another
`with st.expander(...)` within the same function.
"""

import ast
import textwrap
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "dashboard" / "app.py"


def _is_expander_with(node: ast.AST) -> bool:
    """True if `node` is a `with st.expander(...):` statement."""
    if not isinstance(node, ast.With):
        return False
    for item in node.items:
        call = item.context_expr
        if (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "expander"
        ):
            return True
    return False


def _has_nested_expander(node: ast.AST, inside_expander: bool = False) -> bool:
    this_is_expander = _is_expander_with(node)
    if this_is_expander and inside_expander:
        return True
    child_inside = inside_expander or this_is_expander
    for child in ast.iter_child_nodes(node):
        if _has_nested_expander(child, child_inside):
            return True
    return False


def _first_function(source: str) -> ast.FunctionDef:
    tree = ast.parse(textwrap.dedent(source))
    return tree.body[0]


def test_nested_expander_guard_detects_bug_pattern():
    fn = _first_function(
        """
        def bad():
            with st.expander("outer"):
                with st.expander("inner"):
                    pass
        """
    )
    assert _has_nested_expander(fn)


def test_nested_expander_guard_allows_sequential_expanders():
    fn = _first_function(
        """
        def good():
            with st.expander("first"):
                pass
            with st.expander("second"):
                pass
        """
    )
    assert not _has_nested_expander(fn)


def test_app_has_no_nested_expanders():
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    # Check per-function so sequential top-level expanders are fine.
    offenders = [
        fn.name
        for fn in ast.walk(tree)
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
        and _has_nested_expander(fn)
    ]
    assert not offenders, f"Nested st.expander found in: {offenders}"
