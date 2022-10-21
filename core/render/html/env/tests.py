from typing import Any

from ..default import Render
from ..utils import jinjaGlobalTest


@jinjaGlobalTest
def test_dict(render: Render, value: Any) -> bool:
    """Jinja2 test: Return True if the object is a dict."""
    return isinstance(value, dict)


@jinjaGlobalTest
def test_list(render: Render, value: Any) -> bool:
    """Jinja2 test: Return True if the object is a list."""
    return isinstance(value, list)
