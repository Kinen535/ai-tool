"""Presentation and creation flow for the existing scoped reputation store."""
import sqlite3

from flask import abort, g, redirect, render_template, request

from services.v155_workspace_data_boundary import (
    WorkspaceDataBoundaryError, resolve_workspace_data_boundary,
)
from services.v156_reputation_store import (
    add_reputation_event_relation_scoped,
    build_reputation_home_report_scoped,
    create_reputation_event_scoped,
    create_reputation_subject_scoped,
    ensure_reputation_tables,
    get_reputation_subject_scoped,
    list_reputation_subjects_scoped,
    make_reputation_workspace_scoped_connection,
)


def _battle_id():
    try:
        boundary = resolve_workspace_data_boundary(
            getattr(g, "v155_access_context", None)
        )
        battle_id = int(boundary.current_battle_id)
    except (WorkspaceDataBoundaryError, AttributeError, TypeError, ValueError):
        abort(403)
    if battle_id <= 0:
        abort(403)
    return battle_id


def _connection():
    conn = sqlite3.connect("data/snapshots.db")
    conn.row_factory = sqlite3.Row
    return conn


def home():
    battle_id = _battle_id()
    conn = _connection()
    try:
        report = build_reputation_home_report_scoped(conn, battle_id=battle_id)
        scoped = make_reputation_workspace_scoped_connection(conn, battle_id)
        report["recent_subjects"] = scoped.execute(
            "SELECT * FROM v156_reputation_subjects "
            "ORDER BY updated_at DESC, id DESC LIMIT 6"
        ).fetchall()
    finally:
        conn.close()
    return render_template("reputation_home.html", report=report, title="信誉档案库")


def subject_new():
    battle_id = _battle_id()
    data = dict(request.form) if request.method == "POST" else {}
    if request.method == "POST":
        keys = ("subject_type", "display_name", "game_id", "alias_names",
                "trust_level", "risk_level", "status", "note")
        values = {key: (data.get(key) or "").strip() for key in keys}
        defaults = {"subject_type": "player", "trust_level": "unknown",
                    "risk_level": "normal", "status": "active"}
        for key, default in defaults.items():
            values[key] = values[key] or default
        values["source_type"] = (data.get("source") or "manual").strip() or "manual"
        if not values["display_name"] and not values["game_id"]:
            return render_template(
                "reputation_subject_new.html", title="新建档案", form_data=data,
                form_error="名称和游戏编号至少填写一项。",
            ), 400
        conn = _connection()
        try:
            ensure_reputation_tables(conn)
            subject_id = create_reputation_subject_scoped(
                conn, values, battle_id=battle_id
            )
        finally:
            conn.close()
        return redirect(f"/reputation/subjects/{subject_id}?created=1")
    prefill = request.args.get("prefill", "").strip()
    if prefill:
        data["game_id" if prefill.isdigit() else "display_name"] = prefill
    return render_template(
        "reputation_subject_new.html", title="新建档案", form_data=data,
        form_error=("名称和游戏编号至少填写一项。"
                    if request.args.get("error") == "missing" else ""),
    )


def _subject_id(raw):
    value = str(raw or "").strip()
    if not value:
        return 0
    try:
        number = int(value)
    except (TypeError, ValueError):
        abort(400)
    if number <= 0:
        abort(400)
    return number


def _event_form(conn, battle_id, data, error=""):
    subject_id = _subject_id(data.get("subject_id"))
    selected = None
    if subject_id:
        selected = get_reputation_subject_scoped(
            conn, subject_id, battle_id=battle_id
        )
        if selected is None:
            abort(404)
    subjects = list_reputation_subjects_scoped(
        conn, limit=5000, battle_id=battle_id
    )
    if selected is not None and not any(s["id"] == subject_id for s in subjects):
        subjects.insert(0, dict(selected))
    return render_template(
        "reputation_event_new.html", title="记录事件", form_data=data,
        form_error=error, subjects=subjects, selected_subject=selected,
        selected_subject_id=subject_id,
    )


def event_new():
    battle_id = _battle_id()
    conn = _connection()
    try:
        ensure_reputation_tables(conn)
        return _event_form(conn, battle_id, {
            "subject_id": request.args.get("subject_id", ""),
            "title": request.args.get("prefill", ""),
        })
    finally:
        conn.close()


class _DeferredCommits:
    """Let the unchanged store calls share one outer transaction."""
    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def commit(self):
        pass


def event_create():
    battle_id = _battle_id()
    data = dict(request.form)
    # Retain the aliases accepted by the existing /reputation/events POST.
    data["title"] = (data.get("title") or data.get("event_title") or "").strip()
    data["summary"] = (data.get("summary") or data.get("event_summary") or "").strip()
    data["evidence_note"] = (data.get("evidence_note") or data.get("evidence")
                             or data.get("note") or "").strip()
    conn = _connection()
    try:
        ensure_reputation_tables(conn)
        subject_id = _subject_id(data.get("subject_id"))
        if subject_id and get_reputation_subject_scoped(
            conn, subject_id, battle_id=battle_id
        ) is None:
            abort(404)
        if not data["title"]:
            return _event_form(conn, battle_id, data, "请填写事件标题。"), 400
        values = {key: (data.get(key) or "").strip() for key in (
            "title", "event_type", "impact_level", "status",
            "event_time", "summary", "evidence_note",
        )}
        for key, default in (("event_type", "normal"), ("impact_level", "low"),
                             ("status", "recorded")):
            values[key] = values[key] or default
        conn.execute("BEGIN IMMEDIATE")
        try:
            deferred = _DeferredCommits(conn)
            event_id = create_reputation_event_scoped(
                deferred, values, battle_id=battle_id
            )
            if subject_id:
                relation_id = add_reputation_event_relation_scoped(
                    deferred, event_id=event_id, subject_id=subject_id,
                    relation_role=(data.get("relation_role") or "关联对象").strip(),
                    note=(data.get("relation_note") or "").strip(),
                    battle_id=battle_id,
                )
                if relation_id is None:
                    abort(409)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    finally:
        conn.close()
    return redirect(f"/reputation/events/{event_id}?created=1")
