from __future__ import annotations

from flask import (
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
    Response,
)

import csv
import hmac
import io
import json
import re
import secrets


MAX_IMPORT_ROWS = 500
MAX_UPLOAD_BYTES = 5 * 1024 * 1024

HEADER_ALIASES = {
    "display_name": (
        "名称",
        "玩家名称",
        "角色名",
        "display_name",
        "name",
    ),
    "game_id": (
        "游戏编号",
        "游戏id",
        "游戏ID",
        "编号",
        "game_id",
    ),
    "alias_names": (
        "曾用名",
        "别名",
        "alias_names",
    ),
    "subject_type": (
        "对象类型",
        "类型",
        "subject_type",
    ),
    "source_type": (
        "资料来源",
        "来源",
        "source_type",
    ),
    "note": (
        "背景与备注",
        "备注",
        "说明",
        "note",
    ),
}


def _clean(value):
    return str(
        value
        if value is not None
        else ""
    ).strip()


def _normalize_header(value):
    return re.sub(
        r"\s+",
        "",
        _clean(value),
    ).lower()


def _header_map(headers):
    lookup = {}

    for canonical, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            lookup[
                _normalize_header(alias)
            ] = canonical

    mapped = {}

    for index, header in enumerate(headers):
        key = lookup.get(
            _normalize_header(header)
        )

        if key:
            mapped[index] = key

    return mapped


def _normalize_game_id(value):
    value = _clean(value)

    if re.fullmatch(
        r"\d+\.0+",
        value,
    ):
        value = value.split(
            ".",
            1,
        )[0]

    return value


def _normalize_subject_type(value):
    value = _clean(value)

    mapping = {
        "": "player",
        "玩家": "player",
        "player": "player",
    }

    return mapping.get(
        value.lower()
        if value
        else "",
        value,
    )


def _decode_csv(raw):
    errors = []

    for encoding in (
        "utf-8-sig",
        "utf-8",
        "gb18030",
    ):

        try:
            return raw.decode(
                encoding
            )

        except UnicodeDecodeError as exc:
            errors.append(
                str(exc)
            )

    raise ValueError(
        "无法识别 CSV 编码，请使用 Excel 另存为 UTF-8 CSV。"
    )


def parse_subject_csv_bytes(raw):
    if not raw:
        raise ValueError(
            "上传文件为空。"
        )

    if len(raw) > MAX_UPLOAD_BYTES:
        raise ValueError(
            "上传文件超过 5MB 限制。"
        )

    text = _decode_csv(
        raw
    )

    reader = csv.reader(
        io.StringIO(text)
    )

    rows = list(reader)

    if not rows:
        raise ValueError(
            "CSV 中没有数据。"
        )

    headers = rows[0]

    mapped = _header_map(
        headers
    )

    required = {
        "display_name",
        "game_id",
    }

    if not required.issubset(
        set(mapped.values())
    ):
        raise ValueError(
            "模板必须包含“名称”和“游戏编号”两列。"
        )

    parsed = []

    for source_row_number, values in enumerate(
        rows[1:],
        2,
    ):

        if not any(
            _clean(value)
            for value in values
        ):
            continue

        record = {
            "source_row":
                source_row_number,

            "display_name":
                "",

            "game_id":
                "",

            "alias_names":
                "",

            "subject_type":
                "player",

            "source_type":
                "bulk_import",

            "note":
                "",
        }

        for index, canonical in mapped.items():

            if index >= len(values):
                continue

            record[
                canonical
            ] = _clean(
                values[index]
            )

        record["game_id"] = (
            _normalize_game_id(
                record["game_id"]
            )
        )

        record["subject_type"] = (
            _normalize_subject_type(
                record["subject_type"]
            )
            or "player"
        )

        if not record["source_type"]:
            record["source_type"] = (
                "bulk_import"
            )

        parsed.append(
            record
        )

    if not parsed:
        raise ValueError(
            "模板中没有可导入的数据行。"
        )

    if len(parsed) > MAX_IMPORT_ROWS:
        raise ValueError(
            "单次最多导入 "
            + str(MAX_IMPORT_ROWS)
            + " 行。"
        )

    return parsed


def _workspace_id_for_battle(
    conn,
    battle_id,
):
    row = conn.execute(
        """
        SELECT workspace_id
        FROM v155_workspace_battles
        WHERE battle_id=?
        LIMIT 1
        """,
        (
            int(battle_id),
        ),
    ).fetchone()

    if row is None:
        raise ValueError(
            "当前战场没有有效工作区映射。"
        )

    return int(
        row[0]
    )


def build_subject_preview(
    conn,
    battle_id,
    records,
):
    workspace_id = (
        _workspace_id_for_battle(
            conn,
            battle_id,
        )
    )

    existing_rows = conn.execute(
        """
        SELECT
            id,
            display_name,
            game_id
        FROM v156_reputation_subjects
        WHERE workspace_id=?
        """,
        (
            workspace_id,
        ),
    ).fetchall()

    existing = {}

    for row in existing_rows:
        game_id = _normalize_game_id(
            row["game_id"]
        )

        if game_id:
            existing[
                game_id
            ] = {
                "id":
                    int(row["id"]),

                "display_name":
                    _clean(
                        row["display_name"]
                    ),
            }

    battle_links = {
        int(row[0])
        for row in conn.execute(
            """
            SELECT subject_id
            FROM v156_reputation_subject_battles
            WHERE workspace_id=?
              AND battle_id=?
            """,
            (
                workspace_id,
                int(battle_id),
            ),
        ).fetchall()
    }

    seen_file_ids = set()

    preview = []

    counts = {
        "total": 0,
        "create": 0,
        "reuse": 0,
        "error": 0,
        "already_linked": 0,
        "new_battle_link": 0,
    }

    for raw in records:

        record = dict(raw)

        record["display_name"] = _clean(
            record.get(
                "display_name"
            )
        )

        record["game_id"] = (
            _normalize_game_id(
                record.get(
                    "game_id"
                )
            )
        )

        record["alias_names"] = _clean(
            record.get(
                "alias_names"
            )
        )

        record["subject_type"] = (
            _normalize_subject_type(
                record.get(
                    "subject_type"
                )
            )
            or "player"
        )

        record["source_type"] = (
            _clean(
                record.get(
                    "source_type"
                )
            )
            or "bulk_import"
        )

        record["note"] = _clean(
            record.get(
                "note"
            )
        )

        record["action"] = ""
        record["message"] = ""
        record["subject_id"] = None
        record["existing_name"] = ""
        record["battle_link"] = ""

        counts["total"] += 1

        if not record["display_name"]:
            record["action"] = "error"
            record["message"] = "名称不能为空"

        elif not record["game_id"]:
            record["action"] = "error"
            record["message"] = "游戏编号不能为空"

        elif len(record["game_id"]) > 64:
            record["action"] = "error"
            record["message"] = "游戏编号长度异常"

        elif record["game_id"] in seen_file_ids:
            record["action"] = "error"
            record["message"] = "文件内游戏编号重复"

        else:
            seen_file_ids.add(
                record["game_id"]
            )

            old = existing.get(
                record["game_id"]
            )

            if old:
                record["action"] = "reuse"
                record["subject_id"] = old["id"]
                record["existing_name"] = (
                    old["display_name"]
                )

                if (
                    old["id"]
                    in battle_links
                ):
                    record["battle_link"] = (
                        "已关联当前战场"
                    )
                    counts[
                        "already_linked"
                    ] += 1

                else:
                    record["battle_link"] = (
                        "将关联当前战场"
                    )
                    counts[
                        "new_battle_link"
                    ] += 1

                if (
                    old["display_name"]
                    and old["display_name"]
                    != record["display_name"]
                ):
                    record["message"] = (
                        "名称不同，保留原档案名称，不自动覆盖"
                    )

            else:
                record["action"] = "create"
                record["battle_link"] = (
                    "将创建并关联当前战场"
                )
                counts[
                    "new_battle_link"
                ] += 1

        if record["action"] == "create":
            counts["create"] += 1

        elif record["action"] == "reuse":
            counts["reuse"] += 1

        else:
            counts["error"] += 1

        preview.append(
            record
        )

    return {
        "workspace_id":
            workspace_id,

        "battle_id":
            int(battle_id),

        "counts":
            counts,

        "rows":
            preview,
    }


def _valid_payload_rows(
    rows,
):
    output = []

    seen = set()

    for row in rows:

        game_id = _normalize_game_id(
            row.get(
                "game_id"
            )
        )

        display_name = _clean(
            row.get(
                "display_name"
            )
        )

        if (
            not game_id
            or not display_name
        ):
            continue

        if game_id in seen:
            continue

        seen.add(
            game_id
        )

        output.append({
            "display_name":
                display_name,

            "game_id":
                game_id,

            "alias_names":
                _clean(
                    row.get(
                        "alias_names"
                    )
                ),

            "subject_type":
                (
                    _normalize_subject_type(
                        row.get(
                            "subject_type"
                        )
                    )
                    or "player"
                ),

            "source_type":
                (
                    _clean(
                        row.get(
                            "source_type"
                        )
                    )
                    or "bulk_import"
                ),

            "note":
                _clean(
                    row.get(
                        "note"
                    )
                ),
        })

    return output


def commit_subject_rows(
    conn,
    battle_id,
    rows,
):
    rows = _valid_payload_rows(
        rows
    )

    if not rows:
        raise ValueError(
            "没有可确认导入的数据。"
        )

    if len(rows) > MAX_IMPORT_ROWS:
        raise ValueError(
            "确认数据超过单次导入限制。"
        )

    workspace_id = (
        _workspace_id_for_battle(
            conn,
            battle_id,
        )
    )

    started_transaction = (
        not conn.in_transaction
    )

    savepoint = (
        "reputation_bulk_import"
    )

    if started_transaction:
        conn.execute(
            "BEGIN IMMEDIATE"
        )
    else:
        conn.execute(
            "SAVEPOINT "
            + savepoint
        )

    created = 0
    reused = 0
    linked = 0

    try:

        for row in rows:

            existing = conn.execute(
                """
                SELECT
                    id,
                    display_name
                FROM v156_reputation_subjects
                WHERE workspace_id=?
                  AND TRIM(game_id)=?
                LIMIT 1
                """,
                (
                    workspace_id,
                    row["game_id"],
                ),
            ).fetchone()

            if existing is not None:
                subject_id = int(
                    existing["id"]
                )

                reused += 1

            else:

                cursor = conn.execute(
                    """
                    INSERT INTO
                        v156_reputation_subjects (
                            workspace_id,
                            battle_id,
                            subject_type,
                            display_name,
                            game_id,
                            alias_names,
                            trust_level,
                            risk_level,
                            status,
                            source_type,
                            note,
                            updated_at
                        )
                    VALUES (
                        ?, ?, ?, ?, ?, ?,
                        'unknown',
                        'normal',
                        'active',
                        ?, ?,
                        datetime(
                            'now',
                            'localtime'
                        )
                    )
                    """,
                    (
                        workspace_id,
                        int(battle_id),
                        row["subject_type"],
                        row["display_name"],
                        row["game_id"],
                        row["alias_names"],
                        row["source_type"],
                        row["note"],
                    ),
                )

                subject_id = int(
                    cursor.lastrowid
                )

                created += 1

            before_link = conn.execute(
                """
                SELECT 1
                FROM v156_reputation_subject_battles
                WHERE workspace_id=?
                  AND subject_id=?
                  AND battle_id=?
                LIMIT 1
                """,
                (
                    workspace_id,
                    subject_id,
                    int(battle_id),
                ),
            ).fetchone()

            conn.execute(
                """
                INSERT OR IGNORE INTO
                    v156_reputation_subject_battles (
                        workspace_id,
                        subject_id,
                        battle_id,
                        first_seen_at,
                        last_seen_at,
                        source_type,
                        updated_at
                    )
                VALUES (
                    ?, ?, ?,
                    datetime('now','localtime'),
                    datetime('now','localtime'),
                    'bulk_import',
                    datetime('now','localtime')
                )
                """,
                (
                    workspace_id,
                    subject_id,
                    int(battle_id),
                ),
            )

            conn.execute(
                """
                UPDATE
                    v156_reputation_subject_battles
                SET
                    last_seen_at=
                        datetime('now','localtime'),
                    updated_at=
                        datetime('now','localtime')
                WHERE workspace_id=?
                  AND subject_id=?
                  AND battle_id=?
                """,
                (
                    workspace_id,
                    subject_id,
                    int(battle_id),
                ),
            )

            if before_link is None:
                linked += 1

        if started_transaction:
            conn.commit()

        else:
            conn.execute(
                "RELEASE SAVEPOINT "
                + savepoint
            )

    except Exception:

        if started_transaction:
            conn.rollback()

        else:
            conn.execute(
                "ROLLBACK TO SAVEPOINT "
                + savepoint
            )

            conn.execute(
                "RELEASE SAVEPOINT "
                + savepoint
            )

        raise

    return {
        "created":
            created,

        "reused":
            reused,

        "battle_links_added":
            linked,

        "processed":
            created + reused,
    }


def _csrf_token():
    key = (
        "reputation_subject_bulk_import_csrf"
    )

    token = session.get(
        key
    )

    if not token:
        token = secrets.token_urlsafe(
            32
        )
        session[key] = token

    return token


def _validate_csrf(value):
    expected = session.get(
        "reputation_subject_bulk_import_csrf",
        "",
    )

    return bool(
        expected
        and value
        and hmac.compare_digest(
            expected,
            value,
        )
    )


def subject_import_template_response():
    content = (
        "\ufeff"
        "名称,游戏编号,曾用名,对象类型,资料来源,背景与备注\r\n"
        "示例玩家,31475391,,玩家,批量导入,示例行可删除\r\n"
    )

    return Response(
        content,
        mimetype="text/csv; charset=utf-8",
        headers={
            "Content-Disposition":
                "attachment; "
                "filename=reputation_subject_import_template.csv"
        },
    )


def subject_import_handler(
    conn,
    battle_id,
):
    try:

        csrf_token = (
            _csrf_token()
        )

        if request.method == "GET":
            return render_template(
                "reputation_subject_import.html",
                csrf_token=csrf_token,
                battle_id=battle_id,
                preview=None,
                rows_json="",
                result=None,
            )

        if not _validate_csrf(
            request.form.get(
                "csrf_token",
                "",
            )
        ):
            flash(
                "批量导入请求校验失败，请刷新页面后重试。",
                "error",
            )

            return redirect(
                url_for(
                    "v156_reputation_subject_import"
                )
            )

        action = (
            request.form.get(
                "action",
                "preview",
            )
            or "preview"
        )

        if action == "preview":

            upload = request.files.get(
                "import_file"
            )

            if (
                upload is None
                or not upload.filename
            ):
                raise ValueError(
                    "请选择 CSV 文件。"
                )

            filename = (
                upload.filename
                or ""
            ).lower()

            if not filename.endswith(
                ".csv"
            ):
                raise ValueError(
                    "当前版本请上传 CSV 文件。"
                )

            raw = upload.read(
                MAX_UPLOAD_BYTES + 1
            )

            records = (
                parse_subject_csv_bytes(
                    raw
                )
            )

            preview = (
                build_subject_preview(
                    conn,
                    battle_id,
                    records,
                )
            )

            valid_rows = [
                row
                for row in preview["rows"]
                if row["action"]
                in (
                    "create",
                    "reuse",
                )
            ]

            rows_json = json.dumps(
                valid_rows,
                ensure_ascii=False,
                separators=(
                    ",",
                    ":",
                ),
            )

            return render_template(
                "reputation_subject_import.html",
                csrf_token=csrf_token,
                battle_id=battle_id,
                preview=preview,
                rows_json=rows_json,
                result=None,
            )

        if action == "confirm":

            raw_json = request.form.get(
                "rows_json",
                "",
            )

            try:
                rows = json.loads(
                    raw_json
                )

            except Exception as exc:
                raise ValueError(
                    "预览数据已失效，请重新上传文件。"
                ) from exc

            if not isinstance(
                rows,
                list,
            ):
                raise ValueError(
                    "预览数据格式错误。"
                )

            result = (
                commit_subject_rows(
                    conn,
                    battle_id,
                    rows,
                )
            )

            flash(
                "批量导入完成：新增 "
                + str(
                    result["created"]
                )
                + "，复用 "
                + str(
                    result["reused"]
                )
                + "，新增当前战场关联 "
                + str(
                    result[
                        "battle_links_added"
                    ]
                )
                + "。",
                "success",
            )

            return render_template(
                "reputation_subject_import.html",
                csrf_token=csrf_token,
                battle_id=battle_id,
                preview=None,
                rows_json="",
                result=result,
            )

        raise ValueError(
            "未知导入操作。"
        )

    except ValueError as exc:

        flash(
            str(exc),
            "error",
        )

        return render_template(
            "reputation_subject_import.html",
            csrf_token=_csrf_token(),
            battle_id=battle_id,
            preview=None,
            rows_json="",
            result=None,
        )

    finally:
        try:
            conn.close()
        except Exception:
            pass


# =================================================================
# A5-A3 formal event bulk import
# =================================================================

_EVENT_IMPORT_MAX_ROWS = 500
_EVENT_IMPORT_MAX_BYTES = 5 * 1024 * 1024

_EVENT_TYPE_MAP = {
    "general": "general",
    "normal": "normal",
    "普通记录": "normal",
    "betrayal": "betrayal",
    "背刺": "betrayal",
    "背刺/跳反": "betrayal",
    "背刺 / 跳反": "betrayal",
    "fraud": "fraud",
    "欺诈": "fraud",
    "欺诈/诈骗": "fraud",
    "欺诈 / 诈骗": "fraud",
    "conflict": "conflict",
    "纠纷": "conflict",
    "纠纷/冲突": "conflict",
    "纠纷 / 冲突": "conflict",
    "cooperation": "cooperation",
    "合作履约": "cooperation",
    "management": "management",
    "管理事件": "management",
    "other": "other",
    "其他": "other",
    "resource_dispute": "resource_dispute",
    "资源纠纷": "resource_dispute",
    "contract_break": "contract_break",
    "合作履约问题": "contract_break",
    "positive": "positive",
    "正向信誉记录": "positive",
}

_EVENT_IMPACT_MAP = {
    "low": "low",
    "轻微": "low",
    "normal": "normal",
    "普通": "normal",
    "medium": "medium",
    "中": "medium",
    "high": "high",
    "高": "high",
    "severe": "severe",
    "严重": "severe",
    "critical": "critical",
    "极严重": "critical",
}

_EVENT_STATUS_MAP = {
    "recorded": "recorded",
    "记录中": "recorded",
    "verified": "verified",
    "已核实": "verified",
    "disputed": "disputed",
    "有争议": "disputed",
    "archived": "archived",
    "已归档": "archived",
    "pending": "pending",
    "待核实": "pending",
    "resolved": "resolved",
    "已处理": "resolved",
    "voided": "voided",
    "已作废": "voided",
}

_EVENT_HEADER_ALIASES = {
    "title": (
        "事件标题",
        "标题",
        "title",
        "event_title",
    ),
    "game_id": (
        "游戏编号",
        "game_id",
        "游戏id",
        "游戏ID",
    ),
    "event_type": (
        "事件类型",
        "类型",
        "event_type",
    ),
    "impact_level": (
        "影响级别",
        "影响等级",
        "impact_level",
    ),
    "status": (
        "状态",
        "事件状态",
        "status",
    ),
    "event_time": (
        "事件时间",
        "时间",
        "event_time",
    ),
    "summary": (
        "摘要",
        "事件摘要",
        "summary",
    ),
    "evidence_note": (
        "证据备注",
        "证据",
        "evidence_note",
    ),
    "relation_role": (
        "关联角色",
        "关系角色",
        "relation_role",
    ),
    "relation_note": (
        "关联备注",
        "关系备注",
        "relation_note",
    ),
}


def _event_header_map(headers):
    normalized_actual = {}

    for actual in headers or []:
        normalized_actual[
            _normalize_header(actual)
        ] = actual

    result = {}

    for canonical, aliases in (
        _EVENT_HEADER_ALIASES.items()
    ):
        for alias in aliases:
            key = _normalize_header(alias)

            if key in normalized_actual:
                result[canonical] = (
                    normalized_actual[key]
                )
                break

    return result


def _normalize_event_choice(
    value,
    mapping,
    default,
):
    value = _clean(value)

    if not value:
        return default, ""

    if value in mapping:
        return mapping[value], ""

    lowered = value.lower()

    if lowered in mapping:
        return mapping[lowered], ""

    return "", value


def parse_event_csv_bytes(raw):
    import csv
    import io

    if not isinstance(
        raw,
        (bytes, bytearray),
    ):
        raise ValueError(
            "上传内容不是有效的 CSV 文件。"
        )

    if len(raw) > _EVENT_IMPORT_MAX_BYTES:
        raise ValueError(
            "CSV 文件不能超过 5MB。"
        )

    text = _decode_csv(
        bytes(raw)
    )

    reader = csv.DictReader(
        io.StringIO(text)
    )

    headers = reader.fieldnames or []

    mapping = _event_header_map(
        headers
    )

    missing = [
        label
        for key, label
        in (
            ("title", "事件标题"),
            ("game_id", "游戏编号"),
        )
        if key not in mapping
    ]

    if missing:
        raise ValueError(
            "缺少必填列："
            + "、".join(missing)
        )

    records = []

    for source_row, raw_row in enumerate(
        reader,
        2,
    ):
        if len(records) >= _EVENT_IMPORT_MAX_ROWS:
            raise ValueError(
                "单次最多导入 500 行。"
            )

        values = {}

        for canonical in (
            _EVENT_HEADER_ALIASES
        ):
            actual = mapping.get(
                canonical
            )

            values[canonical] = (
                _clean(
                    raw_row.get(
                        actual,
                        "",
                    )
                )
                if actual
                else ""
            )

        title = values["title"]

        game_id = _normalize_game_id(
            values["game_id"]
        )

        event_type, bad_event_type = (
            _normalize_event_choice(
                values["event_type"],
                _EVENT_TYPE_MAP,
                "normal",
            )
        )

        impact_level, bad_impact = (
            _normalize_event_choice(
                values["impact_level"],
                _EVENT_IMPACT_MAP,
                "low",
            )
        )

        status, bad_status = (
            _normalize_event_choice(
                values["status"],
                _EVENT_STATUS_MAP,
                "recorded",
            )
        )

        errors = []

        if not title:
            errors.append(
                "事件标题不能为空"
            )

        if not game_id:
            errors.append(
                "游戏编号不能为空"
            )

        if bad_event_type:
            errors.append(
                "不支持的事件类型："
                + bad_event_type
            )

        if bad_impact:
            errors.append(
                "不支持的影响级别："
                + bad_impact
            )

        if bad_status:
            errors.append(
                "不支持的状态："
                + bad_status
            )

        records.append({
            "source_row":
                source_row,

            "title":
                title,

            "game_id":
                game_id,

            "event_type":
                event_type,

            "impact_level":
                impact_level,

            "status":
                status,

            "event_time":
                values["event_time"],

            "summary":
                values["summary"],

            "evidence_note":
                values["evidence_note"],

            "relation_role":
                (
                    values["relation_role"]
                    or "关联对象"
                ),

            "relation_note":
                values["relation_note"],

            "parse_error":
                "；".join(errors),
        })

    if not records:
        raise ValueError(
            "CSV 中没有可导入的数据行。"
        )

    return records


def _event_subject_rows(
    conn,
    workspace_id,
    game_id,
):
    return conn.execute(
        """
        SELECT
            id,
            display_name,
            game_id
        FROM v156_reputation_subjects
        WHERE workspace_id=?
          AND TRIM(game_id)=?
        ORDER BY id
        LIMIT 2
        """,
        (
            int(workspace_id),
            str(game_id),
        ),
    ).fetchall()


def build_event_preview(
    conn,
    battle_id,
    records,
):
    conn.row_factory = __import__(
        "sqlite3"
    ).Row

    workspace_id = (
        _workspace_id_for_battle(
            conn,
            battle_id,
        )
    )

    rows = []

    seen = set()

    counts = {
        "total": 0,
        "create": 0,
        "error": 0,
        "matched": 0,
    }

    for record in records:
        row = dict(record)

        counts["total"] += 1

        error = _clean(
            row.get(
                "parse_error",
                "",
            )
        )

        duplicate_key = (
            _clean(
                row.get(
                    "title",
                    "",
                )
            ).casefold(),
            _clean(
                row.get(
                    "event_time",
                    "",
                )
            ).casefold(),
            _normalize_game_id(
                row.get(
                    "game_id",
                    "",
                )
            ),
        )

        if (
            duplicate_key
            in seen
        ):
            if error:
                error += "；"

            error += (
                "CSV 内存在重复事件行"
            )

        else:
            seen.add(
                duplicate_key
            )

        subject_rows = []

        game_id = _normalize_game_id(
            row.get(
                "game_id",
                "",
            )
        )

        if (
            not error
            and game_id
        ):
            subject_rows = (
                _event_subject_rows(
                    conn,
                    workspace_id,
                    game_id,
                )
            )

            if len(subject_rows) == 0:
                error = (
                    "当前信誉档案库中未找到游戏编号 "
                    + game_id
                    + "；不会自动创建档案"
                )

            elif len(subject_rows) > 1:
                error = (
                    "游戏编号 "
                    + game_id
                    + " 在当前 Workspace 中对应多个档案"
                )

        if error:
            row["action"] = "error"
            row["error"] = error
            row["subject_id"] = None
            row["subject_name"] = ""

            counts["error"] += 1

        else:
            subject = subject_rows[0]

            row["action"] = "create"

            row["subject_id"] = int(
                subject["id"]
            )

            row["subject_name"] = (
                subject["display_name"]
                or ""
            )

            row["error"] = ""

            counts["create"] += 1
            counts["matched"] += 1

        rows.append(row)

    return {
        "workspace_id":
            workspace_id,

        "battle_id":
            int(battle_id),

        "counts":
            counts,

        "rows":
            rows,
    }


def _validate_event_commit_rows(
    conn,
    battle_id,
    rows,
):
    workspace_id = (
        _workspace_id_for_battle(
            conn,
            battle_id,
        )
    )

    normalized = []

    seen = set()

    if not isinstance(
        rows,
        list,
    ):
        raise ValueError(
            "导入数据格式错误。"
        )

    if not rows:
        raise ValueError(
            "没有待导入事件。"
        )

    if len(rows) > _EVENT_IMPORT_MAX_ROWS:
        raise ValueError(
            "单次最多导入 500 行。"
        )

    for index, raw in enumerate(
        rows,
        1,
    ):
        if not isinstance(
            raw,
            dict,
        ):
            raise ValueError(
                "第 "
                + str(index)
                + " 行数据格式错误。"
            )

        title = _clean(
            raw.get(
                "title",
                "",
            )
        )

        game_id = _normalize_game_id(
            raw.get(
                "game_id",
                "",
            )
        )

        event_type, bad_type = (
            _normalize_event_choice(
                raw.get(
                    "event_type",
                    "",
                ),
                _EVENT_TYPE_MAP,
                "normal",
            )
        )

        impact_level, bad_impact = (
            _normalize_event_choice(
                raw.get(
                    "impact_level",
                    "",
                ),
                _EVENT_IMPACT_MAP,
                "low",
            )
        )

        status, bad_status = (
            _normalize_event_choice(
                raw.get(
                    "status",
                    "",
                ),
                _EVENT_STATUS_MAP,
                "recorded",
            )
        )

        if not title:
            raise ValueError(
                "事件标题不能为空。"
            )

        if not game_id:
            raise ValueError(
                "游戏编号不能为空。"
            )

        if (
            bad_type
            or bad_impact
            or bad_status
        ):
            raise ValueError(
                "导入数据包含不支持的枚举值。"
            )

        duplicate_key = (
            title.casefold(),
            _clean(
                raw.get(
                    "event_time",
                    "",
                )
            ).casefold(),
            game_id,
        )

        if duplicate_key in seen:
            raise ValueError(
                "确认数据中存在重复事件行。"
            )

        seen.add(
            duplicate_key
        )

        subject_rows = (
            _event_subject_rows(
                conn,
                workspace_id,
                game_id,
            )
        )

        if len(subject_rows) != 1:
            raise ValueError(
                "游戏编号 "
                + game_id
                + " 无法唯一匹配既有档案；"
                  "本次导入已取消。"
            )

        subject = subject_rows[0]

        normalized.append({
            "title":
                title,

            "game_id":
                game_id,

            "subject_id":
                int(
                    subject["id"]
                ),

            "subject_name":
                subject["display_name"]
                or "",

            "event_type":
                event_type,

            "impact_level":
                impact_level,

            "status":
                status,

            "event_time":
                _clean(
                    raw.get(
                        "event_time",
                        "",
                    )
                ),

            "summary":
                _clean(
                    raw.get(
                        "summary",
                        "",
                    )
                ),

            "evidence_note":
                _clean(
                    raw.get(
                        "evidence_note",
                        "",
                    )
                ),

            "relation_role":
                (
                    _clean(
                        raw.get(
                            "relation_role",
                            "",
                        )
                    )
                    or "关联对象"
                ),

            "relation_note":
                _clean(
                    raw.get(
                        "relation_note",
                        "",
                    )
                ),
        })

    return (
        workspace_id,
        normalized,
    )


def commit_event_rows(
    conn,
    battle_id,
    rows,
):
    conn.row_factory = __import__(
        "sqlite3"
    ).Row

    workspace_id, rows = (
        _validate_event_commit_rows(
            conn,
            battle_id,
            rows,
        )
    )

    created_event_ids = []

    conn.execute(
        "BEGIN IMMEDIATE"
    )

    try:
        for row in rows:
            cursor = conn.execute(
                """
                INSERT INTO v156_reputation_events (
                    workspace_id,
                    battle_id,
                    title,
                    event_type,
                    impact_level,
                    status,
                    event_time,
                    summary,
                    evidence_note,
                    created_at,
                    updated_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    datetime('now','localtime'),
                    datetime('now','localtime')
                )
                """,
                (
                    workspace_id,
                    int(battle_id),
                    row["title"],
                    row["event_type"],
                    row["impact_level"],
                    row["status"],
                    row["event_time"],
                    row["summary"],
                    row["evidence_note"],
                ),
            )

            event_id = int(
                cursor.lastrowid
            )

            relation = conn.execute(
                """
                INSERT INTO v156_reputation_event_relations (
                    workspace_id,
                    battle_id,
                    event_id,
                    subject_id,
                    relation_role,
                    note,
                    created_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?,
                    datetime('now','localtime')
                )
                """,
                (
                    workspace_id,
                    int(battle_id),
                    event_id,
                    row["subject_id"],
                    row["relation_role"],
                    row["relation_note"],
                ),
            )

            if (
                relation.lastrowid
                is None
            ):
                raise RuntimeError(
                    "事件关系写入失败。"
                )

            created_event_ids.append(
                event_id
            )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    return {
        "created":
            len(
                created_event_ids
            ),

        "event_ids":
            created_event_ids,
    }


def event_import_template_response():
    from flask import Response

    csv_text = (
        "\ufeff"
        "事件标题,游戏编号,事件类型,影响级别,状态,"
        "事件时间,摘要,证据备注,关联角色,关联备注\r\n"
        "示例事件,12345678,背刺 / 跳反,严重,记录中,"
        "2026-10-10,事件摘要,证据说明,关联对象,关系说明\r\n"
    )

    return Response(
        csv_text,
        mimetype="text/csv",
        headers={
            "Content-Disposition":
                "attachment; "
                "filename=reputation_event_import_template.csv"
        },
    )


def event_import_handler(
    conn,
    battle_id,
):
    from flask import (
        redirect,
        render_template,
        request,
        url_for,
    )
    import json

    conn.row_factory = __import__(
        "sqlite3"
    ).Row

    try:
        token = _csrf_token()

        if request.method == "GET":
            return render_template(
                "reputation_event_import.html",
                csrf_token=token,
                battle_id=battle_id,
                preview=None,
                rows_json="",
                error="",
            )

        if not _validate_csrf(
            request.form.get(
                "csrf_token",
                "",
            )
        ):
            return render_template(
                "reputation_event_import.html",
                csrf_token=token,
                battle_id=battle_id,
                preview=None,
                rows_json="",
                error="请求校验失败，请重新打开页面后再试。",
            ), 400

        action = _clean(
            request.form.get(
                "action",
                "",
            )
        )

        if action == "preview":
            uploaded = (
                request.files.get(
                    "import_file"
                )
            )

            if (
                uploaded is None
                or not uploaded.filename
            ):
                return render_template(
                    "reputation_event_import.html",
                    csrf_token=token,
                    battle_id=battle_id,
                    preview=None,
                    rows_json="",
                    error="请选择 CSV 文件。",
                ), 400

            if not (
                uploaded.filename.lower()
                .endswith(".csv")
            ):
                return render_template(
                    "reputation_event_import.html",
                    csrf_token=token,
                    battle_id=battle_id,
                    preview=None,
                    rows_json="",
                    error="当前版本仅支持 CSV 文件。",
                ), 400

            raw = uploaded.read(
                _EVENT_IMPORT_MAX_BYTES
                + 1
            )

            try:
                records = (
                    parse_event_csv_bytes(
                        raw
                    )
                )

                preview = (
                    build_event_preview(
                        conn,
                        battle_id,
                        records,
                    )
                )

            except ValueError as exc:
                return render_template(
                    "reputation_event_import.html",
                    csrf_token=token,
                    battle_id=battle_id,
                    preview=None,
                    rows_json="",
                    error=str(exc),
                ), 400

            rows_json = json.dumps(
                preview["rows"],
                ensure_ascii=False,
            )

            return render_template(
                "reputation_event_import.html",
                csrf_token=token,
                battle_id=battle_id,
                preview=preview,
                rows_json=rows_json,
                error="",
            )

        if action == "confirm":
            try:
                rows = json.loads(
                    request.form.get(
                        "rows_json",
                        "[]",
                    )
                )

                result = commit_event_rows(
                    conn,
                    battle_id,
                    rows,
                )

            except (
                ValueError,
                json.JSONDecodeError,
            ) as exc:
                return render_template(
                    "reputation_event_import.html",
                    csrf_token=token,
                    battle_id=battle_id,
                    preview=None,
                    rows_json="",
                    error=str(exc),
                ), 400

            return redirect(
                url_for(
                    "v156_reputation_events",
                    bulk_imported=result[
                        "created"
                    ],
                )
            )

        return render_template(
            "reputation_event_import.html",
            csrf_token=token,
            battle_id=battle_id,
            preview=None,
            rows_json="",
            error="不支持的操作。",
        ), 400

    finally:
        try:
            conn.close()
        except Exception:
            pass

