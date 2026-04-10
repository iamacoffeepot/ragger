"""MCP tool auto-registration from annotated Python API methods."""

from __future__ import annotations

import dataclasses
import enum
import importlib
import inspect
import json
import sqlite3
from typing import Any, get_type_hints


_tools: list[dict[str, Any]] = []


def mcp_tool(*, name: str, description: str):
    """Mark a method for MCP tool registration.

    Works on classmethods and instance methods. Apply before @classmethod
    for classmethods::

        @classmethod
        @mcp_tool(name="ItemByName", description="Find an item by exact name")
        def by_name(cls, conn: sqlite3.Connection, name: str) -> Item | None:
            ...

    For instance methods, the owning class must implement ``by_id(cls, conn, id)``::

        @mcp_tool(name="QuestSkillRequirements", description="Skill requirements for a quest")
        def skill_requirements(self, conn: sqlite3.Connection) -> list[GroupSkillRequirement]:
            ...

    The registry detects ``self`` vs ``cls`` and handles lookup automatically.
    Instance method tools get an ``id: int`` parameter injected.
    """

    def decorator(fn):
        _tools.append({"name": name, "description": description, "fn": fn})
        return fn

    return decorator


def _serialize(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, list):
        return [_serialize(item) for item in obj]
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        if not hasattr(obj, "asdict"):
            raise TypeError(
                f"{type(obj).__name__} must implement asdict() to be returned from an MCP tool"
            )
        return obj.asdict()
    if isinstance(obj, enum.Enum):
        return obj.value
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, (int, float, str, bool)):
        return obj
    return str(obj)


def _unwrap_enum(annotation: Any) -> type[enum.Enum] | None:
    """Extract the enum type from an annotation, handling Optional[Enum] and Enum | None."""
    if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
        return annotation
    args = getattr(annotation, "__args__", None)
    if args is None:
        return None
    for arg in args:
        if isinstance(arg, type) and issubclass(arg, enum.Enum):
            return arg
    return None


def _is_enum_type(annotation: Any) -> bool:
    return _unwrap_enum(annotation) is not None


def _coerce_enum(value: Any, enum_type: type[enum.Enum]) -> enum.Enum:
    """Coerce a string value to an enum member by name, then by value."""
    if isinstance(value, enum_type):
        return value

    by_name = value.upper().replace(" ", "_") if isinstance(value, str) else str(value)
    try:
        return enum_type[by_name]
    except KeyError:
        pass

    try:
        return enum_type(value)
    except ValueError:
        pass

    members = ", ".join(enum_type.__members__)
    raise ValueError(f"{value!r} is not a valid {enum_type.__name__} (expected one of: {members})")


def _schema_annotation(annotation: Any) -> Any:
    """Map a Python type hint to something FastMCP can express as JSON schema."""
    if _is_enum_type(annotation):
        return str
    return annotation


def _resolve_owner(fn) -> type | None:
    """Resolve the owning class of a method from its __qualname__."""
    qualname = fn.__qualname__
    if "." not in qualname:
        return None
    class_name = qualname.rsplit(".", 1)[0]
    module = importlib.import_module(fn.__module__)
    return getattr(module, class_name, None)


def register_all(mcp, db_path: str) -> None:
    """Register all @mcp_tool-decorated functions with a FastMCP server."""

    for entry in _tools:
        tool_name: str = entry["name"]
        description: str = entry["description"]
        fn = entry["fn"]

        sig = inspect.signature(fn)
        try:
            hints = get_type_hints(fn)
        except Exception:
            hints = fn.__annotations__

        owner_cls = _resolve_owner(fn)
        param_names = list(sig.parameters.keys())
        is_instance = param_names and param_names[0] == "self"

        if is_instance and owner_cls is not None and not hasattr(owner_cls, "by_id"):
            raise TypeError(
                f"{owner_cls.__name__} must implement by_id(cls, conn, id) "
                f"for instance method tool {tool_name}"
            )

        skip = {"cls", "self", "conn"}
        exposed = [n for n in param_names if n not in skip]

        coercions: dict[str, type[enum.Enum]] = {}
        new_params = []
        new_annotations: dict[str, Any] = {}

        if is_instance:
            new_params.append(
                inspect.Parameter(
                    "id",
                    kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    annotation=int,
                )
            )
            new_annotations["id"] = int

        for param_name in exposed:
            original = sig.parameters[param_name]
            annotation = hints.get(param_name, str)

            enum_type = _unwrap_enum(annotation)
            if enum_type is not None:
                coercions[param_name] = enum_type

            schema_type = _schema_annotation(annotation)
            new_params.append(
                inspect.Parameter(
                    param_name,
                    kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    default=original.default,
                    annotation=schema_type,
                )
            )
            new_annotations[param_name] = schema_type

        if is_instance:

            def _make_instance_handler(fn, owner_cls, db_path, coercions):
                def handler(**kwargs):
                    entity_id = kwargs.pop("id")
                    for param_name, enum_type in coercions.items():
                        if param_name in kwargs:
                            kwargs[param_name] = _coerce_enum(kwargs[param_name], enum_type)

                    conn = sqlite3.connect(db_path)
                    try:
                        instance = owner_cls.by_id(conn, entity_id)
                        if instance is None:
                            return json.dumps(None)
                        result = fn(instance, conn, **kwargs)
                        return json.dumps(_serialize(result))
                    finally:
                        conn.close()

                return handler

            handler = _make_instance_handler(fn, owner_cls, db_path, coercions)

        else:

            def _make_handler(fn, owner_cls, db_path, coercions):
                def handler(**kwargs):
                    for param_name, enum_type in coercions.items():
                        if param_name in kwargs:
                            kwargs[param_name] = _coerce_enum(kwargs[param_name], enum_type)

                    conn = sqlite3.connect(db_path)
                    try:
                        if owner_cls is not None:
                            result = fn(owner_cls, conn, **kwargs)
                        else:
                            result = fn(conn, **kwargs)
                        return json.dumps(_serialize(result))
                    finally:
                        conn.close()

                return handler

            handler = _make_handler(fn, owner_cls, db_path, coercions)

        handler.__name__ = tool_name
        handler.__qualname__ = tool_name
        handler.__doc__ = description
        handler.__signature__ = inspect.Signature(new_params)
        handler.__annotations__ = new_annotations
        handler.__module__ = fn.__module__

        mcp.tool(name=tool_name)(handler)
