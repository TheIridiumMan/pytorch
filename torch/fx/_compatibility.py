import textwrap
from typing import Any, Callable, Dict, TypeVar


F = TypeVar("F", bound=Callable)


_BACK_COMPAT_OBJECTS: Dict[Any, None] = {}
_MARKED_WITH_COMPATIBILITY: Dict[Any, None] = {}


def compatibility(is_backward_compatible: bool) -> Callable[[F], F]:
    if is_backward_compatible:

        def mark_back_compat(fn: F) -> F:
            docstring = textwrap.dedent(getattr(fn, "__doc__", None) or "")
            docstring += """
.. note::
    Backwards-compatibility for this API is guaranteed.
"""
            fn.__doc__ = docstring
            _BACK_COMPAT_OBJECTS.setdefault(fn)
            _MARKED_WITH_COMPATIBILITY.setdefault(fn)
            return fn

        return mark_back_compat
    else:

        def mark_not_back_compat(fn: F) -> F:
            docstring = textwrap.dedent(getattr(fn, "__doc__", None) or "")
            docstring += """
.. warning::
    This API is experimental and is *NOT* backward-compatible.
"""
            fn.__doc__ = docstring
            _MARKED_WITH_COMPATIBILITY.setdefault(fn)
            return fn

        return mark_not_back_compat
