from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from services.v155_rbac_workspace_resolver import has_permission


PROTECTED_PATH_METHOD_PERMISSIONS: dict[
    str,
    dict[str, tuple[str, str]],
] = {'/': {'GET': ('dashboard.view', ''), 'HEAD': ('dashboard.view', ''), 'OPTIONS': ('dashboard.view', '')},
 '/ai/daily': {'GET': ('ai.daily.view', 'staff.view'),
               'HEAD': ('ai.daily.view', 'staff.view'),
               'OPTIONS': ('ai.daily.view', 'staff.view')},
 '/archives/enemies': {'GET': ('archive.enemies.view', 'archive.view'),
                       'HEAD': ('archive.enemies.view', 'archive.view'),
                       'OPTIONS': ('archive.enemies.view', 'archive.view')},
 '/archives/events': {'GET': ('archive.events.view', 'archive.view'),
                      'HEAD': ('archive.events.view', 'archive.view'),
                      'OPTIONS': ('archive.events.view', 'archive.view')},
 '/archives/friends': {'GET': ('archive.friends.view', 'archive.view'),
                       'HEAD': ('archive.friends.view', 'archive.view'),
                       'OPTIONS': ('archive.friends.view', 'archive.view')},
 '/archives/groups': {'GET': ('archive.groups.view', 'archive.view'),
                      'HEAD': ('archive.groups.view', 'archive.view'),
                      'OPTIONS': ('archive.groups.view', 'archive.view')},
 '/archives/players': {'GET': ('archive.players.view', 'archive.view'),
                       'HEAD': ('archive.players.view', 'archive.view'),
                       'OPTIONS': ('archive.players.view', 'archive.view')},
 '/battles': {'GET': ('battle.view', ''), 'HEAD': ('battle.view', ''), 'OPTIONS': ('battle.view', '')},
 '/command': {'GET': ('command.view', 'staff.view'),
              'HEAD': ('command.view', 'staff.view'),
              'OPTIONS': ('command.view', 'staff.view')},
 '/compare': {'GET': ('compare.view', ''),
              'HEAD': ('compare.view', ''),
              'OPTIONS': ('compare.view', ''),
              'POST': ('compare.run', '')},
 '/identity': {'GET': ('identity.view', 'member.view'),
               'HEAD': ('identity.view', 'member.view'),
               'OPTIONS': ('identity.view', 'member.view')},
 '/identity/logs': {'GET': ('identity.logs.view', 'member.view'),
                    'HEAD': ('identity.logs.view', 'member.view'),
                    'OPTIONS': ('identity.logs.view', 'member.view')},
 '/leaders': {'GET': ('leaders.view', 'staff.view'),
              'HEAD': ('leaders.view', 'staff.view'),
              'OPTIONS': ('leaders.view', 'staff.view')},
 '/members': {'GET': ('members.view', 'member.view'),
              'HEAD': ('members.view', 'member.view'),
              'OPTIONS': ('members.view', 'member.view')},
 '/reputation': {'GET': ('reputation.home.view', 'reputation.view'),
                 'HEAD': ('reputation.home.view', 'reputation.view'),
                 'OPTIONS': ('reputation.home.view', 'reputation.view')},
 '/reputation/duplicates': {'GET': ('reputation.duplicates.view', 'reputation.view'),
                            'HEAD': ('reputation.duplicates.view', 'reputation.view'),
                            'OPTIONS': ('reputation.duplicates.view', 'reputation.view'),
                            'POST': ('reputation.manage', '')},
 '/reputation/events': {'GET': ('reputation.events.view', 'reputation.view'),
                        'HEAD': ('reputation.events.view', 'reputation.view'),
                        'OPTIONS': ('reputation.events.view', 'reputation.view'),
                        'POST': ('reputation.manage', '')},
 '/reputation/merge-logs': {'GET': ('reputation.merge_logs.view', 'reputation.view'),
                            'HEAD': ('reputation.merge_logs.view', 'reputation.view'),
                            'OPTIONS': ('reputation.merge_logs.view', 'reputation.view')},
 '/reputation/search': {'GET': ('reputation.search.view', 'reputation.view'),
                        'HEAD': ('reputation.search.view', 'reputation.view'),
                        'OPTIONS': ('reputation.search.view', 'reputation.view')},
 '/reputation/subjects': {'GET': ('reputation.subjects.view', 'reputation.view'),
                          'HEAD': ('reputation.subjects.view', 'reputation.view'),
                          'OPTIONS': ('reputation.subjects.view', 'reputation.view'),
                          'POST': ('reputation.manage', '')},
 '/risk': {'GET': ('risk.view', ''), 'HEAD': ('risk.view', ''), 'OPTIONS': ('risk.view', '')},
 '/rules': {'GET': ('rules.view', ''), 'HEAD': ('rules.view', ''), 'OPTIONS': ('rules.view', '')},
 '/snapshots': {'GET': ('import.use', ''),
                'HEAD': ('import.use', ''),
                'OPTIONS': ('import.use', ''),
                'POST': ('import.use', '')},
 '/staff': {'GET': ('staff.center.view', 'staff.view'),
            'HEAD': ('staff.center.view', 'staff.view'),
            'OPTIONS': ('staff.center.view', 'staff.view')},
 '/strategic': {'GET': ('strategic.view', 'staff.view'),
                'HEAD': ('strategic.view', 'staff.view'),
                'OPTIONS': ('strategic.view', 'staff.view')},
 '/talent': {'GET': ('talent.view', 'member.view'),
             'HEAD': ('talent.view', 'member.view'),
             'OPTIONS': ('talent.view', 'member.view')},
 '/tasks': {'GET': ('tasks.view', 'staff.view'),
            'HEAD': ('tasks.view', 'staff.view'),
            'OPTIONS': ('tasks.view', 'staff.view')},
 '/trends': {'GET': ('trend.view', ''), 'HEAD': ('trend.view', ''), 'OPTIONS': ('trend.view', '')}}


def normalize_protected_request_path(path: Any) -> str:
    """Normalize Flask request.path for the frozen V15.5 gate."""

    if not isinstance(path, str):
        return ""

    normalized = path.strip()

    if not normalized.startswith("/"):
        return normalized

    if normalized != "/":
        normalized = normalized.rstrip("/")

    return normalized or "/"


def evaluate_backend_permission(
    *,
    context: Any,
    path: Any,
    method: Any,
) -> dict[str, Any]:
    """Return a side-effect-free authorization decision.

    Only paths in PROTECTED_PATH_METHOD_PERMISSIONS are handled here.
    Protected paths fail closed on missing/invalid context, unsupported
    methods, or missing required permissions.
    """

    normalized_path = normalize_protected_request_path(path)

    route_contract = PROTECTED_PATH_METHOD_PERMISSIONS.get(
        normalized_path
    )

    if route_contract is None:
        return {
            "handled": False,
            "allowed": True,
            "normalized_path": normalized_path,
            "method": str(method or "").upper().strip(),
            "required_permission": "",
            "compatibility_parent": "",
            "reason": "path_not_protected",
        }

    normalized_method = str(
        method or ""
    ).upper().strip()

    if not isinstance(context, Mapping):
        return {
            "handled": True,
            "allowed": False,
            "normalized_path": normalized_path,
            "method": normalized_method,
            "required_permission": "",
            "compatibility_parent": "",
            "reason": "missing_or_invalid_access_context",
        }

    permissions = context.get(
        "permissions"
    )

    if not isinstance(
        permissions,
        (
            set,
            frozenset,
            list,
            tuple,
        ),
    ):
        return {
            "handled": True,
            "allowed": False,
            "normalized_path": normalized_path,
            "method": normalized_method,
            "required_permission": "",
            "compatibility_parent": "",
            "reason": "invalid_permissions_collection",
        }

    permission_contract = route_contract.get(
        normalized_method
    )

    if permission_contract is None:
        return {
            "handled": True,
            "allowed": False,
            "normalized_path": normalized_path,
            "method": normalized_method,
            "required_permission": "",
            "compatibility_parent": "",
            "reason": "unsupported_method",
        }

    required_permission, compatibility_parent = (
        permission_contract
    )

    primary_allowed = has_permission(
        context,
        required_permission,
    )

    parent_allowed = bool(
        compatibility_parent
    ) and has_permission(
        context,
        compatibility_parent,
    )

    allowed = bool(
        primary_allowed
        or parent_allowed
    )

    return {
        "handled": True,
        "allowed": allowed,
        "normalized_path": normalized_path,
        "method": normalized_method,
        "required_permission": required_permission,
        "compatibility_parent": compatibility_parent,
        "reason": (
            "permission_granted"
            if allowed
            else "permission_denied"
        ),
    }


# =====================================================================
# V15.5-A4-12-A3 SECOND-LAYER WORKSPACE BACKEND PERMISSION GATE
#
# Generated candidate only.
# Original first-layer evaluator above remains unchanged and is invoked
# first. Second layer is evaluated only when first layer says:
#     handled == False
# =====================================================================

import re as _v155_second_layer_re


_V155_FIRST_LAYER_EVALUATOR = evaluate_backend_permission


_V155_SECOND_LAYER_STATIC_PATH_METHOD_PERMISSIONS = {'/ai/decision': {'GET': ('staff.view', ''), 'HEAD': ('staff.view', ''), 'OPTIONS': ('staff.view', '')},
 '/ai/weekly': {'GET': ('staff.view', ''), 'HEAD': ('staff.view', ''), 'OPTIONS': ('staff.view', '')},
 '/archive_alliances': {'GET': ('archive.friends.view', 'archive.view'),
                        'HEAD': ('archive.friends.view', 'archive.view'),
                        'OPTIONS': ('archive.friends.view', 'archive.view')},
 '/archive_alliances/save': {'OPTIONS': ('archive.manage', ''), 'POST': ('archive.manage', '')},
 '/archive_enemies': {'GET': ('archive.enemies.view', 'archive.view'),
                      'HEAD': ('archive.enemies.view', 'archive.view'),
                      'OPTIONS': ('archive.enemies.view', 'archive.view')},
 '/archive_enemies/save': {'OPTIONS': ('archive.manage', ''), 'POST': ('archive.manage', '')},
 '/archive_events': {'GET': ('archive.events.view', 'archive.view'),
                     'HEAD': ('archive.events.view', 'archive.view'),
                     'OPTIONS': ('archive.events.view', 'archive.view')},
 '/archive_events/save': {'OPTIONS': ('archive.manage', ''), 'POST': ('archive.manage', '')},
 '/archive_friends': {'GET': ('archive.friends.view', 'archive.view'),
                      'HEAD': ('archive.friends.view', 'archive.view'),
                      'OPTIONS': ('archive.friends.view', 'archive.view')},
 '/archive_friends/save': {'OPTIONS': ('archive.manage', ''), 'POST': ('archive.manage', '')},
 '/archive_groups': {'GET': ('archive.groups.view', 'archive.view'),
                     'HEAD': ('archive.groups.view', 'archive.view'),
                     'OPTIONS': ('archive.groups.view', 'archive.view')},
 '/archive_players': {'GET': ('archive.players.view', 'archive.view'),
                      'HEAD': ('archive.players.view', 'archive.view'),
                      'OPTIONS': ('archive.players.view', 'archive.view')},
 '/archive_search': {'GET': ('archive.view', ''), 'HEAD': ('archive.view', ''), 'OPTIONS': ('archive.view', '')},
 '/archives': {'GET': ('archive.view', ''), 'HEAD': ('archive.view', ''), 'OPTIONS': ('archive.view', '')},
 '/archives/alliances': {'GET': ('archive.friends.view', 'archive.view'),
                         'HEAD': ('archive.friends.view', 'archive.view'),
                         'OPTIONS': ('archive.friends.view', 'archive.view')},
 '/archives/allies': {'GET': ('archive.friends.view', 'archive.view'),
                      'HEAD': ('archive.friends.view', 'archive.view'),
                      'OPTIONS': ('archive.friends.view', 'archive.view')},
 '/archives/allies/save': {'OPTIONS': ('archive.manage', ''), 'POST': ('archive.manage', '')},
 '/archives/enemies/save': {'OPTIONS': ('archive.manage', ''), 'POST': ('archive.manage', '')},
 '/archives/events/save': {'OPTIONS': ('archive.manage', ''), 'POST': ('archive.manage', '')},
 '/archives/friends/save': {'OPTIONS': ('archive.manage', ''), 'POST': ('archive.manage', '')},
 '/archives/search': {'GET': ('archive.view', ''), 'HEAD': ('archive.view', ''), 'OPTIONS': ('archive.view', '')},
 '/battle/create': {'OPTIONS': ('battle.manage', ''), 'POST': ('battle.manage', '')},
 '/command/action/log': {'OPTIONS': ('command.manage', ''), 'POST': ('command.manage', '')},
 '/compare/export.xlsx': {'OPTIONS': ('compare.run', ''), 'POST': ('compare.run', '')},
 '/export/compare_result': {'GET': ('compare.view', ''), 'HEAD': ('compare.view', ''), 'OPTIONS': ('compare.view', '')},
 '/export/group_summary': {'GET': ('compare.view', ''), 'HEAD': ('compare.view', ''), 'OPTIONS': ('compare.view', '')},
 '/export_members': {'GET': ('members.view', 'member.view'),
                     'HEAD': ('members.view', 'member.view'),
                     'OPTIONS': ('members.view', 'member.view')},
 '/identity/view': {'GET': ('identity.view', 'member.view'),
                    'HEAD': ('identity.view', 'member.view'),
                    'OPTIONS': ('identity.view', 'member.view')},
 '/leaders/mapping/delete': {'OPTIONS': ('leaders.manage', ''), 'POST': ('leaders.manage', '')},
 '/leaders/mapping/save': {'OPTIONS': ('leaders.manage', ''), 'POST': ('leaders.manage', '')},
 '/reputation/events/new': {'GET': ('reputation.events.view', 'reputation.view'),
                            'HEAD': ('reputation.events.view', 'reputation.view'),
                            'OPTIONS': ('reputation.events.view', 'reputation.view')},
 '/reputation/quick-link': {'OPTIONS': ('reputation.manage', ''), 'POST': ('reputation.manage', '')},
 '/reputation/subjects/new': {'GET': ('reputation.subjects.view', 'reputation.view'),
                              'HEAD': ('reputation.subjects.view', 'reputation.view'),
                              'OPTIONS': ('reputation.subjects.view', 'reputation.view'),
                              'POST': ('reputation.manage', '')},
 '/reputation/tasks': {'GET': ('reputation.view', ''),
                       'HEAD': ('reputation.view', ''),
                       'OPTIONS': ('reputation.view', '')},
 '/reputation/tasks/create': {'OPTIONS': ('reputation.manage', ''), 'POST': ('reputation.manage', '')},
 '/reputation/workbench': {'GET': ('reputation.view', ''),
                           'HEAD': ('reputation.view', ''),
                           'OPTIONS': ('reputation.view', '')},
 '/strategic/feedback': {'OPTIONS': ('strategic.manage', ''), 'POST': ('strategic.manage', '')}}


_V155_SECOND_LAYER_DYNAMIC_SOURCE = [('/reputation/events/<int:event_id>/relations/<int:relation_id>/delete',
  '^/reputation/events/[0-9]+/relations/[0-9]+/delete$',
  {'POST': ('reputation.manage', ''), 'OPTIONS': ('reputation.manage', '')}),
 ('/archives/events/<int:event_id>/relations/<int:relation_id>/delete',
  '^/archives/events/[0-9]+/relations/[0-9]+/delete$',
  {'POST': ('archive.manage', ''), 'OPTIONS': ('archive.manage', '')}),
 ('/reputation/events/<int:event_id>/relations/save',
  '^/reputation/events/[0-9]+/relations/save$',
  {'POST': ('reputation.manage', ''), 'OPTIONS': ('reputation.manage', '')}),
 ('/archive_events/<int:event_id>/relations/<int:relation_id>/delete',
  '^/archive_events/[0-9]+/relations/[0-9]+/delete$',
  {'POST': ('archive.manage', ''), 'OPTIONS': ('archive.manage', '')}),
 ('/archives/events/<int:event_id>/relations/save',
  '^/archives/events/[0-9]+/relations/save$',
  {'POST': ('archive.manage', ''), 'OPTIONS': ('archive.manage', '')}),
 ('/archive_events/<int:event_id>/relations/save',
  '^/archive_events/[0-9]+/relations/save$',
  {'POST': ('archive.manage', ''), 'OPTIONS': ('archive.manage', '')}),
 ('/reputation/subjects/<int:subject_id>/delete',
  '^/reputation/subjects/[0-9]+/delete$',
  {'POST': ('reputation.manage', ''), 'OPTIONS': ('reputation.manage', '')}),
 ('/archive_alliances/<int:alliance_id>/update',
  '^/archive_alliances/[0-9]+/update$',
  {'POST': ('archive.manage', ''), 'OPTIONS': ('archive.manage', '')}),
 ('/reputation/events/<int:event_id>/delete',
  '^/reputation/events/[0-9]+/delete$',
  {'POST': ('reputation.manage', ''), 'OPTIONS': ('reputation.manage', '')}),
 ('/reputation/events/<int:event_id>/status',
  '^/reputation/events/[0-9]+/status$',
  {'POST': ('reputation.manage', ''), 'OPTIONS': ('reputation.manage', '')}),
 ('/reputation/subjects/<int:subject_id>/edit',
  '^/reputation/subjects/[0-9]+/edit$',
  {'GET': ('reputation.subjects.view', 'reputation.view'),
   'HEAD': ('reputation.subjects.view', 'reputation.view'),
   'OPTIONS': ('reputation.subjects.view', 'reputation.view'),
   'POST': ('reputation.manage', '')}),
 ('/archives/enemies/<int:enemy_id>/update',
  '^/archives/enemies/[0-9]+/update$',
  {'POST': ('archive.manage', ''), 'OPTIONS': ('archive.manage', '')}),
 ('/archives/friends/<int:alliance_id>/update',
  '^/archives/friends/[0-9]+/update$',
  {'POST': ('archive.manage', ''), 'OPTIONS': ('archive.manage', '')}),
 ('/reputation/tasks/<int:task_id>/update',
  '^/reputation/tasks/[0-9]+/update$',
  {'POST': ('reputation.manage', ''), 'OPTIONS': ('reputation.manage', '')}),
 ('/archive_enemies/<int:enemy_id>/update',
  '^/archive_enemies/[0-9]+/update$',
  {'POST': ('archive.manage', ''), 'OPTIONS': ('archive.manage', '')}),
 ('/archive_friends/<int:alliance_id>/update',
  '^/archive_friends/[0-9]+/update$',
  {'POST': ('archive.manage', ''), 'OPTIONS': ('archive.manage', '')}),
 ('/archives/events/<int:event_id>/update',
  '^/archives/events/[0-9]+/update$',
  {'POST': ('archive.manage', ''), 'OPTIONS': ('archive.manage', '')}),
 ('/reputation/events/<int:event_id>/edit',
  '^/reputation/events/[0-9]+/edit$',
  {'GET': ('reputation.events.view', 'reputation.view'),
   'HEAD': ('reputation.events.view', 'reputation.view'),
   'OPTIONS': ('reputation.events.view', 'reputation.view'),
   'POST': ('reputation.manage', '')}),
 ('/reputation/subjects/<int:subject_id>',
  '^/reputation/subjects/[0-9]+$',
  {'GET': ('reputation.subjects.view', 'reputation.view'),
   'HEAD': ('reputation.subjects.view', 'reputation.view'),
   'OPTIONS': ('reputation.subjects.view', 'reputation.view')}),
 ('/archive_alliances/<int:alliance_id>',
  '^/archive_alliances/[0-9]+$',
  {'GET': ('archive.friends.view', 'archive.view'),
   'HEAD': ('archive.friends.view', 'archive.view'),
   'OPTIONS': ('archive.friends.view', 'archive.view')}),
 ('/reputation/events/<int:event_id>',
  '^/reputation/events/[0-9]+$',
  {'GET': ('reputation.events.view', 'reputation.view'),
   'HEAD': ('reputation.events.view', 'reputation.view'),
   'OPTIONS': ('reputation.events.view', 'reputation.view')}),
 ('/archives/enemies/<int:enemy_id>',
  '^/archives/enemies/[0-9]+$',
  {'GET': ('archive.enemies.view', 'archive.view'),
   'HEAD': ('archive.enemies.view', 'archive.view'),
   'OPTIONS': ('archive.enemies.view', 'archive.view')}),
 ('/archives/friends/<int:alliance_id>',
  '^/archives/friends/[0-9]+$',
  {'GET': ('archive.friends.view', 'archive.view'),
   'HEAD': ('archive.friends.view', 'archive.view'),
   'OPTIONS': ('archive.friends.view', 'archive.view')}),
 ('/archive_enemies/<int:enemy_id>',
  '^/archive_enemies/[0-9]+$',
  {'GET': ('archive.enemies.view', 'archive.view'),
   'HEAD': ('archive.enemies.view', 'archive.view'),
   'OPTIONS': ('archive.enemies.view', 'archive.view')}),
 ('/archive_friends/<int:alliance_id>',
  '^/archive_friends/[0-9]+$',
  {'GET': ('archive.friends.view', 'archive.view'),
   'HEAD': ('archive.friends.view', 'archive.view'),
   'OPTIONS': ('archive.friends.view', 'archive.view')}),
 ('/archives/events/<int:event_id>',
  '^/archives/events/[0-9]+$',
  {'GET': ('archive.events.view', 'archive.view'),
   'HEAD': ('archive.events.view', 'archive.view'),
   'OPTIONS': ('archive.events.view', 'archive.view')}),
 ('/archive_events/<int:event_id>',
  '^/archive_events/[0-9]+$',
  {'GET': ('archive.events.view', 'archive.view'),
   'HEAD': ('archive.events.view', 'archive.view'),
   'OPTIONS': ('archive.events.view', 'archive.view')}),
 ('/archives/group/<group_name>',
  '^/archives/group/[^/]+$',
  {'GET': ('archive.groups.view', 'archive.view'),
   'HEAD': ('archive.groups.view', 'archive.view'),
   'OPTIONS': ('archive.groups.view', 'archive.view')}),
 ('/command/action/<path:action_key>',
  '^/command/action/.+$',
  {'GET': ('command.view', 'staff.view'), 'HEAD': ('command.view', 'staff.view'), 'OPTIONS': ('command.view', 'staff.view')}),
 ('/battle/delete/<int:battle_id>', '^/battle/delete/[0-9]+$', {'POST': ('battle.manage', ''), 'OPTIONS': ('battle.manage', '')}),
 ('/battle/select/<int:battle_id>', '^/battle/select/[0-9]+$', {'POST': ('battle.manage', ''), 'OPTIONS': ('battle.manage', '')}),
 ('/identity/edit/<member_name>',
  '^/identity/edit/[^/]+$',
  {'GET': ('identity.view', 'member.view'),
   'HEAD': ('identity.view', 'member.view'),
   'OPTIONS': ('identity.view', 'member.view'),
   'POST': ('identity.manage', '')}),
 ('/identity/view/<member_name>',
  '^/identity/view/[^/]+$',
  {'GET': ('identity.view', 'member.view'), 'HEAD': ('identity.view', 'member.view'), 'OPTIONS': ('identity.view', 'member.view')}),
 ('/leaders/group/<path:group_name>',
  '^/leaders/group/.+$',
  {'GET': ('leaders.view', 'staff.view'), 'HEAD': ('leaders.view', 'staff.view'), 'OPTIONS': ('leaders.view', 'staff.view')}),
 ('/leaders/owner/<path:owner_name>',
  '^/leaders/owner/.+$',
  {'GET': ('leaders.view', 'staff.view'), 'HEAD': ('leaders.view', 'staff.view'), 'OPTIONS': ('leaders.view', 'staff.view')}),
 ('/snapshot/view/<int:snapshot_id>',
  '^/snapshot/view/[0-9]+$',
  {'GET': ('import.use', ''), 'HEAD': ('import.use', ''), 'OPTIONS': ('import.use', '')}),
 ('/identity/log/<int:log_id>',
  '^/identity/log/[0-9]+$',
  {'GET': ('identity.logs.view', 'member.view'),
   'HEAD': ('identity.logs.view', 'member.view'),
   'OPTIONS': ('identity.logs.view', 'member.view')}),
 ('/tasks/detail/<path:task_key>',
  '^/tasks/detail/.+$',
  {'GET': ('tasks.view', 'staff.view'), 'HEAD': ('tasks.view', 'staff.view'), 'OPTIONS': ('tasks.view', 'staff.view')})]


_V155_SECOND_LAYER_DYNAMIC_PATH_METHOD_PERMISSIONS = tuple(
    (
        _v155_second_layer_re.compile(regex_text),
        route_rule,
        method_contract,
    )
    for route_rule, regex_text, method_contract
    in _V155_SECOND_LAYER_DYNAMIC_SOURCE
)


def _v155_resolve_second_layer_contract(normalized_path):
    static_contract = (
        _V155_SECOND_LAYER_STATIC_PATH_METHOD_PERMISSIONS.get(
            normalized_path
        )
    )

    if static_contract is not None:
        return (
            normalized_path,
            static_contract,
        )

    for (
        pattern,
        route_rule,
        method_contract,
    ) in _V155_SECOND_LAYER_DYNAMIC_PATH_METHOD_PERMISSIONS:

        if pattern.fullmatch(
            normalized_path
        ):
            return (
                route_rule,
                method_contract,
            )

    return (
        "",
        None,
    )


def evaluate_backend_permission(
    *,
    context,
    path,
    method,
):
    first_layer_decision = (
        _V155_FIRST_LAYER_EVALUATOR(
            context=context,
            path=path,
            method=method,
        )
    )

    if first_layer_decision.get(
        "handled"
    ):
        return first_layer_decision

    normalized_path = (
        normalize_protected_request_path(
            path
        )
    )

    (
        _matched_route_rule,
        route_contract,
    ) = _v155_resolve_second_layer_contract(
        normalized_path
    )

    if route_contract is None:
        return first_layer_decision

    normalized_method = str(
        method or ""
    ).upper().strip()

    if not isinstance(
        context,
        Mapping,
    ):
        return {
            "handled": True,
            "allowed": False,
            "normalized_path": normalized_path,
            "method": normalized_method,
            "required_permission": "",
            "compatibility_parent": "",
            "reason": "missing_or_invalid_access_context",
        }

    permissions = context.get(
        "permissions"
    )

    if not isinstance(
        permissions,
        (
            set,
            frozenset,
            list,
            tuple,
        ),
    ):
        return {
            "handled": True,
            "allowed": False,
            "normalized_path": normalized_path,
            "method": normalized_method,
            "required_permission": "",
            "compatibility_parent": "",
            "reason": "invalid_permissions_collection",
        }

    permission_contract = (
        route_contract.get(
            normalized_method
        )
    )

    if permission_contract is None:
        return {
            "handled": True,
            "allowed": False,
            "normalized_path": normalized_path,
            "method": normalized_method,
            "required_permission": "",
            "compatibility_parent": "",
            "reason": "unsupported_method",
        }

    (
        required_permission,
        compatibility_parent,
    ) = permission_contract

    primary_allowed = has_permission(
        context,
        required_permission,
    )

    parent_allowed = (
        bool(
            compatibility_parent
        )
        and has_permission(
            context,
            compatibility_parent,
        )
    )

    allowed = bool(
        primary_allowed
        or parent_allowed
    )

    return {
        "handled": True,
        "allowed": allowed,
        "normalized_path": normalized_path,
        "method": normalized_method,
        "required_permission": required_permission,
        "compatibility_parent": compatibility_parent,
        "reason": (
            "permission_granted"
            if allowed
            else "permission_denied"
        ),
    }
