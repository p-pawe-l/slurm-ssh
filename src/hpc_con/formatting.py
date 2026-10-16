"""
Readable printing of the config dataclasses.
"""

from typing import Any


def format_fields(title: str, fields: list[tuple[str, Any]], missing: str) -> str:
    """
    Formats fields as an aligned block under a title. None values are shown
    as `missing`, lists and dicts as indented items below the field name.
    """
    width: int = max(len(name) for name, _ in fields) + 1
    lines: list[str] = [f"{title}:"]
    for name, value in fields:
        label: str = f"  {name + ':':<{width}}"
        if isinstance(value, dict | list):
            items: list[str] = (
                [f"{key}={item}" for key, item in value.items()]
                if isinstance(value, dict)
                else [str(item) for item in value]
            )
            if items:
                lines.append(f"  {name}:")
                lines += [f"    - {item}" for item in items]
            else:
                lines.append(f"{label} (none)")
        else:
            lines.append(f"{label} {missing if value is None else value}")
    return "\n".join(lines)
