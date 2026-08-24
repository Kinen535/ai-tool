from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


class WorkspaceDataBoundaryError(ValueError):
    """Raised when a Workspace data boundary is missing or invalid."""


@dataclass(frozen=True)
class WorkspaceDataBoundary:
    workspace_id: int
    battle_ids: tuple[int, ...]
    current_battle_id: int
    permissions: tuple[str, ...]


def _positive_int(value: object, *, field: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise WorkspaceDataBoundaryError(
            f"{field} must be an integer"
        ) from exc

    if result <= 0:
        raise WorkspaceDataBoundaryError(
            f"{field} must be positive"
        )

    return result


def resolve_workspace_data_boundary(
    context: object,
) -> WorkspaceDataBoundary:
    """Validate and normalize the request Workspace data boundary."""

    if not isinstance(context, Mapping):
        raise WorkspaceDataBoundaryError(
            "workspace access context is missing"
        )

    workspace_id = _positive_int(
        context.get("workspace_id"),
        field="workspace_id",
    )

    raw_battle_ids = context.get(
        "battle_ids"
    )

    if not isinstance(
        raw_battle_ids,
        (
            list,
            tuple,
            set,
            frozenset,
        ),
    ):
        raise WorkspaceDataBoundaryError(
            "battle_ids must be a collection"
        )

    battle_ids = tuple(
        sorted(
            {
                _positive_int(
                    item,
                    field="battle_ids",
                )
                for item
                in raw_battle_ids
            }
        )
    )

    if not battle_ids:
        raise WorkspaceDataBoundaryError(
            "battle_ids must not be empty"
        )

    current_battle_id = _positive_int(
        context.get(
            "current_battle_id"
        ),
        field="current_battle_id",
    )

    if current_battle_id not in battle_ids:
        raise WorkspaceDataBoundaryError(
            "current_battle_id is outside allowed battle_ids"
        )

    raw_permissions = context.get(
        "permissions"
    )

    if not isinstance(
        raw_permissions,
        (
            list,
            tuple,
            set,
            frozenset,
        ),
    ):
        raise WorkspaceDataBoundaryError(
            "permissions must be a collection"
        )

    permissions = tuple(
        sorted(
            {
                str(item).strip()
                for item
                in raw_permissions
                if str(item).strip()
            }
        )
    )

    return WorkspaceDataBoundary(
        workspace_id=workspace_id,
        battle_ids=battle_ids,
        current_battle_id=current_battle_id,
        permissions=permissions,
    )
