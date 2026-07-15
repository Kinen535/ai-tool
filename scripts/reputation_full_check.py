#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import subprocess
import sys
import re
from pathlib import Path


ROOT = Path("/home/admin/ai-tool")
EXPORT_ROOT = ROOT / "exports" / "reputation"

# V15.6-A32H full check app import path
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# V15.6-A34 full check safe output scrub
def scrub_output(text: str) -> str:
    text = text.replace(str(ROOT), "[PROJECT_ROOT]")
    text = text.replace("/home/admin", "[HOME]")
    text = text.replace("exports/reputation", "[EXPORT_DIR]")
    text = re.sub(r"reputation_export_\d{8}-\d{6}(?:\.zip)?", "reputation_export_[hidden]", text)
    text = re.sub(r"token=[A-Za-z0-9_\-\.]+", "token=[hidden]", text)
    return text


def run(cmd: list[str], title: str) -> None:
    print("=" * 70)
    print(title)
    print("=" * 70)

    result = subprocess.run(
        cmd,
        cwd=str(ROOT),
        text=True,
        capture_output=True,
    )

    if result.stdout:
        print(scrub_output(result.stdout), end="" if result.stdout.endswith("\n") else "\n")

    if result.stderr:
        print(scrub_output(result.stderr), end="" if result.stderr.endswith("\n") else "\n")

    if result.returncode != 0:
        raise SystemExit(f"❌ 失败：{title}")




# V15.6-A35 reputation home security check
def check_reputation_home_security() -> None:
    from app import app

    with app.test_client() as c:
        r = c.get("/reputation")
        html = r.data.decode("utf-8", errors="ignore")

        if r.status_code != 200:
            raise SystemExit("❌ 信誉档案库首页访问失败")

        required = [
            "信誉档案",
            "安全备份",
            "维护页已保护",
            "今日处理重点",
            "未关联事件",
            "待核实事件",
            "证据链完整率",
            "风险处置工作台",
        ]

        forbidden = [
            "/reputation/backup-status",
            "token=",
            "security_admin_token",
            "/home/admin",
            "exports/reputation",
            "python3 scripts/",
            "reputation_export_",
        ]

        for key in required:
            if key not in html:
                raise SystemExit(f"❌ 信誉档案库首页缺少必要内容：{key}")

        for key in forbidden:
            if key in html:
                raise SystemExit(f"❌ 信誉档案库首页暴露敏感内容：{key}")

    print("✅ 信誉档案库首页安全检查通过：维护入口未暴露")


# V15.6-A32G backup status sensitive content check
def check_backup_status_security() -> None:
    from app import app

    token_path = ROOT / "data" / "security_admin_token.txt"
    token = token_path.read_text(encoding="utf-8").strip() if token_path.exists() else ""

    with app.test_client() as c:
        r1 = c.get("/reputation/backup-status")
        if r1.status_code != 404:
            raise SystemExit("❌ 备份状态页无 token 访问未拦截")

        r2 = c.get("/reputation/backup-status", headers={"X-Admin-Token": token})
        html = r2.data.decode("utf-8", errors="ignore")

        if r2.status_code != 200:
            raise SystemExit("❌ 备份状态页 token 访问失败")

        required = [
            "信誉档案库安全备份",
            "最近一次安全备份",
            "维护命令已隐藏",
        ]

        forbidden = [
            "/home/admin",
            "exports/reputation",
            "python3 scripts/",
            "reputation_export_",
            "security_admin_token",
            "backup_reputation.py",
            "reputation_full_check.py",
            "cleanup_reputation_exports.py",
        ]

        for key in required:
            if key not in html:
                raise SystemExit(f"❌ 备份状态页缺少必要内容：{key}")

        for key in forbidden:
            if key in html:
                raise SystemExit(f"❌ 备份状态页暴露敏感内容：{key}")

    print("✅ 备份状态页安全检查通过：无 token 拦截，敏感内容未暴露")


def latest_zip() -> Path | None:
    zips = sorted(EXPORT_ROOT.glob("reputation_export_*.zip"))
    return zips[-1] if zips else None



# V15.6-A38D reputation list chinese visible check
def check_reputation_list_chinese_visible() -> None:
    from app import app
    import re

    pages = [
        "/reputation/subjects",
        "/reputation/events",
        "/reputation/duplicates",
    ]

    forbidden_visible = [
        "black",
        "danger",
        "severe",
        "recorded",
        "pending",
        "disputed",
        "verified",
        "voided",
        "archived",
    ]

    def visible_text(html: str) -> str:
        html = re.sub(r"<script[\s\S]*?</script>", "", html, flags=re.I)
        html = re.sub(r"<style[\s\S]*?</style>", "", html, flags=re.I)
        html = re.sub(r"<[^>]+>", " ", html)
        return re.sub(r"\s+", " ", html)

    with app.test_client() as c:
        combined = ""

        for url in pages:
            r = c.get(url)
            html = r.data.decode("utf-8", errors="ignore")
            text = visible_text(html)
            combined += "\n" + text

            if r.status_code != 200:
                raise SystemExit(f"❌ 列表页访问失败：{url}")

            for key in forbidden_visible:
                if key in text:
                    raise SystemExit(f"❌ 列表页可见文字仍出现英文状态：{url} -> {key}")

        for key in ["黑名单", "严重"]:
            if key not in combined:
                raise SystemExit(f"❌ 列表页缺少中文状态：{key}")

    print("✅ 列表页中文化检查通过：可见文字未发现英文状态")


# V15.6-A39 reputation detail chinese visible check
def check_reputation_detail_chinese_visible() -> None:
    from app import app
    import re

    pages = [
        "/reputation/subjects/8",
        "/reputation/events/3",
        "/reputation/search?q=315789798",
    ]

    forbidden_visible = [
        "black",
        "danger",
        "severe",
        "recorded",
        "pending",
        "disputed",
        "verified",
        "voided",
        "archived",
    ]

    def visible_text(html: str) -> str:
        html = re.sub(r"<script[\s\S]*?</script>", "", html, flags=re.I)
        html = re.sub(r"<style[\s\S]*?</style>", "", html, flags=re.I)
        html = re.sub(r"<[^>]+>", " ", html)
        return re.sub(r"\s+", " ", html)

    with app.test_client() as c:
        combined = ""

        for url in pages:
            r = c.get(url)
            html = r.data.decode("utf-8", errors="ignore")
            text = visible_text(html)
            combined += "\n" + text

            if r.status_code != 200:
                raise SystemExit(f"❌ 详情/检索页访问失败：{url}")

            for key in forbidden_visible:
                if key in text:
                    raise SystemExit(f"❌ 详情/检索页可见文字仍出现英文状态：{url} -> {key}")

        for key in [
            "证据链",
            "严重",
            "处置建议",
            "建议级别",
            "影响评估",
            "评估结论",
            "检索风险结论",
            "风险结论",
            "综合风险研判",
            "综合风险等级",
            "主体当前结论",
            "主要判断依据",
            "证据缺口",
            "建议管理动作",
        ]:
            if key not in combined:
                raise SystemExit(f"❌ 详情/检索页缺少中文关键内容：{key}")

    print("✅ 详情页与检索页中文化检查通过：可见文字未发现英文状态")


# V15.6-A40 reputation core page security check
def check_reputation_core_pages_security() -> None:
    from app import app

    pages = [
        "/reputation",
        "/reputation/workbench",
        "/reputation/tasks",
        "/reputation/search",
        "/reputation/search?q=315789798",
        "/reputation/subjects",
        "/reputation/subjects/new",
        "/reputation/subjects/8",
        "/reputation/subjects/8/edit",
        "/reputation/events",
        "/reputation/events/new",
        "/reputation/events/3",
        "/reputation/events/3/edit",
        "/reputation/duplicates",
        "/reputation/merge-logs",
    ]

    forbidden = [
        "/home/admin",
        "reputation_export_",
        "token=",
        "security_admin_token",
        "/reputation/backup-status",
        "python3 scripts/",
    ]

    with app.test_client() as c:
        for url in pages:
            r = c.get(url)
            html = r.data.decode("utf-8", errors="ignore")

            if r.status_code != 200:
                raise SystemExit(f"❌ 信誉档案库核心页面异常：{url} -> {r.status_code}")

            # V15.7-A6 workbench core check
            if url == "/reputation/workbench":
                required_workbench = [
                    "信誉风险处置工作台",
                    "待处理总数",
                    "P1 紧急",
                    "P2 重点",
                    "P3 待完善",
                    "紧急处置",
                    "重点复核",
                    "待完善",
                    "风险原因",
                    "证据状态",
                    "推荐动作",
                    "处理入口",
                ]

                for required_key in required_workbench:
                    if required_key not in html:
                        raise SystemExit(
                            "❌ 风险处置工作台缺少必要内容："
                            f"{required_key}"
                        )

            # V15.7-A7-4C reputation task page check
            if url == "/reputation/tasks":
                required_tasks = [
                    "信誉风险处置任务",
                    "任务闭环概况",
                    "任务总数",
                    "未闭环",
                    "处置任务列表",
                    "保存更新",
                    "处置结果",
                ]

                for required_key in required_tasks:
                    if required_key not in html:
                        raise SystemExit(
                            "❌ 处置任务页面缺少必要内容："
                            f"{required_key}"
                        )

            for key in forbidden:
                if key in html:
                    raise SystemExit(f"❌ 信誉档案库核心页面暴露敏感内容：{url} -> {key}")

    print("✅ 核心页面巡检通过：页面可访问，未发现敏感内容")


# V15.7-A6B workbench return context check
def check_reputation_workbench_return_context() -> None:
    import sqlite3

    import services.v156_reputation_store as store
    from app import app

    conn = sqlite3.connect("data/snapshots.db")

    subject_row = conn.execute(
        """
        SELECT id
        FROM v156_reputation_subjects
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()

    event_row = conn.execute(
        """
        SELECT id
        FROM v156_reputation_events
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()

    conn.close()

    if not subject_row or not event_row:
        raise SystemExit(
            "❌ 工作台上下文检查缺少测试主体或测试事件"
        )

    subject_id = int(subject_row[0])
    event_id = int(event_row[0])

    return_query = (
        "return_to=%2Freputation%2Fworkbench"
    )

    pages = [
        (
            f"/reputation/subjects/{subject_id}"
            f"?{return_query}",
            "主体详情",
            0,
        ),
        (
            f"/reputation/subjects/{subject_id}/edit"
            f"?{return_query}",
            "主体编辑",
            1,
        ),
        (
            f"/reputation/events/{event_id}"
            f"?{return_query}",
            "事件详情",
            0,
        ),
        (
            f"/reputation/events/{event_id}/edit"
            f"?{return_query}",
            "事件编辑",
            3,
        ),
    ]

    with app.test_client() as client:
        workbench_response = client.get(
            "/reputation/workbench"
        )

        workbench_html = (
            workbench_response.data.decode(
                "utf-8",
                errors="ignore",
            )
        )

        if workbench_response.status_code != 200:
            raise SystemExit(
                "❌ 风险处置工作台访问失败"
            )

        if return_query not in workbench_html:
            raise SystemExit(
                "❌ 工作台处理链接缺少返回上下文"
            )

        for url, label, expected_hidden in pages:
            response = client.get(url)

            html = response.data.decode(
                "utf-8",
                errors="ignore",
            )

            if response.status_code != 200:
                raise SystemExit(
                    f"❌ {label}页面访问失败"
                )

            if "返回风险处置工作台" not in html:
                raise SystemExit(
                    f"❌ {label}缺少返回工作台按钮"
                )

            actual_hidden = html.count(
                'name="return_to"'
            )

            if actual_hidden != expected_hidden:
                raise SystemExit(
                    f"❌ {label}返回字段数量异常："
                    f"预期 {expected_hidden}，"
                    f"实际 {actual_hidden}"
                )

        unsafe_response = client.get(
            f"/reputation/subjects/{subject_id}"
            "?return_to=https://example.invalid"
        )

        unsafe_html = unsafe_response.data.decode(
            "utf-8",
            errors="ignore",
        )

        if "https://example.invalid" in unsafe_html:
            raise SystemExit(
                "❌ 外部返回地址被输出到页面"
            )

        if "返回风险处置工作台" in unsafe_html:
            raise SystemExit(
                "❌ 非法返回地址被误认为工作台来源"
            )

        original_add = (
            store.add_reputation_event_relation
        )
        original_delete = (
            store.delete_reputation_event_relation
        )

        try:
            store.add_reputation_event_relation = (
                lambda *args, **kwargs: True
            )

            store.delete_reputation_event_relation = (
                lambda *args, **kwargs: True
            )

            save_response = client.post(
                f"/reputation/events/{event_id}"
                "/relations/save",
                data={
                    "subject_id": "0",
                    "relation_role": "",
                    "note": "",
                    "return_to": (
                        "/reputation/workbench"
                    ),
                },
                follow_redirects=False,
            )

            delete_response = client.post(
                f"/reputation/events/{event_id}"
                "/relations/999999/delete",
                data={
                    "return_to": (
                        "/reputation/workbench"
                    ),
                },
                follow_redirects=False,
            )

        finally:
            store.add_reputation_event_relation = (
                original_add
            )

            store.delete_reputation_event_relation = (
                original_delete
            )

        expected_redirect = (
            "return_to=%2Freputation%2Fworkbench"
        )

        for label, response in [
            ("添加关联", save_response),
            ("删除关联", delete_response),
        ]:
            location = response.headers.get(
                "Location",
                "",
            )

            if response.status_code not in (301, 302, 303):
                raise SystemExit(
                    f"❌ {label}没有正常重定向"
                )

            if expected_redirect not in location:
                raise SystemExit(
                    f"❌ {label}后丢失工作台上下文"
                )

            if "#relations" not in location:
                raise SystemExit(
                    f"❌ {label}后没有返回关联区域"
                )

    print(
        "✅ 工作台上下文返回检查通过："
        "详情、编辑、关联操作与安全限制均正常"
    )



# V15.7-A7-4C reputation task lifecycle check
def check_reputation_task_lifecycle() -> None:
    import shutil
    import sqlite3
    import tempfile
    import uuid
    from pathlib import Path

    import services.v156_reputation_store as store
    from app import app

    root = Path(__file__).resolve().parents[1]
    source_db = root / "data" / "snapshots.db"

    if not source_db.exists():
        raise SystemExit(
            "❌ 任务生命周期检查缺少正式数据库"
        )

    def clone_row(
        conn,
        table,
        source_row,
        overrides,
    ):
        columns = [
            row["name"]
            for row in conn.execute(
                f"PRAGMA table_info({table})"
            ).fetchall()
            if row["name"] != "id"
        ]

        values = []

        for column in columns:
            if column in overrides:
                values.append(
                    overrides[column]
                )
            else:
                values.append(
                    source_row[column]
                )

        placeholders = ",".join(
            ["?"] * len(columns)
        )

        column_sql = ",".join(columns)

        cursor = conn.execute(
            f"""
            INSERT INTO {table} (
                {column_sql}
            )
            VALUES (
                {placeholders}
            )
            """,
            tuple(values),
        )

        return int(cursor.lastrowid)

    with tempfile.TemporaryDirectory() as tmp:
        temp_db = (
            Path(tmp)
            / "reputation_task_check.db"
        )

        shutil.copy2(
            source_db,
            temp_db,
        )

        conn = sqlite3.connect(
            str(temp_db)
        )
        conn.row_factory = sqlite3.Row

        store.ensure_reputation_tables(conn)

        source_subject = conn.execute(
            """
            SELECT *
            FROM v156_reputation_subjects
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

        source_event = conn.execute(
            """
            SELECT *
            FROM v156_reputation_events
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

        if not source_subject:
            conn.close()
            raise SystemExit(
                "❌ 任务生命周期检查缺少测试主体"
            )

        if not source_event:
            conn.close()
            raise SystemExit(
                "❌ 任务生命周期检查缺少测试事件"
            )

        token = uuid.uuid4().hex[:12]

        subject_id = clone_row(
            conn,
            "v156_reputation_subjects",
            source_subject,
            {
                "display_name": (
                    f"A7全链路测试主体-{token}"
                ),
                "game_id": (
                    f"A7-{token}"
                ),
                "trust_level": "black",
                "risk_level": "black",
                "status": "active",
            },
        )

        event_id = clone_row(
            conn,
            "v156_reputation_events",
            source_event,
            {
                "title": (
                    f"A7全链路测试事件-{token}"
                ),
            },
        )

        conn.commit()

        created = (
            store.create_reputation_task_from_workbench(
                conn,
                entity_type="subject",
                entity_id=subject_id,
            )
        )

        if not created.get("ok"):
            conn.close()
            raise SystemExit(
                "❌ 工作台创建处置任务失败："
                f"{created}"
            )

        subject_task_id = int(
            created["task_id"]
        )

        subject_task = store.get_reputation_task(
            conn,
            subject_task_id,
        )

        if not subject_task:
            conn.close()
            raise SystemExit(
                "❌ 创建后无法读取主体任务"
            )

        if not (
            subject_task["task_reason"]
            and subject_task[
                "recommended_action"
            ]
        ):
            conn.close()
            raise SystemExit(
                "❌ 工作台任务缺少风险原因"
                "或推荐动作快照"
            )

        duplicate = (
            store.create_reputation_task_from_workbench(
                conn,
                entity_type="subject",
                entity_id=subject_id,
            )
        )

        if not duplicate.get("duplicate"):
            conn.close()
            raise SystemExit(
                "❌ 同一对象的重复未闭环任务"
                "没有被拦截"
            )

        processing = store.update_reputation_task(
            conn,
            subject_task_id,
            {
                "priority": "P1",
                "status": "processing",
                "owner": "A7全链路检查",
                "result_note": "",
            },
        )

        if not processing.get("ok"):
            conn.close()
            raise SystemExit(
                "❌ 任务无法进入处理中状态"
            )

        processing_row = processing["task"]

        if (
            processing_row["status"]
            != "processing"
            or processing_row["owner"]
            != "A7全链路检查"
            or processing_row["completed_at"]
        ):
            conn.close()
            raise SystemExit(
                "❌ 处理中任务字段状态异常"
            )

        missing_result = (
            store.update_reputation_task(
                conn,
                subject_task_id,
                {
                    "priority": "P1",
                    "status": "completed",
                    "owner": "A7全链路检查",
                    "result_note": "",
                },
            )
        )

        if not missing_result.get(
            "result_required"
        ):
            conn.close()
            raise SystemExit(
                "❌ 空处置结果的闭环请求"
                "没有被拦截"
            )

        completed = store.update_reputation_task(
            conn,
            subject_task_id,
            {
                "priority": "P1",
                "status": "completed",
                "owner": "A7全链路检查",
                "result_note": (
                    "全链路检查完成，"
                    "主体任务闭环正常。"
                ),
            },
        )

        if not completed.get("ok"):
            conn.close()
            raise SystemExit(
                "❌ 主体任务无法完成闭环"
            )

        completed_row = completed["task"]

        if (
            completed_row["status"]
            != "completed"
            or not completed_row["result_note"]
            or not completed_row["completed_at"]
        ):
            conn.close()
            raise SystemExit(
                "❌ 已完成主体任务缺少"
                "结果或闭环时间"
            )

        next_cycle = (
            store.create_reputation_task_from_workbench(
                conn,
                entity_type="subject",
                entity_id=subject_id,
            )
        )

        if not next_cycle.get("ok"):
            conn.close()
            raise SystemExit(
                "❌ 已闭环对象无法创建"
                "新一轮处置任务"
            )

        next_cycle_id = int(
            next_cycle["task_id"]
        )

        ignored_cycle = (
            store.update_reputation_task(
                conn,
                next_cycle_id,
                {
                    "priority": "P1",
                    "status": "ignored",
                    "owner": "A7全链路检查",
                    "result_note": (
                        "新一轮任务用于验证"
                        "忽略状态闭环。"
                    ),
                },
            )
        )

        if not ignored_cycle.get("ok"):
            conn.close()
            raise SystemExit(
                "❌ 新一轮主体任务"
                "无法忽略闭环"
            )

        event_task = store.create_reputation_task(
            conn,
            {
                "entity_type": "event",
                "entity_id": event_id,
                "priority": "P2",
                "task_reason": (
                    "全链路测试事件需要复核"
                ),
                "recommended_action": (
                    "核查事件证据并形成结论"
                ),
                "source_type": "full_check",
            },
        )

        if not event_task.get("ok"):
            conn.close()
            raise SystemExit(
                "❌ 事件处置任务创建失败"
            )

        event_task_id = int(
            event_task["task_id"]
        )

        event_closed = (
            store.update_reputation_task(
                conn,
                event_task_id,
                {
                    "priority": "P2",
                    "status": "completed",
                    "owner": "A7全链路检查",
                    "result_note": (
                        "事件任务闭环检查正常。"
                    ),
                },
            )
        )

        if not event_closed.get("ok"):
            conn.close()
            raise SystemExit(
                "❌ 事件处置任务无法闭环"
            )

        active_map = (
            store.get_active_reputation_task_map(
                conn
            )
        )

        if (
            ("subject", subject_id)
            in active_map
            or ("event", event_id)
            in active_map
        ):
            conn.close()
            raise SystemExit(
                "❌ 已闭环测试任务仍被识别"
                "为活动任务"
            )

        conn.close()

    original_create = (
        store.create_reputation_task_from_workbench
    )

    original_update = (
        store.update_reputation_task
    )

    try:
        store.create_reputation_task_from_workbench = (
            lambda *args, **kwargs: {
                "ok": True,
                "task_id": 901,
            }
        )

        store.update_reputation_task = (
            lambda *args, **kwargs: {
                "ok": True,
            }
        )

        with app.test_client() as client:
            create_response = client.post(
                "/reputation/tasks/create",
                data={
                    "entity_type": "subject",
                    "entity_id": "8",
                },
                follow_redirects=False,
            )

            create_location = (
                create_response.headers.get(
                    "Location",
                    "",
                )
            )

            if create_response.status_code != 302:
                raise SystemExit(
                    "❌ 创建任务路由没有重定向"
                )

            if (
                "task_result=created"
                not in create_location
                or "task_id=901"
                not in create_location
            ):
                raise SystemExit(
                    "❌ 创建任务路由结果参数异常"
                )

            update_response = client.post(
                "/reputation/tasks/901/update",
                data={
                    "priority": "P1",
                    "status": "processing",
                    "owner": "A7全链路检查",
                    "result_note": "",
                    "return_status": "pending",
                    "return_priority": "P1",
                    "return_q": "测试",
                },
                follow_redirects=False,
            )

            update_location = (
                update_response.headers.get(
                    "Location",
                    "",
                )
            )

            if update_response.status_code != 302:
                raise SystemExit(
                    "❌ 更新任务路由没有重定向"
                )

            if (
                "task_result=updated"
                not in update_location
                or "#task-901"
                not in update_location
            ):
                raise SystemExit(
                    "❌ 更新任务路由结果参数异常"
                )

        store.update_reputation_task = (
            lambda *args, **kwargs: {
                "ok": False,
                "result_required": True,
            }
        )

        with app.test_client() as client:
            required_response = client.post(
                "/reputation/tasks/901/update",
                data={
                    "priority": "P1",
                    "status": "completed",
                    "owner": "A7全链路检查",
                    "result_note": "",
                },
                follow_redirects=False,
            )

            required_location = (
                required_response.headers.get(
                    "Location",
                    "",
                )
            )

            if (
                required_response.status_code != 302
                or "task_result=result_required"
                not in required_location
            ):
                raise SystemExit(
                    "❌ 闭环结果必填路由映射异常"
                )

    finally:
        store.create_reputation_task_from_workbench = (
            original_create
        )

        store.update_reputation_task = (
            original_update
        )

    print(
        "✅ 处置任务全生命周期检查通过："
        "创建、重复拦截、处理中、"
        "结果必填、完成、忽略、"
        "新周期和路由均正常"
    )

def main() -> int:
    print("V15.7 Reputation Full Chain Check")
    print("=" * 70)

    run(
        [
            sys.executable,
            "-m",
            "py_compile",
            "app.py",
            "services/v156_reputation_store.py",
            "scripts/reputation_smoke_test.py",
            "scripts/reputation_health_check.py",
            "scripts/export_reputation_csv.py",
            "scripts/verify_reputation_export.py",
            "scripts/backup_reputation.py",
            "scripts/preview_reputation_restore.py",
            "scripts/reputation_full_check.py",
        ],
        "Step 1/9：Python 语法编译检查",
    )

    run(
        [sys.executable, "scripts/reputation_smoke_test.py"],
        "Step 2/9：信誉档案库页面烟测",
    )

    print("=" * 70)
    print("Step 3/9：信誉档案库首页安全检查")
    print("=" * 70)
    check_reputation_home_security()

    print("=" * 70)
    print("Step 4/9：备份状态页安全检查")
    print("=" * 70)
    check_backup_status_security()

    print("=" * 70)
    print("列表页中文化检查")
    print("=" * 70)
    check_reputation_list_chinese_visible()

    print("=" * 70)
    print("详情页与检索页中文化检查")
    print("=" * 70)
    check_reputation_detail_chinese_visible()

    print("=" * 70)
    print("核心页面巡检")
    print("=" * 70)
    check_reputation_core_pages_security()

    print("=" * 70)
    print("工作台上下文返回检查")
    print("=" * 70)
    check_reputation_workbench_return_context()

    print("=" * 70)
    print("Step 5/9：处置任务全生命周期检查")
    print("=" * 70)
    check_reputation_task_lifecycle()

    run(
        [sys.executable, "scripts/reputation_health_check.py"],
        "Step 6/9：信誉档案库数据体检",
    )

    run(
        [sys.executable, "scripts/backup_reputation.py"],
        "Step 7/9：一键备份导出",
    )

    zip_path = latest_zip()

    if not zip_path:
        raise SystemExit("❌ 没有找到最新 ZIP 备份包")

    run(
        [sys.executable, "scripts/verify_reputation_export.py", str(zip_path)],
        "Step 8/9：ZIP 备份包校验",
    )

    run(
        [sys.executable, "scripts/preview_reputation_restore.py", str(zip_path)],
        "Step 9/9：恢复前预检",
    )

    print("=" * 70)
    print("✅ V15.7 信誉档案库全链路自检通过")
    print(f"✅ 最新备份包：{scrub_output(str(zip_path))}")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
