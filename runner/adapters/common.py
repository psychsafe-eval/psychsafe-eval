from __future__ import annotations

from typing import Any


def dump_sdk_object(obj: Any) -> Any:
    """Best-effort JSON-serializable preservation of an SDK response object."""
    if obj is None or isinstance(obj, (str, int, float, bool, list, dict)):
        return obj
    for method in ("model_dump", "to_dict"):
        fn = getattr(obj, method, None)
        if callable(fn):
            try:
                return fn()
            except Exception:
                pass
    return {"repr": repr(obj), "type": type(obj).__name__}


def require_nonempty_text(text: Any, provider: str) -> str:
    # Empty/non-text provider returns are administrative/contract problems, not
    # quality judgments and not silently converted into a successful answer.
    if not isinstance(text, str) or not text:
        from runner.core import AdministrationFailure
        raise AdministrationFailure(
            f"{provider} returned no renderable substantive text."
        )
    return text
