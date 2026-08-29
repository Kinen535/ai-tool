from __future__ import annotations

import importlib
import sqlite3
import sys
from pathlib import Path

import pytest

from services.v158_auth_service import issue_csrf_token
from services.v155_membership_permission_override_service import (
    get_membership_permission_admin_state,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_DB = PROJECT_ROOT / "data/snapshots.db"

SCHEMA_SQL = r"""
CREATE TABLE v158_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    username TEXT NOT NULL COLLATE NOCASE
        CHECK (username = trim(username))
        CHECK (length(username) BETWEEN 3 AND 64)
        CHECK (substr(username, 1, 1) GLOB '[A-Za-z0-9]')
        CHECK (username NOT GLOB '*[^A-Za-z0-9._-]*'),

    password_hash TEXT NOT NULL
        CHECK (length(password_hash) >= 60),

    display_name TEXT NOT NULL DEFAULT ''
        CHECK (length(display_name) <= 100),

    role TEXT NOT NULL
        CHECK (role IN ('super_admin', 'manager', 'viewer')),

    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'disabled')),

    failed_login_count INTEGER NOT NULL DEFAULT 0
        CHECK (failed_login_count >= 0),

    locked_until TEXT,
    last_failed_login_at TEXT,
    last_login_at TEXT,

    last_login_ip TEXT NOT NULL DEFAULT ''
        CHECK (length(last_login_ip) <= 64),

    password_changed_at TEXT NOT NULL
        DEFAULT (datetime('now', 'localtime')),

    must_change_password INTEGER NOT NULL DEFAULT 0
        CHECK (must_change_password IN (0, 1)),

    session_version INTEGER NOT NULL DEFAULT 1
        CHECK (session_version >= 1),

    created_at TEXT NOT NULL
        DEFAULT (datetime('now', 'localtime')),

    updated_at TEXT NOT NULL
        DEFAULT (datetime('now', 'localtime'))
);
CREATE TABLE v155_workspaces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    workspace_key TEXT NOT NULL
        CHECK (
            workspace_key = trim(workspace_key)
            AND length(workspace_key) BETWEEN 3 AND 64
        ),

    workspace_name TEXT NOT NULL
        CHECK (
            workspace_name = trim(workspace_name)
            AND length(workspace_name) BETWEEN 1 AND 100
        ),

    owner_user_id INTEGER NOT NULL,

    status TEXT NOT NULL
        DEFAULT 'active'
        CHECK (
            status IN (
                'active',
                'disabled',
                'archived'
            )
        ),

    created_at TEXT NOT NULL
        DEFAULT (
            datetime('now', 'localtime')
        ),

    updated_at TEXT NOT NULL
        DEFAULT (
            datetime('now', 'localtime')
        ),

    FOREIGN KEY (
        owner_user_id
    )
    REFERENCES v158_users(id)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT
);
CREATE TABLE v155_roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    workspace_id INTEGER NOT NULL,

    role_key TEXT NOT NULL
        CHECK (
            role_key = trim(role_key)
            AND length(role_key) BETWEEN 2 AND 64
        ),

    role_name TEXT NOT NULL
        CHECK (
            role_name = trim(role_name)
            AND length(role_name) BETWEEN 1 AND 100
        ),

    description TEXT NOT NULL
        DEFAULT '',

    is_system INTEGER NOT NULL
        DEFAULT 0
        CHECK (
            is_system IN (0, 1)
        ),

    status TEXT NOT NULL
        DEFAULT 'active'
        CHECK (
            status IN (
                'active',
                'disabled'
            )
        ),

    created_at TEXT NOT NULL
        DEFAULT (
            datetime('now', 'localtime')
        ),

    updated_at TEXT NOT NULL
        DEFAULT (
            datetime('now', 'localtime')
        ),

    FOREIGN KEY (
        workspace_id
    )
    REFERENCES v155_workspaces(id)
        ON UPDATE RESTRICT
        ON DELETE CASCADE,

    UNIQUE (
        id,
        workspace_id
    )
);
CREATE TABLE v155_permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    permission_key TEXT NOT NULL
        CHECK (
            permission_key = trim(permission_key)
            AND length(permission_key) BETWEEN 3 AND 100
        ),

    permission_name TEXT NOT NULL
        DEFAULT '',

    module_key TEXT NOT NULL
        DEFAULT '',

    description TEXT NOT NULL
        DEFAULT '',

    is_system INTEGER NOT NULL
        DEFAULT 1
        CHECK (
            is_system IN (0, 1)
        ),

    created_at TEXT NOT NULL
        DEFAULT (
            datetime('now', 'localtime')
        )
);
CREATE TABLE v155_role_permissions (
    role_id INTEGER NOT NULL,

    permission_id INTEGER NOT NULL,

    created_at TEXT NOT NULL
        DEFAULT (
            datetime('now', 'localtime')
        ),

    PRIMARY KEY (
        role_id,
        permission_id
    ),

    FOREIGN KEY (
        role_id
    )
    REFERENCES v155_roles(id)
        ON UPDATE RESTRICT
        ON DELETE CASCADE,

    FOREIGN KEY (
        permission_id
    )
    REFERENCES v155_permissions(id)
        ON UPDATE RESTRICT
        ON DELETE CASCADE
);
CREATE TABLE v155_workspace_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    workspace_id INTEGER NOT NULL,

    user_id INTEGER NOT NULL,

    role_id INTEGER NOT NULL,

    status TEXT NOT NULL
        DEFAULT 'active'
        CHECK (
            status IN (
                'active',
                'disabled'
            )
        ),

    is_default INTEGER NOT NULL
        DEFAULT 0
        CHECK (
            is_default IN (0, 1)
        ),

    created_at TEXT NOT NULL
        DEFAULT (
            datetime('now', 'localtime')
        ),

    updated_at TEXT NOT NULL
        DEFAULT (
            datetime('now', 'localtime')
        ),

    FOREIGN KEY (
        workspace_id
    )
    REFERENCES v155_workspaces(id)
        ON UPDATE RESTRICT
        ON DELETE CASCADE,

    FOREIGN KEY (
        user_id
    )
    REFERENCES v158_users(id)
        ON UPDATE RESTRICT
        ON DELETE CASCADE,

    FOREIGN KEY (
        role_id,
        workspace_id
    )
    REFERENCES v155_roles(
        id,
        workspace_id
    )
        ON UPDATE RESTRICT
        ON DELETE RESTRICT
);
CREATE TABLE v155_workspace_battles (
    workspace_id INTEGER NOT NULL,

    battle_id INTEGER NOT NULL,

    is_current INTEGER NOT NULL
        DEFAULT 0
        CHECK (
            is_current IN (0, 1)
        ),

    status TEXT NOT NULL
        DEFAULT 'active'
        CHECK (
            status IN (
                'active',
                'archived'
            )
        ),

    created_at TEXT NOT NULL
        DEFAULT (
            datetime('now', 'localtime')
        ),

    PRIMARY KEY (
        workspace_id,
        battle_id
    ),

    FOREIGN KEY (
        workspace_id
    )
    REFERENCES v155_workspaces(id)
        ON UPDATE RESTRICT
        ON DELETE CASCADE,

    FOREIGN KEY (
        battle_id
    )
    REFERENCES battles(id)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT
);
CREATE TABLE v155_membership_permission_overrides (
    membership_id INTEGER NOT NULL,

    permission_id INTEGER NOT NULL,

    effect TEXT NOT NULL
        CHECK (
            effect IN (
                'grant',
                'deny'
            )
        ),

    created_at TEXT NOT NULL
        DEFAULT (
            datetime('now', 'localtime')
        ),

    updated_at TEXT NOT NULL
        DEFAULT (
            datetime('now', 'localtime')
        ),

    PRIMARY KEY (
        membership_id,
        permission_id
    ),

    FOREIGN KEY (
        membership_id
    )
    REFERENCES v155_workspace_members(id)
        ON UPDATE RESTRICT
        ON DELETE CASCADE,

    FOREIGN KEY (
        permission_id
    )
    REFERENCES v155_permissions(id)
        ON UPDATE RESTRICT
        ON DELETE CASCADE
);
CREATE TABLE v158_action_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    user_id INTEGER
        CHECK (
            user_id IS NULL OR user_id > 0
        ),

    username_snapshot TEXT NOT NULL DEFAULT ''
        CHECK (
            length(username_snapshot) <= 64
        ),

    role_snapshot TEXT NOT NULL DEFAULT ''
        CHECK (
            role_snapshot IN (
                '',
                'super_admin',
                'manager',
                'viewer',
                'system'
            )
        ),

    battle_id INTEGER
        CHECK (
            battle_id IS NULL OR battle_id > 0
        ),

    request_id TEXT NOT NULL DEFAULT ''
        CHECK (
            length(request_id) <= 64
        ),

    action_key TEXT NOT NULL
        CHECK (
            length(action_key) BETWEEN 2 AND 100
        ),

    action_label TEXT NOT NULL DEFAULT ''
        CHECK (
            length(action_label) <= 200
        ),

    target_type TEXT NOT NULL DEFAULT ''
        CHECK (
            length(target_type) <= 100
        ),

    target_id TEXT NOT NULL DEFAULT ''
        CHECK (
            length(target_id) <= 100
        ),

    target_label TEXT NOT NULL DEFAULT ''
        CHECK (
            length(target_label) <= 300
        ),

    result_status TEXT NOT NULL
        CHECK (
            result_status IN (
                'success',
                'failure',
                'blocked'
            )
        ),

    before_data TEXT NOT NULL DEFAULT ''
        CHECK (
            before_data = ''
            OR json_valid(before_data)
        ),

    after_data TEXT NOT NULL DEFAULT ''
        CHECK (
            after_data = ''
            OR json_valid(after_data)
        ),

    reason TEXT NOT NULL DEFAULT ''
        CHECK (
            length(reason) <= 2000
        ),

    request_method TEXT NOT NULL DEFAULT ''
        CHECK (
            request_method IN (
                '',
                'GET',
                'POST',
                'PUT',
                'PATCH',
                'DELETE',
                'CLI',
                'SYSTEM'
            )
        ),

    request_path TEXT NOT NULL DEFAULT ''
        CHECK (
            length(request_path) <= 500
        ),

    ip_address TEXT NOT NULL DEFAULT ''
        CHECK (
            length(ip_address) <= 64
        ),

    user_agent TEXT NOT NULL DEFAULT ''
        CHECK (
            length(user_agent) <= 1000
        ),

    created_at TEXT NOT NULL
        DEFAULT (datetime('now', 'localtime'))
);
"""

SEED = {'v158_users': [{'id': 1,
                 'username': 'kinen',
                 'password_hash': 'TEST_ONLY_DISABLED_PASSWORD_HASH_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX',
                 'display_name': '系统管理员',
                 'role': 'super_admin',
                 'status': 'active',
                 'failed_login_count': 0,
                 'locked_until': None,
                 'last_failed_login_at': '2026-08-17 14:47:28',
                 'last_login_at': '2026-08-28 13:56:54',
                 'last_login_ip': '',
                 'password_changed_at': '2026-07-16 01:50:46',
                 'must_change_password': 0,
                 'session_version': 1,
                 'created_at': '2026-07-16 01:50:46',
                 'updated_at': '2026-08-28 13:56:54'},
                {'id': 2,
                 'username': 'MiniQ',
                 'password_hash': 'TEST_ONLY_DISABLED_PASSWORD_HASH_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX',
                 'display_name': '折柳',
                 'role': 'viewer',
                 'status': 'active',
                 'failed_login_count': 0,
                 'locked_until': None,
                 'last_failed_login_at': None,
                 'last_login_at': '2026-08-19 23:08:58',
                 'last_login_ip': '',
                 'password_changed_at': '2026-08-08 17:07:33',
                 'must_change_password': 0,
                 'session_version': 1,
                 'created_at': '2026-08-08 17:07:33',
                 'updated_at': '2026-08-19 23:08:58'}],
 'v155_workspaces': [{'id': 1,
                      'workspace_key': 'legacy-main',
                      'workspace_name': '主工作区',
                      'owner_user_id': 1,
                      'status': 'active',
                      'created_at': '2026-08-10 01:46:53',
                      'updated_at': '2026-08-10 01:46:53'}],
 'v155_roles': [{'id': 1,
                 'workspace_id': 1,
                 'role_key': 'workspace_admin',
                 'role_name': '工作区管理员',
                 'description': '',
                 'is_system': 1,
                 'status': 'active',
                 'created_at': '2026-08-10 01:46:53',
                 'updated_at': '2026-08-10 01:46:53'},
                {'id': 2,
                 'workspace_id': 1,
                 'role_key': 'manager',
                 'role_name': '管理员',
                 'description': '',
                 'is_system': 1,
                 'status': 'active',
                 'created_at': '2026-08-10 01:46:53',
                 'updated_at': '2026-08-10 01:46:53'},
                {'id': 3,
                 'workspace_id': 1,
                 'role_key': 'viewer',
                 'role_name': '只读用户',
                 'description': '',
                 'is_system': 1,
                 'status': 'active',
                 'created_at': '2026-08-10 01:46:53',
                 'updated_at': '2026-08-10 01:46:53'}],
 'v155_permissions': [{'id': 1,
                       'permission_key': 'dashboard.view',
                       'permission_name': '查看总览',
                       'module_key': 'dashboard',
                       'description': '',
                       'is_system': 1,
                       'created_at': '2026-08-10 01:46:53'},
                      {'id': 2,
                       'permission_key': 'import.use',
                       'permission_name': '导入数据',
                       'module_key': 'import',
                       'description': '',
                       'is_system': 1,
                       'created_at': '2026-08-10 01:46:53'},
                      {'id': 3,
                       'permission_key': 'compare.view',
                       'permission_name': '查看数据对比',
                       'module_key': 'compare',
                       'description': '',
                       'is_system': 1,
                       'created_at': '2026-08-10 01:46:53'},
                      {'id': 4,
                       'permission_key': 'compare.run',
                       'permission_name': '执行数据对比',
                       'module_key': 'compare',
                       'description': '',
                       'is_system': 1,
                       'created_at': '2026-08-10 01:46:53'},
                      {'id': 5,
                       'permission_key': 'trend.view',
                       'permission_name': '查看趋势分析',
                       'module_key': 'trend',
                       'description': '',
                       'is_system': 1,
                       'created_at': '2026-08-10 01:46:53'},
                      {'id': 6,
                       'permission_key': 'risk.view',
                       'permission_name': '查看风险中心',
                       'module_key': 'risk',
                       'description': '',
                       'is_system': 1,
                       'created_at': '2026-08-10 01:46:53'},
                      {'id': 7,
                       'permission_key': 'member.view',
                       'permission_name': '查看成员',
                       'module_key': 'member',
                       'description': '',
                       'is_system': 1,
                       'created_at': '2026-08-10 01:46:53'},
                      {'id': 8,
                       'permission_key': 'member.manage',
                       'permission_name': '管理成员',
                       'module_key': 'member',
                       'description': '',
                       'is_system': 1,
                       'created_at': '2026-08-10 01:46:53'},
                      {'id': 9,
                       'permission_key': 'battle.view',
                       'permission_name': '查看战场',
                       'module_key': 'battle',
                       'description': '',
                       'is_system': 1,
                       'created_at': '2026-08-10 01:46:53'},
                      {'id': 10,
                       'permission_key': 'battle.manage',
                       'permission_name': '管理战场',
                       'module_key': 'battle',
                       'description': '',
                       'is_system': 1,
                       'created_at': '2026-08-10 01:46:53'},
                      {'id': 11,
                       'permission_key': 'battle.delete',
                       'permission_name': '删除战场数据',
                       'module_key': 'battle',
                       'description': '',
                       'is_system': 1,
                       'created_at': '2026-08-10 01:46:53'},
                      {'id': 12,
                       'permission_key': 'staff.view',
                       'permission_name': '查看幕僚中心',
                       'module_key': 'staff',
                       'description': '',
                       'is_system': 1,
                       'created_at': '2026-08-10 01:46:53'},
                      {'id': 13,
                       'permission_key': 'staff.manage',
                       'permission_name': '管理幕僚任务',
                       'module_key': 'staff',
                       'description': '',
                       'is_system': 1,
                       'created_at': '2026-08-10 01:46:53'},
                      {'id': 14,
                       'permission_key': 'archive.view',
                       'permission_name': '查看档案',
                       'module_key': 'archive',
                       'description': '',
                       'is_system': 1,
                       'created_at': '2026-08-10 01:46:53'},
                      {'id': 15,
                       'permission_key': 'archive.manage',
                       'permission_name': '管理档案',
                       'module_key': 'archive',
                       'description': '',
                       'is_system': 1,
                       'created_at': '2026-08-10 01:46:53'},
                      {'id': 16,
                       'permission_key': 'reputation.view',
                       'permission_name': '查看信誉中心',
                       'module_key': 'reputation',
                       'description': '',
                       'is_system': 1,
                       'created_at': '2026-08-10 01:46:53'},
                      {'id': 17,
                       'permission_key': 'reputation.manage',
                       'permission_name': '管理信誉中心',
                       'module_key': 'reputation',
                       'description': '',
                       'is_system': 1,
                       'created_at': '2026-08-10 01:46:53'},
                      {'id': 18,
                       'permission_key': 'report.export',
                       'permission_name': '导出报表',
                       'module_key': 'report',
                       'description': '',
                       'is_system': 1,
                       'created_at': '2026-08-10 01:46:53'},
                      {'id': 19,
                       'permission_key': 'rules.view',
                       'permission_name': '查看规则说明',
                       'module_key': 'rules',
                       'description': '',
                       'is_system': 1,
                       'created_at': '2026-08-10 01:46:53'},
                      {'id': 20,
                       'permission_key': 'account.manage',
                       'permission_name': '管理账号',
                       'module_key': 'account',
                       'description': '',
                       'is_system': 1,
                       'created_at': '2026-08-10 01:46:53'},
                      {'id': 21,
                       'permission_key': 'security.manage',
                       'permission_name': '管理安全中心',
                       'module_key': 'security',
                       'description': '',
                       'is_system': 1,
                       'created_at': '2026-08-10 01:46:53'},
                      {'id': 22,
                       'permission_key': 'identity.view',
                       'permission_name': '查看身份中心',
                       'module_key': 'member',
                       'description': '页面级权限：身份中心；路径：/identity；兼容父权限：member.view',
                       'is_system': 1,
                       'created_at': '2026-08-10 19:31:12'},
                      {'id': 23,
                       'permission_key': 'talent.view',
                       'permission_name': '查看人才中心',
                       'module_key': 'member',
                       'description': '页面级权限：人才中心；路径：/talent；兼容父权限：member.view',
                       'is_system': 1,
                       'created_at': '2026-08-10 19:31:12'},
                      {'id': 24,
                       'permission_key': 'members.view',
                       'permission_name': '查看成员',
                       'module_key': 'member',
                       'description': '页面级权限：成员；路径：/members；兼容父权限：member.view',
                       'is_system': 1,
                       'created_at': '2026-08-10 19:31:12'},
                      {'id': 25,
                       'permission_key': 'identity.logs.view',
                       'permission_name': '查看身份日志',
                       'module_key': 'member',
                       'description': '页面级权限：身份日志；路径：/identity/logs；兼容父权限：member.view',
                       'is_system': 1,
                       'created_at': '2026-08-10 19:31:12'},
                      {'id': 26,
                       'permission_key': 'archive.players.view',
                       'permission_name': '查看人物档案',
                       'module_key': 'archive',
                       'description': '页面级权限：人物档案；路径：/archives/players；兼容父权限：archive.view',
                       'is_system': 1,
                       'created_at': '2026-08-10 19:31:12'},
                      {'id': 27,
                       'permission_key': 'archive.groups.view',
                       'permission_name': '查看分组档案',
                       'module_key': 'archive',
                       'description': '页面级权限：分组档案；路径：/archives/groups；兼容父权限：archive.view',
                       'is_system': 1,
                       'created_at': '2026-08-10 19:31:12'},
                      {'id': 28,
                       'permission_key': 'archive.friends.view',
                       'permission_name': '查看友盟档案',
                       'module_key': 'archive',
                       'description': '页面级权限：友盟档案；路径：/archives/friends；兼容父权限：archive.view',
                       'is_system': 1,
                       'created_at': '2026-08-10 19:31:12'},
                      {'id': 29,
                       'permission_key': 'archive.enemies.view',
                       'permission_name': '查看敌军档案',
                       'module_key': 'archive',
                       'description': '页面级权限：敌军档案；路径：/archives/enemies；兼容父权限：archive.view',
                       'is_system': 1,
                       'created_at': '2026-08-10 19:31:12'},
                      {'id': 30,
                       'permission_key': 'archive.events.view',
                       'permission_name': '查看战场事件',
                       'module_key': 'archive',
                       'description': '页面级权限：战场事件；路径：/archives/events；兼容父权限：archive.view',
                       'is_system': 1,
                       'created_at': '2026-08-10 19:31:12'},
                      {'id': 31,
                       'permission_key': 'reputation.home.view',
                       'permission_name': '查看信誉首页',
                       'module_key': 'reputation',
                       'description': '页面级权限：信誉首页；路径：/reputation；兼容父权限：reputation.view',
                       'is_system': 1,
                       'created_at': '2026-08-10 19:31:12'},
                      {'id': 32,
                       'permission_key': 'reputation.search.view',
                       'permission_name': '查看信誉检索',
                       'module_key': 'reputation',
                       'description': '页面级权限：信誉检索；路径：/reputation/search；兼容父权限：reputation.view',
                       'is_system': 1,
                       'created_at': '2026-08-10 19:31:12'},
                      {'id': 33,
                       'permission_key': 'reputation.subjects.view',
                       'permission_name': '查看信誉主体',
                       'module_key': 'reputation',
                       'description': '页面级权限：信誉主体；路径：/reputation/subjects；兼容父权限：reputation.view',
                       'is_system': 1,
                       'created_at': '2026-08-10 19:31:12'},
                      {'id': 34,
                       'permission_key': 'reputation.events.view',
                       'permission_name': '查看信誉事件',
                       'module_key': 'reputation',
                       'description': '页面级权限：信誉事件；路径：/reputation/events；兼容父权限：reputation.view',
                       'is_system': 1,
                       'created_at': '2026-08-10 19:31:12'},
                      {'id': 35,
                       'permission_key': 'reputation.duplicates.view',
                       'permission_name': '查看重复检测',
                       'module_key': 'reputation',
                       'description': '页面级权限：重复检测；路径：/reputation/duplicates；兼容父权限：reputation.view',
                       'is_system': 1,
                       'created_at': '2026-08-10 19:31:12'},
                      {'id': 36,
                       'permission_key': 'reputation.merge_logs.view',
                       'permission_name': '查看合并日志',
                       'module_key': 'reputation',
                       'description': '页面级权限：合并日志；路径：/reputation/merge-logs；兼容父权限：reputation.view',
                       'is_system': 1,
                       'created_at': '2026-08-10 19:31:12'},
                      {'id': 37,
                       'permission_key': 'ai.daily.view',
                       'permission_name': '查看AI日报',
                       'module_key': 'staff',
                       'description': '页面级权限：AI日报；路径：/ai/daily；兼容父权限：staff.view',
                       'is_system': 1,
                       'created_at': '2026-08-10 19:31:12'},
                      {'id': 38,
                       'permission_key': 'staff.center.view',
                       'permission_name': '查看AI幕僚中心',
                       'module_key': 'staff',
                       'description': '页面级权限：AI幕僚中心；路径：/staff；兼容父权限：staff.view',
                       'is_system': 1,
                       'created_at': '2026-08-10 19:31:12'},
                      {'id': 39,
                       'permission_key': 'strategic.view',
                       'permission_name': '查看AI战略推演中心',
                       'module_key': 'staff',
                       'description': '页面级权限：AI战略推演中心；路径：/strategic；兼容父权限：staff.view',
                       'is_system': 1,
                       'created_at': '2026-08-10 19:31:12'},
                      {'id': 40,
                       'permission_key': 'tasks.view',
                       'permission_name': '查看战场任务协同中心',
                       'module_key': 'staff',
                       'description': '页面级权限：战场任务协同中心；路径：/tasks；兼容父权限：staff.view',
                       'is_system': 1,
                       'created_at': '2026-08-10 19:31:12'},
                      {'id': 41,
                       'permission_key': 'leaders.view',
                       'permission_name': '查看组长驾驶舱',
                       'module_key': 'staff',
                       'description': '页面级权限：组长驾驶舱；路径：/leaders；兼容父权限：staff.view',
                       'is_system': 1,
                       'created_at': '2026-08-10 19:31:12'},
                      {'id': 42,
                       'permission_key': 'command.view',
                       'permission_name': '查看盟务指挥中枢',
                       'module_key': 'staff',
                       'description': '页面级权限：盟务指挥中枢；路径：/command；兼容父权限：staff.view',
                       'is_system': 1,
                       'created_at': '2026-08-10 19:31:12'},
                      {'id': 43,
                       'permission_key': 'command.manage',
                       'permission_name': '指挥操作管理',
                       'module_key': 'command',
                       'description': 'V15.5 Workspace 指挥操作写权限',
                       'is_system': 1,
                       'created_at': '2026-08-11 16:52:39'},
                      {'id': 44,
                       'permission_key': 'identity.manage',
                       'permission_name': '身份资料管理',
                       'module_key': 'identity',
                       'description': 'V15.5 Workspace 身份资料写权限',
                       'is_system': 1,
                       'created_at': '2026-08-11 16:52:39'},
                      {'id': 45,
                       'permission_key': 'leaders.manage',
                       'permission_name': '负责人映射管理',
                       'module_key': 'leaders',
                       'description': 'V15.5 Workspace 负责人映射写权限',
                       'is_system': 1,
                       'created_at': '2026-08-11 16:52:39'},
                      {'id': 46,
                       'permission_key': 'strategic.manage',
                       'permission_name': '战略反馈管理',
                       'module_key': 'strategic',
                       'description': 'V15.5 Workspace 战略反馈写权限',
                       'is_system': 1,
                       'created_at': '2026-08-11 16:52:39'}],
 'v155_role_permissions': [{'role_id': 1, 'permission_id': 15, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 1, 'permission_id': 14, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 1, 'permission_id': 11, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 1, 'permission_id': 10, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 1, 'permission_id': 9, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 1, 'permission_id': 4, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 1, 'permission_id': 3, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 1, 'permission_id': 1, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 1, 'permission_id': 2, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 1, 'permission_id': 8, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 1, 'permission_id': 7, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 1, 'permission_id': 18, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 1, 'permission_id': 17, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 1, 'permission_id': 16, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 1, 'permission_id': 6, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 1, 'permission_id': 19, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 1, 'permission_id': 13, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 1, 'permission_id': 12, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 1, 'permission_id': 5, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 2, 'permission_id': 15, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 2, 'permission_id': 14, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 2, 'permission_id': 10, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 2, 'permission_id': 9, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 2, 'permission_id': 4, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 2, 'permission_id': 3, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 2, 'permission_id': 1, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 2, 'permission_id': 2, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 2, 'permission_id': 8, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 2, 'permission_id': 7, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 2, 'permission_id': 18, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 2, 'permission_id': 17, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 2, 'permission_id': 16, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 2, 'permission_id': 6, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 2, 'permission_id': 19, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 2, 'permission_id': 13, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 2, 'permission_id': 12, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 2, 'permission_id': 5, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 3, 'permission_id': 14, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 3, 'permission_id': 9, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 3, 'permission_id': 3, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 3, 'permission_id': 1, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 3, 'permission_id': 7, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 3, 'permission_id': 16, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 3, 'permission_id': 6, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 3, 'permission_id': 19, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 3, 'permission_id': 12, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 3, 'permission_id': 5, 'created_at': '2026-08-10 01:46:53'},
                           {'role_id': 1, 'permission_id': 43, 'created_at': '2026-08-11 16:52:39'},
                           {'role_id': 1, 'permission_id': 44, 'created_at': '2026-08-11 16:52:39'},
                           {'role_id': 1, 'permission_id': 45, 'created_at': '2026-08-11 16:52:39'},
                           {'role_id': 1, 'permission_id': 46, 'created_at': '2026-08-11 16:52:39'},
                           {'role_id': 2, 'permission_id': 43, 'created_at': '2026-08-11 16:52:39'},
                           {'role_id': 2, 'permission_id': 44, 'created_at': '2026-08-11 16:52:39'},
                           {'role_id': 2, 'permission_id': 45, 'created_at': '2026-08-11 16:52:39'},
                           {'role_id': 2,
                            'permission_id': 46,
                            'created_at': '2026-08-11 16:52:39'}],
 'v155_workspace_members': [{'id': 1,
                             'workspace_id': 1,
                             'user_id': 1,
                             'role_id': 1,
                             'status': 'active',
                             'is_default': 1,
                             'created_at': '2026-08-10 01:46:53',
                             'updated_at': '2026-08-10 01:46:53'},
                            {'id': 2,
                             'workspace_id': 1,
                             'user_id': 2,
                             'role_id': 3,
                             'status': 'active',
                             'is_default': 1,
                             'created_at': '2026-08-10 01:46:53',
                             'updated_at': '2026-08-10 01:46:53'}],
 'v155_workspace_battles': [],
 'v155_membership_permission_overrides': [],
 'v158_action_logs': []}

SUPER_ADMIN = {
    "id": 1,
    "username": "kinen",
    "role": "super_admin",
    "status": "active",
    "session_version": 1,
}

VIEWER = {
    "id": 2,
    "username": "MiniQ",
    "role": "viewer",
    "status": "active",
    "session_version": 1,
}

TARGET_MEMBERSHIP_ID = 2


def _connect(path):
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _build_db(path):
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row

    try:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.executescript(SCHEMA_SQL)

        for table, rows in SEED.items():
            if not rows:
                continue

            columns = list(rows[0].keys())
            column_sql = ",".join(
                f'"{column}"' for column in columns
            )
            placeholders = ",".join("?" for _ in columns)

            values = [
                tuple(row.get(column) for column in columns)
                for row in rows
            ]

            conn.executemany(
                f'INSERT INTO "{table}" '
                f'({column_sql}) VALUES ({placeholders})',
                values,
            )

        conn.commit()
        conn.execute("PRAGMA foreign_keys=ON")

        assert conn.execute(
            "PRAGMA quick_check"
        ).fetchone()[0] == "ok"

        assert conn.execute(
            "PRAGMA foreign_key_check"
        ).fetchall() == []

    finally:
        conn.close()


@pytest.fixture
def isolated_db(tmp_path):
    path = tmp_path / "access-center.sqlite3"
    _build_db(path)
    return path


@pytest.fixture(scope="session")
def app_module(tmp_path_factory):
    bootstrap_dir = tmp_path_factory.mktemp(
        "v155-access-center-app-bootstrap"
    )
    bootstrap_db = bootstrap_dir / "bootstrap.sqlite3"

    _build_db(bootstrap_db)

    real_connect = sqlite3.connect
    project_db = PROJECT_DB.resolve()

    def redirect_connect(database, *args, **kwargs):
        text = str(database)

        is_project_db = False

        if not text.startswith("file:"):
            try:
                is_project_db = (
                    Path(text).resolve()
                    == project_db
                )
            except Exception:
                is_project_db = False

        if is_project_db:
            database = str(bootstrap_db)

        return real_connect(
            database,
            *args,
            **kwargs,
        )

    sqlite3.connect = redirect_connect

    try:
        sys.modules.pop("app", None)
        module = importlib.import_module("app")

    finally:
        sqlite3.connect = real_connect

    module.DB_FILE = str(bootstrap_db)

    module.app.config.update(
        TESTING=True,
        SECRET_KEY=(
            "v155-access-center-integration-"
            "test-secret-only"
        ),
    )

    return module


@pytest.fixture
def harness(
    app_module,
    isolated_db,
    monkeypatch,
):
    auth = {
        "user": dict(SUPER_ADMIN),
    }

    monkeypatch.setattr(
        app_module,
        "DB_FILE",
        str(isolated_db),
    )

    def fake_validate_auth_session(
        conn,
        session_data,
    ):
        user = auth["user"]

        if user is None:
            return {
                "ok": False,
                "reason": "missing_session",
            }

        return {
            "ok": True,
            "user": dict(user),
        }

    monkeypatch.setattr(
        app_module,
        "validate_auth_session",
        fake_validate_auth_session,
    )

    import services.v155_rbac_request_context as context_module
    import services.v155_rbac_backend_permission_gate as gate_module

    def fake_populate(
        g_object,
        db_file,
        current_user,
    ):
        g_object.v155_access_context = {
            "test": True,
            "current_user": current_user,
        }

    monkeypatch.setattr(
        context_module,
        "populate_request_access_context",
        fake_populate,
    )

    monkeypatch.setattr(
        gate_module,
        "evaluate_backend_permission",
        lambda **kwargs: {
            "handled": False,
            "allowed": True,
        },
    )

    client = app_module.app.test_client()

    return {
        "client": client,
        "auth": auth,
        "db": isolated_db,
        "app_module": app_module,
    }


def _csrf(client):
    with client.session_transaction() as session_data:
        return issue_csrf_token(session_data)


def _last_flash_category(client):
    with client.session_transaction() as session_data:
        flashes = list(
            session_data.get("_flashes") or []
        )

    assert flashes
    return flashes[-1][0]


def _permission_row(path, permission_key):
    conn = _connect(path)

    try:
        return conn.execute(
            """
            SELECT *
            FROM v155_membership_permission_overrides o
            JOIN v155_permissions p
              ON p.id=o.permission_id
            WHERE o.membership_id=?
              AND p.permission_key=?
            """,
            (
                TARGET_MEMBERSHIP_ID,
                permission_key,
            ),
        ).fetchone()

    finally:
        conn.close()


def _valid_delta_permission(path):
    conn = _connect(path)

    try:
        row = conn.execute(
            """
            SELECT DISTINCT p.permission_key
            FROM v155_permissions p
            JOIN v155_role_permissions rp
              ON rp.permission_id=p.id
            JOIN v155_roles r
              ON r.id=rp.role_id
             AND r.workspace_id=1
             AND r.status='active'
            WHERE p.permission_key NOT IN (
                'account.manage',
                'security.manage'
            )
              AND NOT EXISTS (
                  SELECT 1
                  FROM v155_role_permissions baseline
                  WHERE baseline.role_id=3
                    AND baseline.permission_id=p.id
              )
            ORDER BY p.permission_key
            LIMIT 1
            """
        ).fetchone()

        assert row is not None
        return row["permission_key"]

    finally:
        conn.close()


def _non_grantable_permission(path):
    conn = _connect(path)

    try:
        row = conn.execute(
            """
            SELECT p.permission_key
            FROM v155_permissions p
            WHERE p.permission_key NOT IN (
                'account.manage',
                'security.manage'
            )
              AND NOT EXISTS (
                  SELECT 1
                  FROM v155_role_permissions rp
                  JOIN v155_roles r
                    ON r.id=rp.role_id
                  WHERE rp.permission_id=p.id
                    AND r.workspace_id=1
                    AND r.status='active'
              )
            ORDER BY p.permission_key
            LIMIT 1
            """
        ).fetchone()

        assert row is not None
        return row["permission_key"]

    finally:
        conn.close()


def _admin_state(path):
    conn = _connect(path)

    try:
        return get_membership_permission_admin_state(
            conn,
            target_membership_id=TARGET_MEMBERSHIP_ID,
        )

    finally:
        conn.close()


def test_unauthenticated_and_non_super_admin_forbidden(
    harness,
):
    client = harness["client"]

    harness["auth"]["user"] = None

    response = client.get(
        "/security/access-center"
    )

    assert response.status_code in (302, 303)
    location = response.headers["Location"]

    assert location.startswith("/login?")
    assert "next=/security/access-center" in location

    harness["auth"]["user"] = dict(VIEWER)

    response = client.get(
        "/security/access-center"
    )

    assert response.status_code == 403


def test_super_admin_get_and_existing_report_intact(
    harness,
):
    client = harness["client"]

    response = client.get(
        "/security/access-center"
    )

    assert response.status_code == 200

    body = response.get_data(as_text=True)

    assert "权限中心" in body
    assert "用户权限" in body
    assert "角色权限" in body
    assert "工作区" in body
    assert "成员权限覆盖" in body


def test_membership_selector_validation_and_render(
    harness,
):
    client = harness["client"]

    assert client.get(
        "/security/access-center?membership_id=abc"
    ).status_code == 400

    assert client.get(
        "/security/access-center?membership_id=0"
    ).status_code == 400

    assert client.get(
        "/security/access-center?membership_id=999999"
    ).status_code == 404

    response = client.get(
        f"/security/access-center?"
        f"membership_id={TARGET_MEMBERSHIP_ID}"
    )

    assert response.status_code == 200

    body = response.get_data(as_text=True)

    assert "MiniQ" in body
    assert "membership #2" in body


def test_csrf_and_unknown_action_rejected(
    harness,
):
    client = harness["client"]

    response = client.post(
        "/security/access-center",
        data={
            "action":
                "set_membership_permission_override",
            "target_membership_id":
                str(TARGET_MEMBERSHIP_ID),
            "permission_key":
                "dashboard.view",
            "effect":
                "grant",
        },
    )

    assert response.status_code == 400

    response = client.post(
        "/security/access-center",
        data={
            "csrf_token": _csrf(client),
            "action": "unknown_action",
        },
    )

    assert response.status_code == 400


def test_grant_deny_clear_prg_flash_audit_and_session_version(
    harness,
):
    client = harness["client"]
    db = harness["db"]

    permission_key = _valid_delta_permission(db)

    conn = _connect(db)

    try:
        session_before = conn.execute(
            """
            SELECT session_version
            FROM v158_users
            WHERE id=2
            """
        ).fetchone()[0]

    finally:
        conn.close()

    response = client.post(
        "/security/access-center",
        data={
            "csrf_token": _csrf(client),
            "action":
                "set_membership_permission_override",
            "target_membership_id":
                str(TARGET_MEMBERSHIP_ID),
            "permission_key":
                permission_key,
            "effect":
                "grant",
        },
    )

    assert response.status_code in (302, 303)
    assert (
        f"membership_id={TARGET_MEMBERSHIP_ID}"
        in response.headers["Location"]
    )
    assert _last_flash_category(client) == "success"

    row = _permission_row(
        db,
        permission_key,
    )

    assert row is not None
    assert row["effect"] == "grant"

    state = _admin_state(db)

    item = next(
        item
        for item in state["permissions"]
        if item["permission_key"] == permission_key
    )

    assert item["override_effect"] == "grant"
    assert item["effective"] is True

    response = client.get(
        response.headers["Location"]
    )

    assert response.status_code == 200
    assert permission_key in response.get_data(
        as_text=True
    )

    response = client.post(
        "/security/access-center",
        data={
            "csrf_token": _csrf(client),
            "action":
                "set_membership_permission_override",
            "target_membership_id":
                str(TARGET_MEMBERSHIP_ID),
            "permission_key":
                permission_key,
            "effect":
                "deny",
        },
    )

    assert response.status_code in (302, 303)
    assert _last_flash_category(client) == "success"

    row = _permission_row(
        db,
        permission_key,
    )

    assert row is not None
    assert row["effect"] == "deny"

    state = _admin_state(db)

    item = next(
        item
        for item in state["permissions"]
        if item["permission_key"] == permission_key
    )

    assert item["override_effect"] == "deny"
    assert item["effective"] is False

    response = client.post(
        "/security/access-center",
        data={
            "csrf_token": _csrf(client),
            "action":
                "clear_membership_permission_override",
            "target_membership_id":
                str(TARGET_MEMBERSHIP_ID),
            "permission_key":
                permission_key,
        },
    )

    assert response.status_code in (302, 303)
    assert _last_flash_category(client) == "success"

    assert _permission_row(
        db,
        permission_key,
    ) is None

    conn = _connect(db)

    try:
        session_after = conn.execute(
            """
            SELECT session_version
            FROM v158_users
            WHERE id=2
            """
        ).fetchone()[0]

        actions = conn.execute(
            """
            SELECT action_key, result_status
            FROM v158_action_logs
            WHERE target_type=
                'workspace_membership_permission'
            ORDER BY id
            """
        ).fetchall()

    finally:
        conn.close()

    assert session_after == session_before

    success_actions = [
        row["action_key"]
        for row in actions
        if row["result_status"] == "success"
    ]

    assert "membership_permission_grant" in success_actions
    assert "membership_permission_deny" in success_actions
    assert "membership_permission_clear" in success_actions


def test_platform_and_non_grantable_permissions_blocked(
    harness,
):
    client = harness["client"]
    db = harness["db"]

    for permission_key in (
        "account.manage",
        _non_grantable_permission(db),
    ):
        response = client.post(
            "/security/access-center",
            data={
                "csrf_token": _csrf(client),
                "action":
                    "set_membership_permission_override",
                "target_membership_id":
                    str(TARGET_MEMBERSHIP_ID),
                "permission_key":
                    permission_key,
                "effect":
                    "grant",
            },
        )

        assert response.status_code in (302, 303)
        assert _last_flash_category(client) == "warning"

        assert _permission_row(
            db,
            permission_key,
        ) is None


def test_audit_failure_rolls_route_mutation_back(
    harness,
    monkeypatch,
):
    client = harness["client"]
    db = harness["db"]

    permission_key = _valid_delta_permission(db)

    import services.v155_membership_permission_override_service as override_module

    def fail_audit(*args, **kwargs):
        raise sqlite3.OperationalError(
            "forced integration audit failure"
        )

    monkeypatch.setattr(
        override_module,
        "record_action_log",
        fail_audit,
    )

    response = client.post(
        "/security/access-center",
        data={
            "csrf_token": _csrf(client),
            "action":
                "set_membership_permission_override",
            "target_membership_id":
                str(TARGET_MEMBERSHIP_ID),
            "permission_key":
                permission_key,
            "effect":
                "grant",
        },
    )

    assert response.status_code in (302, 303)
    assert _last_flash_category(client) == "error"

    assert _permission_row(
        db,
        permission_key,
    ) is None
