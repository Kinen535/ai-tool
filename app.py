from __future__ import annotations
from services.ai_engine import (
    classify_player,
    calculate_ai_risk
)
from services.staff_engine import build_staff_report
from services.talent_engine import (
    build_member_strategy
)

from pathlib import Path
from datetime import datetime
import io
import json
import re
import sqlite3
import traceback

DB_PATH = "data/snapshots.db"

import pandas as pd
from flask import Flask, flash, redirect, render_template, request, send_file, url_for

print("🔥🔥🔥 app.py 稳定版已加载！🔥🔥🔥")

# =========================
# 基础配置
# =========================
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
SNAPSHOT_DIR = BASE_DIR / "snapshots"
DATA_DIR.mkdir(exist_ok=True)
SNAPSHOT_DIR.mkdir(exist_ok=True)

COMPARE_RESULT_FILE = DATA_DIR / "compare_result.csv"
GROUP_SUMMARY_FILE = DATA_DIR / "group_summary.csv"
ADVICE_FILE = DATA_DIR / "advice.json"
DB_FILE = DATA_DIR / "snapshots.db"

HIGH_POWER = 35000
MID_POWER = 25000
HIGH_BATTLE_MIN = 50000
MID_BATTLE_MIN = 30000
CORE_BATTLE_MIN = 100000

app = Flask(__name__)
app.secret_key = "alliance-manager-v9-stable"

snapshot_cache: dict[str, pd.DataFrame] = {}

compare_page_cache = {}
trends_cache = {}

# =========================
# 通用工具
# =========================
def safe_int(value, default: int = 0) -> int:
    try:
        if pd.isna(value):
            return default
        return int(float(value))
    except Exception:
        return default


def empty_advice() -> dict:
    return {"清理名单": [], "警告名单": [], "核心成员": [], "未执行名单": []}


def read_csv_path(path: Path) -> pd.DataFrame:
    for enc in ("utf-8-sig", "gbk", "utf-8"):
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception:
            pass
    return pd.read_csv(path)


def read_csv_flexible(file_storage) -> pd.DataFrame:
    for enc in ("utf-8-sig", "gbk", "utf-8"):
        try:
            file_storage.stream.seek(0)
            return pd.read_csv(file_storage, encoding=enc)
        except Exception:
            pass
    file_storage.stream.seek(0)
    return pd.read_csv(file_storage)


def normalize_snapshot_time(snapshot_time: str) -> str:
    safe_time = str(snapshot_time).split(".")[0]
    safe_time = safe_time.replace("T", " ")
    safe_time = safe_time.replace(":", "-").replace(" ", "_")
    return safe_time


# =========================
# 数据库
# =========================
def get_conn():
    conn = sqlite3.connect(DB_FILE, timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout = 15000;")
    return conn


def init_db():

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 原快照表
    cur.execute("""
    CREATE TABLE IF NOT EXISTS snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        snapshot_time TEXT,
        data TEXT,
        source_filename TEXT,
        created_at TEXT
    )
    """)

    # 玩家历史记录表
    cur.execute("""
    CREATE TABLE IF NOT EXISTS player_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,

        snapshot_time TEXT,
        source_filename TEXT,

        member TEXT,
        group_name TEXT,

        battle_total INTEGER,
        assist_total INTEGER,
        donate_total INTEGER,
        power_value INTEGER,
        power_total INTEGER,

        created_at TEXT
    )
    """)

    # 赛季管理表
    cur.execute("""
    CREATE TABLE IF NOT EXISTS seasons (
        id INTEGER PRIMARY KEY AUTOINCREMENT,

        season_code TEXT,
        season_name TEXT,
        script_type TEXT,

        is_current INTEGER DEFAULT 0,
        created_at TEXT
    )
    """)

    # =========================
    # snapshots 增加 battle_id
    # =========================

    try:
        cur.execute("""
            ALTER TABLE snapshots
            ADD COLUMN battle_id INTEGER DEFAULT 1
        """)
    except sqlite3.OperationalError:
        pass

    # 给旧 snapshots 表补赛季字段
    try:
        cur.execute("ALTER TABLE snapshots ADD COLUMN season_code TEXT DEFAULT 'S24'")
    except sqlite3.OperationalError:
        pass

    try:
        cur.execute("ALTER TABLE snapshots ADD COLUMN season_name TEXT DEFAULT '九州剧本'")
    except sqlite3.OperationalError:
        pass

    # 给旧 player_records 表补赛季字段
    try:
        cur.execute("ALTER TABLE player_records ADD COLUMN season_code TEXT DEFAULT 'S24'")
    except sqlite3.OperationalError:
        pass

    try:
        cur.execute("ALTER TABLE player_records ADD COLUMN season_name TEXT DEFAULT '九州剧本'")
    except sqlite3.OperationalError:
        pass

    cur.execute("""
    CREATE TABLE IF NOT EXISTS battles (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        battle_name TEXT,

        script_type TEXT,

        alliance_name TEXT,

        is_current INTEGER DEFAULT 0,

        created_at TEXT

    )
    """)        

    # 初始化当前赛季
    cur.execute("""
    INSERT INTO seasons (
        season_code,
        season_name,
        script_type,
        is_current,
        created_at
    )
    SELECT
        'S24',
        '九州剧本',
        'jiuzhou',
        1,
        datetime('now')
    WHERE NOT EXISTS (
        SELECT 1 FROM seasons WHERE season_code = 'S24'
    )
    """)

    # 查询性能索引
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_member
    ON player_records(member)
    """)

    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_snapshot_time
    ON player_records(snapshot_time)
    """)

    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_player_records_season
    ON player_records(season_code)
    """)

    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_snapshots_season
    ON snapshots(season_code)
    """)

    conn.commit()
    conn.close()

    print("✅ 数据库初始化完成")


def list_snapshot_times() -> list[str]:

    conn = get_conn()

    try:

        battle_row = conn.execute("""
            SELECT id
            FROM battles
            WHERE is_current = 1
            LIMIT 1
        """).fetchone()

        battle_id = (
            battle_row["id"]
            if battle_row
            else 1
        )

        rows = conn.execute(
            """
            SELECT snapshot_time
            FROM snapshots
            WHERE battle_id = ?
            AND is_deleted = 0
            ORDER BY snapshot_time DESC
            """,
            (battle_id,)
        ).fetchall()

        print(
            f"📦 当前战场快照数: {len(rows)} "
            f"(battle_id={battle_id})"
        )

        return [
            r["snapshot_time"]
            for r in rows
        ]

    finally:

        conn.close()

def load_current_battle_members() -> pd.DataFrame:

    conn = get_conn()

    battle_row = conn.execute("""
        SELECT id
        FROM battles
        WHERE is_current = 1
        LIMIT 1
    """).fetchone()

    if not battle_row:
        conn.close()
        return pd.DataFrame()

    battle_id = battle_row["id"]

    snapshot_row = conn.execute("""
        SELECT snapshot_time
        FROM snapshots
        WHERE battle_id = ?
        ORDER BY id DESC
        LIMIT 1
    """, (battle_id,)).fetchone()

    conn.close()

    if not snapshot_row:
        return pd.DataFrame()

    try:
        return load_snapshot_df(
            snapshot_row["snapshot_time"],
            battle_id
        )
    except Exception as e:
        print("❌ 读取战场成员失败:", e)
        return pd.DataFrame()


# =========================
# 快照导入和读取
# =========================
def extract_snapshot_time(filename: str) -> str:
    if not filename:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    name = str(filename)
    patterns = [
        r"(\d{4}年\d{2}月\d{2}日\d{2}时\d{2}分\d{2}秒)",
        r"(\d{4}-\d{2}-\d{2}[ _]\d{2}[:\-]\d{2}[:\-]\d{2})",
        r"(\d{4}-\d{2}-\d{2}[ _]\d{2}[:\-]\d{2})",
        r"(\d{4}年\d{2}月\d{2}日\d{2}时\d{2}分)",
    ]

    for pattern in patterns:
        m = re.search(pattern, name)
        if m:
            raw = m.group(1)
            raw = raw.replace("年", "-").replace("月", "-").replace("日", " ")
            raw = raw.replace("时", ":").replace("分", ":").replace("秒", "")
            raw = raw.replace("_", " ")
            parts = raw.split(" ")
            if len(parts) == 2:
                date_part = parts[0]
                time_part = parts[1].replace("-", ":")
                if len(time_part.split(":")) == 2:
                    time_part += ":00"
                return f"{date_part} {time_part}"

    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_game_csv(file_storage) -> pd.DataFrame:
    df = read_csv_flexible(file_storage)
    df.columns = [str(c).strip() for c in df.columns]

    print("📊 原始列名:", df.columns.tolist())

    if "成员" not in df.columns:
        unnamed_cols = [c for c in df.columns if "Unnamed" in str(c)]
        if unnamed_cols:
            df = df.rename(columns={unnamed_cols[0]: "成员"})

    if "门阀" in df.columns and "分组" not in df.columns:
        df["分组"] = df["门阀"]

    required = [
        "成员", "贡献排行", "贡献本周", "战功本周", "助攻本周", "捐献本周",
        "贡献总量", "战功总量", "助攻总量", "捐献总量", "势力值", "所属州", "分组",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"周表缺少字段：{', '.join(missing)}")

    numeric_cols = [
        "贡献排行", "贡献本周", "战功本周", "助攻本周", "捐献本周",
        "贡献总量", "战功总量", "助攻总量", "捐献总量", "势力值",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    df["成员"] = df["成员"].astype(str).fillna("").str.strip()
    df["所属州"] = df["所属州"].astype(str).fillna("").str.strip()
    df["分组"] = df["分组"].astype(str).fillna("").str.strip()
    df["power"] = df["势力值"].astype(int)

    print("✅ 清洗后行数:", len(df))
    return df

def save_snapshot(df: pd.DataFrame, snapshot_time: str, source_filename: str = "") -> bool:

    conn = None

    try:

        payload_json = json.dumps(
            df.to_dict(orient="records"),
            ensure_ascii=False
        )

        conn = get_conn()
        cur = conn.cursor()

        # =========================
        # 当前战场ID
        # =========================

        battle_row = cur.execute(
            """
            SELECT id
            FROM battles
            WHERE is_current = 1
            LIMIT 1
            """
        ).fetchone()

        battle_id = battle_row["id"] if battle_row else 1

        # =========================
        # 检查有效快照
        # =========================

        active_snapshot = cur.execute(
            """
            SELECT id
            FROM snapshots
            WHERE snapshot_time = ?
            AND battle_id = ?
            AND is_deleted = 0
            """,
            (
                snapshot_time,
                battle_id
            )
        ).fetchone()

        if active_snapshot:

            print(
                f"⚠️ 已存在该时间快照，跳过写入: {snapshot_time}"
            )

            return False

        # =========================
        # 检查已删除快照
        # =========================

        deleted_snapshot = cur.execute(
            """
            SELECT id
            FROM snapshots
            WHERE snapshot_time = ?
            AND battle_id = ?
            AND is_deleted = 1
            """,
            (
                snapshot_time,
                battle_id
            )
        ).fetchone()

        if deleted_snapshot:

            print(
                f"♻️ 恢复已删除快照: {snapshot_time}"
            )

            cur.execute(
                """
                UPDATE snapshots
                SET
                    is_deleted = 0,
                    data = ?,
                    source_filename = ?,
                    created_at = ?
                WHERE id = ?
                """,
                (
                    payload_json,
                    source_filename,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    deleted_snapshot["id"]
                )
            )

            cur.execute(
                """
                UPDATE player_records
                SET is_deleted = 0
                WHERE snapshot_time = ?
                AND battle_id = ?
                """,
                (
                    snapshot_time,
                    battle_id
                )
            )

            conn.commit()

            print(
                f"✅ 已恢复快照: {snapshot_time}"
            )

            return True

        # =========================
        # 保存原始 JSON 快照
        # =========================

        cur.execute(
            """
            INSERT INTO snapshots (

                snapshot_time,
                data,
                source_filename,
                battle_id,
                created_at

            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (

                snapshot_time,
                payload_json,
                source_filename,
                battle_id,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            ),
        )

        # =========================
        # 展开玩家数据
        # =========================

        for _, row in df.iterrows():

            try:

                member = str(
                    row.get("成员", "")
                ).strip()

                group_name = str(
                    row.get("分组", "")
                ).strip()

                battle_total = int(
                    float(row.get("战功总量", 0) or 0)
                )

                assist_total = int(
                    float(row.get("助攻总量", 0) or 0)
                )

                donate_total = int(
                    float(row.get("捐献总量", 0) or 0)
                )

                power_value = int(
                    float(row.get("势力值", 0) or 0)
                )

                previous_record = get_previous_player_record(
                    member,
                    snapshot_time,
                    battle_id
                )

                if previous_record:

                    battle_gain = (
                        battle_total -
                        previous_record["battle_total"]
                    )

                    assist_gain = (
                        assist_total -
                        previous_record["assist_total"]
                    )

                    donate_gain = (
                        donate_total -
                        previous_record["donate_total"]
                    )

                    power_gain = (
                        power_value -
                        previous_record["power_value"]
                    )

                else:

                    battle_gain = 0
                    assist_gain = 0
                    donate_gain = 0
                    power_gain = 0

                cur.execute(
                    """
                    INSERT INTO player_records (

                        snapshot_time,
                        source_filename,
                        battle_id,

                        member,
                        group_name,

                        battle_total,
                        assist_total,
                        donate_total,
                        power_value,

                        battle_gain,
                        assist_gain,
                        donate_gain,
                        power_gain
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot_time,
                        source_filename,
                        battle_id,

                        member,
                        group_name,

                        battle_total,
                        assist_total,
                        donate_total,
                        power_value,

                        battle_gain,
                        assist_gain,
                        donate_gain,
                        power_gain

                    )
                )

            except Exception as e:

                print(
                    "❌ 玩家展开失败:",
                    e
                )

        conn.commit()

        # =========================
        # CSV 文件备份
        # =========================

        safe_time = normalize_snapshot_time(
            snapshot_time
        )

        file_path = (
            SNAPSHOT_DIR /
            f"battle_{battle_id}_{safe_time}.csv"
        )

        df.to_csv(
            file_path,
            index=False,
            encoding="utf-8-sig"
        )

        print(
            f"📁 CSV 已保存: {file_path}"
        )

        print(
            f"✅ 快照已保存: {snapshot_time}, "
            f"文件: {source_filename}, "
            f"行数: {len(df)}"
        )

        print(
            f"✅ 玩家记录展开完成: {len(df)}"
        )

        return True

    except Exception as e:

        print(
            "❌ save_snapshot 出错:",
            str(e)
        )

        traceback.print_exc()

        if conn is not None:
            conn.rollback()

        raise

    finally:

        if conn is not None:
            conn.close()


def get_previous_player_record(
    member_name: str,
    snapshot_time: str,
    battle_id: int
):

    conn = get_conn()

    try:

        row = conn.execute(
            """
            SELECT

                battle_total,
                assist_total,
                donate_total,
                power_value

            FROM player_records

            WHERE member = ?
            AND battle_id = ?
            AND snapshot_time < ?

            ORDER BY snapshot_time DESC

            LIMIT 1
            """,
            (
                member_name,
                battle_id,
                snapshot_time
            )
        ).fetchone()

        return row

    finally:

        conn.close()

def rebuild_gain(battle_id: int):

    conn = get_conn()

    try:
        rows = conn.execute(
            """
            SELECT
                id,
                member,
                snapshot_time,
                battle_total,
                assist_total,
                donate_total,
                power_value
            FROM player_records
            WHERE battle_id = ?
            AND is_deleted = 0
            ORDER BY member ASC, snapshot_time ASC
            """,
            (battle_id,)
        ).fetchall()

        last_map = {}
        updated_count = 0

        for row in rows:
            member = row["member"]

            if member not in last_map:
                battle_gain = 0
                assist_gain = 0
                donate_gain = 0
                power_gain = 0
            else:

                last = last_map[member]

                battle_now = row["battle_total"] or 0
                battle_old = last["battle_total"] or 0

                assist_now = row["assist_total"] or 0
                assist_old = last["assist_total"] or 0

                donate_now = row["donate_total"] or 0
                donate_old = last["donate_total"] or 0

                power_now = row["power_value"] or 0
                power_old = last["power_value"] or 0

                battle_gain = battle_now - battle_old
                assist_gain = assist_now - assist_old
                donate_gain = donate_now - donate_old
                power_gain = power_now - power_old

            conn.execute(
                """
                UPDATE player_records
                SET
                    battle_gain = ?,
                    assist_gain = ?,
                    donate_gain = ?,
                    power_gain = ?
                WHERE id = ?
                """,
                (
                    battle_gain,
                    assist_gain,
                    donate_gain,
                    power_gain,
                    row["id"]
                )
            )

            last_map[member] = row
            updated_count += 1

        conn.commit()

        print(f"✅ rebuild_gain 完成：battle_id={battle_id}, 更新 {updated_count} 条")

        return updated_count

    except Exception as e:
        conn.rollback()
        print("❌ rebuild_gain 出错:", e)
        traceback.print_exc()
        raise

    finally:
        conn.close()

def sync_member_profiles(
    battle_id: int,
    snapshot_time: str
):

    conn = get_conn()

    try:

        rows = conn.execute(
            """
            SELECT
                member,
                av,
                bs,
                trend,
                risk_level,
                risk_reason
            FROM player_records
            WHERE battle_id = ?
            AND snapshot_time = ?
            AND is_deleted = 0
            """,
            (
                battle_id,
                snapshot_time
            )
        ).fetchall()

        updated_count = 0

        for row in rows:

            member_name = row["member"]

            exists = conn.execute(
                """
                SELECT
                    id
                FROM member_profiles
                WHERE member_name = ?
                """,
                (
                    member_name,
                )
            ).fetchone()

            if exists:

                conn.execute(
                    """
                    UPDATE member_profiles
                    SET

                        av = ?,
                        bs = ?,
                        trend = ?,
                        risk_level = ?,
                        risk_reason = ?,
                        last_seen = ?

                    WHERE member_name = ?
                    """,
                    (
                        row["av"] or 0,
                        row["bs"] or 0,
                        row["trend"] or "stable",
                        row["risk_level"] or "safe",
                        row["risk_reason"] or "",
                        snapshot_time,
                        member_name
                    )
                )

            else:

                conn.execute(
                    """
                    INSERT INTO member_profiles (

                        member_name,
                        av,
                        bs,
                        trend,
                        risk_level,
                        risk_reason,

                        role_tag,
                        identity_score,
                        is_protected,

                        first_seen,
                        last_seen,
                        created_at

                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        member_name,
                        row["av"] or 0,
                        row["bs"] or 0,
                        row["trend"] or "stable",
                        row["risk_level"] or "safe",
                        row["risk_reason"] or "",

                        "member",
                        0,
                        0,

                        snapshot_time,
                        snapshot_time,
                        datetime.now().strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                    )
                )

            updated_count += 1

        conn.commit()

        print(
            f"👤 MemberProfile同步完成: "
            f"{updated_count} 条"
        )

        return updated_count

    except Exception as e:

        conn.rollback()

        print(
            "❌ sync_member_profiles 出错:",
            e
        )

        traceback.print_exc()

        raise

    finally:

        conn.close()        


def calculate_wv(
    battle_id: int,
    snapshot_time: str
):

    conn = get_conn()

    try:

        rows = conn.execute(
            """
            SELECT
                id,
                battle_gain,
                assist_gain
            FROM player_records
            WHERE battle_id = ?
            AND snapshot_time = ?
            AND is_deleted = 0
            """,
            (
                battle_id,
                snapshot_time
            )
        ).fetchall()

        if not rows:
            return 0

        battle_list = sorted(
            [r["battle_gain"] or 0 for r in rows]
        )

        assist_list = sorted(
            [r["assist_gain"] or 0 for r in rows]
        )

        updated_count = 0

        for row in rows:

            battle_gain = row["battle_gain"] or 0
            assist_gain = row["assist_gain"] or 0

            battle_rank = (
                battle_list.index(battle_gain) + 1
            )

            assist_rank = (
                assist_list.index(assist_gain) + 1
            )

            battle_percentile = (
                battle_rank /
                len(battle_list)
            ) * 100

            assist_percentile = (
                assist_rank /
                len(assist_list)
            ) * 100

            wv = (
                battle_percentile * 0.7
                +
                assist_percentile * 0.3
            )

            conn.execute(
                """
                UPDATE player_records
                SET wv = ?
                WHERE id = ?
                """,
                (
                    round(wv, 2),
                    row["id"]
                )
            )

            updated_count += 1

        conn.commit()

        print(
            f"⚔️ WV计算完成: "
            f"{snapshot_time} "
            f"更新 {updated_count} 条"
        )

        return updated_count

    except Exception as e:

        conn.rollback()

        print(
            "❌ calculate_wv 出错:",
            e
        )

        traceback.print_exc()

        raise

    finally:

        conn.close()

def calculate_identity_score(
    battle_id: int,
    snapshot_time: str
):

    conn = get_conn()

    try:

        rows = conn.execute(
            """
            SELECT
                member_name,
                av,
                bs,
                trend,
                risk_level,
                role_tag,
                is_protected,
                exempt_stall
            FROM member_profiles
            """
        ).fetchall()

        updated_count = 0

        for row in rows:

            score = 0

            role_tag = row["role_tag"] or "member"

            # =====================
            # 基础表现分
            # =====================

            score += min(
                40,
                (row["bs"] or 0) * 0.4
            )

            score += min(
                25,
                (row["av"] or 0) * 0.25
            )

            trend = row["trend"] or "stable"

            if trend == "explosive":

                score += 15

            elif trend == "up":

                score += 10

            elif trend == "stable":

                score += 5

            risk = row["risk_level"] or ""

            if risk == "protected":

                score += 15

            elif risk == "safe":

                score += 10

            elif risk == "warning":

                score += 5

            # =====================
            # 身份加成
            # =====================

            if role_tag == "admin":

                score += 30

            elif role_tag == "warehouse":

                score += 25

            elif role_tag == "core":

                score += 20

            if row["is_protected"] == 1:

                score += 10

            if row["exempt_stall"] == 1:

                score += 5

            # =====================
            # 特殊身份保底
            # =====================

            if role_tag == "admin":

                score = max(
                    score,
                    90
                )

            elif role_tag == "warehouse":

                score = max(
                    score,
                    80
                )

            elif role_tag == "core":

                score = max(
                    score,
                    85
                )

            elif row["is_protected"] == 1:

                score = max(
                    score,
                    75
                )

            score = min(
                100,
                round(score, 1)
            )

            conn.execute(
                """
                UPDATE member_profiles
                SET identity_score = ?
                WHERE member_name = ?
                """,
                (
                    score,
                    row["member_name"]
                )
            )

            conn.execute(
                """
                INSERT OR REPLACE INTO identity_history (

                    member_name,
                    snapshot_time,

                    av,
                    bs,

                    trend,
                    risk_level,

                    identity_score,

                    created_at

                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, datetime('now')
                )
                """,
                (
                    row["member_name"],
                    snapshot_time,

                    row["av"] or 0,
                    row["bs"] or 0,

                    row["trend"] or "stable",
                    row["risk_level"] or "safe",

                    score
                )
            )

            updated_count += 1

        conn.commit()

        print(
            f"🏅 IdentityScore完成: "
            f"{updated_count} 条"
        )

        return updated_count

    finally:

        conn.close()


def sync_identity(
    battle_id: int,
    snapshot_time: str
):

    conn = get_conn()

    try:

        rows = conn.execute(
            """
            SELECT
                member_name,
                role_tag,
                role_desc,
                role_rule,
                role_weight,
                identity_score,
                is_protected,
                exempt_stall
            FROM member_profiles
            """
        ).fetchall()

        updated_count = 0

        for row in rows:

            conn.execute(
                """
                UPDATE player_records
                SET

                    role_tag = ?,
                    role_desc = ?,
                    role_rule = ?,
                    role_weight = ?,

                    identity_score = ?,
                    is_protected = ?,
                    exempt_stall = ?
                WHERE battle_id = ?
                AND snapshot_time = ?
                AND member = ?
                """,
                (
                    row["role_tag"] or "member",
                    row["role_desc"] or "",
                    row["role_rule"] or "normal",
                    row["role_weight"] or 1,

                    row["identity_score"] or 0,
                    row["is_protected"] or 0,
                    row["exempt_stall"] or 0,

                    battle_id,
                    snapshot_time,
                    row["member_name"]
                )
            )

            updated_count += 1

        conn.commit()

        print(
            f"🛡 Identity同步完成: "
            f"{updated_count} 条"
        )

        return updated_count

    except Exception as e:

        conn.rollback()

        print(
            "❌ sync_identity 出错:",
            e
        )

        traceback.print_exc()

        raise

    finally:

        conn.close()



def calculate_bv(
    battle_id: int,
    snapshot_time: str
):

    conn = get_conn()

    try:

        rows = conn.execute(
            """
            SELECT
                id,
                donate_gain,
                power_gain
            FROM player_records
            WHERE battle_id = ?
            AND snapshot_time = ?
            AND is_deleted = 0
            """,
            (
                battle_id,
                snapshot_time
            )
        ).fetchall()

        if not rows:
            return 0

        donate_list = sorted(
            [r["donate_gain"] or 0 for r in rows]
        )

        power_list = sorted(
            [r["power_gain"] or 0 for r in rows]
        )

        updated_count = 0

        for row in rows:

            donate_gain = row["donate_gain"] or 0
            power_gain = row["power_gain"] or 0

            donate_rank = (
                donate_list.index(donate_gain) + 1
            )

            power_rank = (
                power_list.index(power_gain) + 1
            )

            donate_percentile = (
                donate_rank /
                len(donate_list)
            ) * 100

            power_percentile = (
                power_rank /
                len(power_list)
            ) * 100

            bv = (
                donate_percentile * 0.6
                +
                power_percentile * 0.4
            )

            conn.execute(
                """
                UPDATE player_records
                SET bv = ?
                WHERE id = ?
                """,
                (
                    round(bv, 2),
                    row["id"]
                )
            )

            updated_count += 1

        conn.commit()

        print(
            f"🏗️ BV计算完成: "
            f"{snapshot_time} "
            f"更新 {updated_count} 条"
        )

        return updated_count

    except Exception as e:

        conn.rollback()

        print(
            "❌ calculate_bv 出错:",
            e
        )

        traceback.print_exc()

        raise

    finally:

        conn.close()

def calculate_av(
    battle_id: int,
    snapshot_time: str
):

    conn = get_conn()

    try:

        rows = conn.execute(
            """
            SELECT
                id,
                wv,
                bv
            FROM player_records
            WHERE battle_id = ?
            AND snapshot_time = ?
            AND is_deleted = 0
            """,
            (
                battle_id,
                snapshot_time
            )
        ).fetchall()

        if not rows:
            return 0

        updated_count = 0

        for row in rows:

            wv = row["wv"] or 0
            bv = row["bv"] or 0

            av = (
                wv * 0.4
                +
                bv * 0.6
            )

            conn.execute(
                """
                UPDATE player_records
                SET av = ?
                WHERE id = ?
                """,
                (
                    round(av, 2),
                    row["id"]
                )
            )

            updated_count += 1

        conn.commit()

        print(
            f"🔥 AV计算完成: "
            f"{snapshot_time} "
            f"更新 {updated_count} 条"
        )

        return updated_count

    except Exception as e:

        conn.rollback()

        print(
            "❌ calculate_av 出错:",
            e
        )

        traceback.print_exc()

        raise

    finally:

        conn.close()

def calculate_trend(
    battle_id: int,
    snapshot_time: str
):

    conn = get_conn()

    try:

        current_rows = conn.execute(
            """
            SELECT
                id,
                member
            FROM player_records
            WHERE battle_id = ?
            AND snapshot_time = ?
            AND is_deleted = 0
            """,
            (
                battle_id,
                snapshot_time
            )
        ).fetchall()

        updated_count = 0

        for current in current_rows:

            member = current["member"]

            history = conn.execute(
                """
                SELECT
                    battle_gain,
                    assist_gain
                FROM player_records
                WHERE battle_id = ?
                AND member = ?
                AND is_deleted = 0
                ORDER BY snapshot_time DESC
                LIMIT 10
                """,
                (
                    battle_id,
                    member
                )
            ).fetchall()

            if len(history) < 5:

                trend = "stable"
                trend_score = 60

            else:

                values = []

                for h in reversed(history):

                    battle_gain = h["battle_gain"] or 0
                    assist_gain = h["assist_gain"] or 0

                    values.append(
                        battle_gain
                        +
                        assist_gain * 2
                    )

                half = len(values) // 2

                old_avg = (
                    sum(values[:half])
                    /
                    max(1, len(values[:half]))
                )

                new_avg = (
                    sum(values[half:])
                    /
                    max(1, len(values[half:]))
                )

                if old_avg <= 0:

                    ratio = 1

                else:

                    ratio = (
                        new_avg
                        /
                        old_avg
                    )

                if max(values) < 100:

                    trend = "dead"
                    trend_score = 0

                elif new_avg < 500:

                    if ratio >= 2:

                        trend = "up"
                        trend_score = 80

                    elif ratio >= 0.8:

                        trend = "stable"
                        trend_score = 60

                    else:

                        trend = "down"
                        trend_score = 30

                else:

                    if ratio >= 2:

                        trend = "explosive"
                        trend_score = 100

                    elif ratio >= 1.2:

                        trend = "up"
                        trend_score = 80

                    elif ratio >= 0.8:

                        trend = "stable"
                        trend_score = 60

                    elif ratio >= 0.3:

                        trend = "down"
                        trend_score = 30

                    else:

                        trend = "dead"
                        trend_score = 0

            conn.execute(
                """
                UPDATE player_records
                SET

                    trend = ?,
                    trend_score = ?

                WHERE id = ?
                """,
                (
                    trend,
                    trend_score,
                    current["id"]
                )
            )

            updated_count += 1

        conn.commit()

        print(
            f"📈 Trend计算完成: "
            f"{snapshot_time} "
            f"更新 {updated_count} 条"
        )

        return updated_count

    except Exception as e:

        conn.rollback()

        print(
            "❌ calculate_trend 出错:",
            e
        )

        traceback.print_exc()

        raise

    finally:

        conn.close()


def calculate_bs(
    battle_id: int,
    snapshot_time: str
):

    conn = get_conn()

    try:

        rows = conn.execute(
            """
            SELECT
                id,
                av,
                wv,
                bv,
                trend_score
            FROM player_records
            WHERE battle_id = ?
            AND snapshot_time = ?
            AND is_deleted = 0
            """,
            (
                battle_id,
                snapshot_time
            )
        ).fetchall()

        updated_count = 0

        for row in rows:

            av = row["av"] or 0
            wv = row["wv"] or 0
            bv = row["bv"] or 0
            trend_score = row["trend_score"] or 0

            bs = (

                av * 0.40

                +

                wv * 0.25

                +

                bv * 0.15

                +

                trend_score * 0.20

            )

            conn.execute(
                """
                UPDATE player_records
                SET bs = ?
                WHERE id = ?
                """,
                (
                    round(bs, 2),
                    row["id"]
                )
            )

            updated_count += 1

        conn.commit()

        print(
            f"🏆 BS计算完成: "
            f"{snapshot_time} "
            f"更新 {updated_count} 条"
        )

        return updated_count

    except Exception as e:

        conn.rollback()

        print(
            "❌ calculate_bs 出错:",
            e
        )

        traceback.print_exc()

        raise

    finally:

        conn.close()        

def calculate_risk(
    battle_id: int,
    snapshot_time: str
):

    conn = get_conn()

    try:

        rows = conn.execute(
            """
            SELECT
                id,
                member,
                av,
                bs,
                trend,
                stall_count
            FROM player_records
            WHERE battle_id = ?
            AND snapshot_time = ?
            AND is_deleted = 0
            """,
            (
                battle_id,
                snapshot_time
            )
        ).fetchall()

        updated_count = 0

        for row in rows:

            member = row["member"]
            profile = conn.execute(
                """
                SELECT
                    is_protected,
                    role_tag,
                    role_weight,
                    exempt_stall
                FROM member_profiles
                WHERE member_name = ?
                """,
                (
                    member,
                )
            ).fetchone()

            if (
                profile
                and
                profile["is_protected"] == 1
            ):

                conn.execute(
                    """
                    UPDATE player_records
                    SET
                        risk_level = 'protected'
                    WHERE id = ?
                    """,
                    (
                        row["id"],
                    )
                )

                updated_count += 1

                continue

            av = row["av"] or 0
            bs = row["bs"] or 0
            trend = row["trend"] or "stable"
            stall_count = row["stall_count"] or 0

            role_weight = 1
            role_tag = "member"
            exempt_stall = 0

            if profile:

                role_tag = (
                    profile["role_tag"]
                    or "member"
                )

                role_weight = (
                    profile["role_weight"]
                    or 1
                )

                exempt_stall = (
                    profile["exempt_stall"]
                    or 0
                )
            reasons = []

            risk_score = 0

            # =====================
            # BS
            # =====================

            risk_score += bs * 0.5 * role_weight

            # =====================
            # 核心成员加成
            # =====================

            if role_tag == "core":

                risk_score += 5

                reasons.append(
                    "核心成员加成"
                )

            # =====================
            # AV
            # =====================

            risk_score += av * 0.2 * role_weight

            # =====================
            # Trend
            # =====================

            if trend == "explosive":

                risk_score += 20
                reasons.append("高速成长")

            elif trend == "up":

                risk_score += 10

            elif trend == "stable":

                risk_score += 0

            elif trend == "down":

                risk_score -= 10
                reasons.append("持续下滑")

            elif trend == "dead":

                risk_score -= 20
                reasons.append("长期停滞")

            # =====================
            # Stall
            # =====================

            if exempt_stall == 1:

                reasons.append(
                    "身份免停滞"
                )

            else:

                risk_score -= stall_count * 3

                if stall_count >= 2:

                    reasons.append(
                        f"连续停滞{stall_count}期"
                    )

            # =====================
            # 风险等级
            # =====================

            if role_tag == "admin":

                risk_level = "safe"

                reasons.append(
                    "管理员保护"
                )

            elif role_tag == "warehouse":

                risk_level = "safe"

                reasons.append(
                    "仓库号保护"
                )

            else:

                if risk_score >= 50:

                    risk_level = "safe"

                elif risk_score >= 30:

                    risk_level = "warning"

                elif risk_score >= 10:

                    risk_level = "danger"

                else:

                    risk_level = "clear"

            # =====================
            # 额外标签
            # =====================

            if bs < 20:

                reasons.append(
                    "长期低贡献"
                )

            if av < 20:

                reasons.append(
                    "活跃不足"
                )

            # 风险等级补充原因

            if risk_level == "danger":

                reasons.append(
                    f"综合健康分过低({round(risk_score,1)})"
                )

            elif risk_level == "warning":

                reasons.append(
                    f"综合健康分偏低({round(risk_score,1)})"
                )

            # 去重

            reasons = list(
                dict.fromkeys(reasons)
            )

            risk_reason = "｜".join(
                reasons
            )

            conn.execute(
                """
                UPDATE player_records
                SET
                    risk_level = ?,
                    risk_reason = ?
                WHERE id = ?
                """,
                (
                    risk_level,
                    risk_reason,
                    row["id"]
                )
            )

            updated_count += 1

        conn.commit()

        print(
            f"🚨 Risk计算完成: "
            f"{snapshot_time} "
            f"更新 {updated_count} 条"
        )

        return updated_count

    except Exception as e:

        conn.rollback()

        print(
            "❌ calculate_risk 出错:",
            e
        )

        traceback.print_exc()

        raise

    finally:

        conn.close()

def calculate_stall(
    battle_id: int,
    snapshot_time: str
):

    conn = get_conn()

    try:

        rows = conn.execute(
            """
            SELECT
                id,
                member
            FROM player_records
            WHERE battle_id = ?
            AND snapshot_time = ?
            AND is_deleted = 0
            """,
            (
                battle_id,
                snapshot_time
            )
        ).fetchall()

        updated_count = 0

        current_time = datetime.strptime(
            snapshot_time,
            "%Y-%m-%d %H:%M:%S"
        )

        for row in rows:

            member = row["member"]

            profile = conn.execute(
                """
                SELECT
                    exempt_stall
                FROM member_profiles
                WHERE member_name = ?
                """,
                (
                   member,
                )
            ).fetchone()

            if (
               profile
               and
               profile["exempt_stall"] == 1
            ):

               conn.execute(
                   """
                   UPDATE player_records
                   SET
                       stall_count = 0
                   WHERE id = ?
                   """,
                   (
                       row["id"],
                   )
               )

               updated_count += 1

               continue

            previous = conn.execute(
                """
                SELECT
                    stall_count
                FROM player_records
                WHERE battle_id = ?
                AND member = ?
                AND snapshot_time < ?
                AND is_deleted = 0
                ORDER BY snapshot_time DESC
                LIMIT 1
                """,
                (
                    battle_id,
                    member,
                    snapshot_time
                )
            ).fetchone()

            previous_stall = (
                previous["stall_count"]
                if previous
                else 0
            )

            history = conn.execute(
                """
                SELECT
                    snapshot_time,
                    battle_gain,
                    assist_gain,
                    power_gain,
                    donate_gain
                FROM player_records
                WHERE battle_id = ?
                AND member = ?
                AND snapshot_time <= ?
                AND is_deleted = 0
                ORDER BY snapshot_time DESC
                LIMIT 3
                """,
                (
                    battle_id,
                    member,
                    snapshot_time
                )
            ).fetchall()

            active = False
            last_active_time = None

            for h in history:

                gain_active = (
                    (h["battle_gain"] or 0) > 0
                    or
                    (h["assist_gain"] or 0) > 0
                    or
                    (h["power_gain"] or 0) > 0
                    or
                    (h["donate_gain"] or 0) > 0
                )

                if gain_active:

                    active = True

                    last_active_time = datetime.strptime(
                        h["snapshot_time"],
                        "%Y-%m-%d %H:%M:%S"
                    )

                    break

            if active:

                stall_count = 0

            elif last_active_time:

                hours_gap = (
                    current_time
                    -
                    last_active_time
                ).total_seconds() / 3600

                if hours_gap < 6:

                    stall_count = previous_stall

                else:

                    stall_count = previous_stall + 1

            else:

                stall_count = previous_stall + 1

            conn.execute(
                """
                UPDATE player_records
                SET
                    stall_count = ?
                WHERE id = ?
                """,
                (
                    stall_count,
                    row["id"]
                )
            )

            updated_count += 1

        conn.commit()

        print(
            f"⏸ Stall计算完成: "
            f"{snapshot_time} "
            f"更新 {updated_count} 条"
        )

        return updated_count

    except Exception as e:

        conn.rollback()

        print(
            "❌ calculate_stall 出错:",
            e
        )

        traceback.print_exc()

        raise

    finally:

        conn.close()

        

def calculate_stall_penalty(
    battle_id: int,
    snapshot_time: str
):

    conn = get_conn()

    try:

        rows = conn.execute(
            """
            SELECT
                id,
                bs,
                stall_count
            FROM player_records
            WHERE battle_id = ?
            AND snapshot_time = ?
            AND is_deleted = 0
            """,
            (
                battle_id,
                snapshot_time
            )
        ).fetchall()

        updated_count = 0

        for row in rows:

            bs = row["bs"] or 0
            stall_count = row["stall_count"] or 0

            if stall_count >= 8:

                penalty = 20

            elif stall_count >= 5:

                penalty = 10

            elif stall_count >= 3:

                penalty = 5

            else:

                penalty = 0

            final_bs = max(
                0,
                bs - penalty
            )

            conn.execute(
                """
                UPDATE player_records
                SET
                    stall_penalty = ?,
                    bs = ?
                WHERE id = ?
                """,
                (
                    penalty,
                    final_bs,
                    row["id"]
                )
            )

            updated_count += 1

        conn.commit()

        print(
            f"⏸️ StallPenalty完成: "
            f"{snapshot_time} "
            f"更新 {updated_count} 条"
        )

        return updated_count

    except Exception as e:

        conn.rollback()

        print(
            "❌ calculate_stall_penalty 出错:",
            e
        )

        traceback.print_exc()

        raise

    finally:

        conn.close()        


def process_snapshot_pipeline(
    snapshot_time: str
):

    try:

        conn = get_conn()

        battle_row = conn.execute("""
            SELECT id
            FROM battles
            WHERE is_current = 1
            LIMIT 1
        """).fetchone()

        battle_id = (
            battle_row["id"]
            if battle_row
            else 1
        )

        print(
            f"🚀 Pipeline启动: "
            f"{snapshot_time}"
        )

        rebuild_gain(
            battle_id
        )
   
        calculate_wv(
            battle_id,
            snapshot_time
        )

        calculate_bv(
            battle_id,
            snapshot_time
        )

        calculate_av(
            battle_id,
            snapshot_time
        )

        calculate_trend(
            battle_id,
            snapshot_time
        )

        calculate_bs(
            battle_id,
            snapshot_time
        )

        calculate_stall(
            battle_id,
            snapshot_time
        )

        calculate_stall_penalty(
            battle_id,
            snapshot_time
        )

        calculate_risk(
            battle_id,
            snapshot_time
        )

        sync_member_profiles(
           battle_id,
           snapshot_time
        )

        calculate_identity_score(
            battle_id,
            snapshot_time
        )

        sync_identity(
            battle_id,
            snapshot_time
        )

        print(
            f"✅ Pipeline完成: "
            f"{snapshot_time}"
        )

    except Exception as e:

        print(
            "❌ Pipeline失败:",
            str(e)
        )

        traceback.print_exc()

    finally:

        try:
            conn.close()
        except:
            pass         

def load_snapshot_df(snapshot_time: str, battle_id: int | None = None) -> pd.DataFrame:

    safe_time = normalize_snapshot_time(snapshot_time)

    conn = get_conn()

    try:

        # =========================
        # 确定战场ID
        # =========================
        if battle_id is None:

            battle_row = conn.execute("""
                SELECT id
                FROM battles
                WHERE is_current = 1
                LIMIT 1
            """).fetchone()

            battle_id = (
                battle_row["id"]
                if battle_row
                else 1
            )

        # =========================
        # 缓存隔离
        # =========================
        cache_key = f"battle_{battle_id}_{safe_time}"

        if cache_key in snapshot_cache:
            print("⚡ 使用缓存:", cache_key)
            return snapshot_cache[cache_key].copy()

        # =========================
        # 优先从数据库读取
        # =========================
        row = conn.execute(
            """
            SELECT data
            FROM snapshots
            WHERE snapshot_time = ?
            AND battle_id = ?
            """,
            (
                snapshot_time,
                battle_id
            )
        ).fetchone()

        if row:

            print(
                f"📦 从数据库 JSON 恢复快照: {snapshot_time} "
                f"(battle_id={battle_id})"
            )

            data = json.loads(row["data"])
            df = pd.DataFrame(data)

            snapshot_cache[cache_key] = df

            # =========================
            # CSV 仅作为战场隔离备份
            # =========================
            csv_path = SNAPSHOT_DIR / f"battle_{battle_id}_{safe_time}.csv"

            try:
                df.to_csv(
                    csv_path,
                    index=False,
                    encoding="utf-8-sig"
                )
            except Exception:
                pass

            return df.copy()

    finally:

        conn.close()

    raise ValueError(
        f"找不到对应快照：{snapshot_time}，battle_id={battle_id}"
    )

def compare_snapshots(df_old: pd.DataFrame, df_new: pd.DataFrame):

    conn = get_conn()

    df = pd.merge(df_old, df_new, on="成员", how="outer", suffixes=("_old", "_new")).fillna(0)

    result_columns = [
        "成员", "分组", "所属州", "势力值", "贡献排行",
        "战功本周", "助攻本周", "捐献本周", "战功总量", "助攻总量", "捐献总量",
        "战功增长", "助攻增长", "捐献增长", "势力增长", "执行状态", "违规", "状态", "建议",
        "评分", "风险原因", "分类", "优先类别", "优先级排名",
    ]

    if df.empty:
        return pd.DataFrame(columns=result_columns), pd.DataFrame(columns=["分组", "人数"]), empty_advice()

    for col in ["战功总量", "助攻总量", "捐献总量", "势力值"]:
        for suffix in ["_old", "_new"]:
            full_col = f"{col}{suffix}"
            if full_col not in df.columns:
                df[full_col] = 0

    df["战功增长"] = pd.to_numeric(df["战功总量_new"], errors="coerce").fillna(0) - pd.to_numeric(df["战功总量_old"], errors="coerce").fillna(0)
    df["助攻增长"] = pd.to_numeric(df["助攻总量_new"], errors="coerce").fillna(0) - pd.to_numeric(df["助攻总量_old"], errors="coerce").fillna(0)
    df["捐献增长"] = pd.to_numeric(df["捐献总量_new"], errors="coerce").fillna(0) - pd.to_numeric(df["捐献总量_old"], errors="coerce").fillna(0)
    df["势力增长"] = pd.to_numeric(df["势力值_new"], errors="coerce").fillna(0) - pd.to_numeric(df["势力值_old"], errors="coerce").fillna(0)

    avg_power = pd.to_numeric(df["势力值_new"], errors="coerce").fillna(0).mean()
    avg_power = 0 if pd.isna(avg_power) else avg_power

    result_rows = []
    for _, row in df.iterrows():
        name = str(row.get("成员", "")).strip()
        team_name = str(row.get("分组_new", row.get("分组_old", ""))).strip()
        state_name = str(row.get("所属州_new", row.get("所属州_old", ""))).strip()

        power_value = safe_int(row.get("势力值_new", 0))
        contribution_rank = safe_int(row.get("贡献排行_new", 0))
        battle_week = safe_int(row.get("战功本周_new", 0))
        assist_week = safe_int(row.get("助攻本周_new", 0))
        donate_week = safe_int(row.get("捐献本周_new", 0))

        war_growth = safe_int(row.get("战功增长", 0))
        assist_growth = safe_int(row.get("助攻增长", 0))
        donate_growth = safe_int(row.get("捐献增长", 0))
        power_growth = safe_int(row.get("势力增长", 0))

        if war_growth == 0 and assist_growth == 0 and power_growth == 0 and donate_growth == 0:
            exec_status = "完全摆烂"
        elif war_growth > 5000:
            exec_status = "主力打架"
        elif assist_growth > 1000:
            exec_status = "参与攻城"
        elif power_growth > 3000:
            exec_status = "打地发育"
        elif donate_growth > 100:
            exec_status = "仅捐献"
        else:
            exec_status = "低活跃"

        violation = "正常"
        if power_value == 0:
            violation = "成员消失"
        if power_growth > 5000 and assist_growth == 0 and war_growth < 5000:
            violation = "疑似偷地"
        elif war_growth == 0 and assist_growth == 0 and power_growth == 0 and donate_growth == 0:
            violation = "未执行"
        elif war_growth < 3000 and assist_growth < 300 and power_growth <= 0:
            violation = "低活跃"

        growth_score = 100 if power_growth > 20000 else 85 if power_growth > 10000 else 75 if power_growth > 5000 else 60 if power_growth > 0 else 40 if power_growth > -2000 else 20
        execution_score = 100 if exec_status == "主力打架" else 90 if exec_status == "参与攻城" else 75 if exec_status == "打地发育" else 55 if exec_status == "仅捐献" else 40 if exec_status == "低活跃" else 20

        if avg_power == 0:
            power_score = 50
        else:
            ratio = power_value / avg_power
            power_score = 100 if ratio > 1.5 else 85 if ratio > 1.2 else 70 if ratio > 1.0 else 55 if ratio > 0.8 else 35

        behavior_raw = war_growth + assist_growth * 2 + donate_growth * 0.2
        behavior_score = 100 if behavior_raw > 20000 else 85 if behavior_raw > 10000 else 70 if behavior_raw > 5000 else 55 if behavior_raw > 1000 else 40 if behavior_raw > 0 else 20

        base_score = int(growth_score * 0.30 + execution_score * 0.30 + power_score * 0.20 + behavior_score * 0.20)

        # =====================
        # 身份加成
        # =====================

        profile = conn.execute(
            """
            SELECT
                role_tag,
                is_protected,
                exempt_stall
            FROM member_profiles
            WHERE member_name = ?
            """,
            (
               name,
            )
        ).fetchone()

        role_tag = "member"

        is_protected = 0

        if profile:

            role_tag = (
                profile["role_tag"]
                or "member"
            )

            is_protected = (
                profile["is_protected"]
                or 0
            )

        # 管理员

        if role_tag == "admin":

           base_score += 30

        # 仓库号

        elif role_tag == "warehouse":

            base_score += 20

        # 核心成员

        elif role_tag == "core":

            base_score += 10

        risk_level = 0
        risk_reason = []
        if violation == "疑似偷地":
            risk_level = max(risk_level, 3)
            risk_reason.append("疑似偷地")
        if war_growth == 0 and assist_growth == 0 and power_growth == 0 and donate_growth == 0:
            risk_level = max(risk_level, 2)
            risk_reason.append("完全无更新")
        if war_growth < 1000:
            risk_level = max(risk_level, 1)
            risk_reason.append("战功偏低")
        if assist_growth == 0:
            risk_reason.append("无助攻增长")
        if donate_growth == 0:
            risk_reason.append("无捐献增长")
        if power_growth <= 0:
            risk_level = max(risk_level, 1)
            risk_reason.append("无势力增长")

        risk_reason = list(dict.fromkeys(risk_reason))
        final_score = max(0, int(base_score - risk_level * 12))

        # =====================
        # 身份保护
        # =====================

        if is_protected == 1:

            final_score = max(
                final_score,
                85
            )

        if violation == "疑似偷地":
            status, advice_text, category, priority_type = "违规", "建议清理", "清理名单", 1
        elif final_score < 35:
            status, advice_text, category, priority_type = "低活跃", "建议清理", "清理名单", 2
        elif final_score < 65:
            status, advice_text, category, priority_type = "待警告", "重点关注", "警告名单", 3
        elif final_score >= 85:
            status, advice_text, category, priority_type = "核心", "优先资源", "核心成员", 99
        else:
            status, advice_text, category, priority_type = "正常", "保持", "正常成员", 50

        result_rows.append({
            "成员": name,
            "分组": team_name,
            "所属州": state_name,
            "势力值": power_value,
            "贡献排行": contribution_rank,
            "战功本周": battle_week,
            "助攻本周": assist_week,
            "捐献本周": donate_week,
            "战功总量": safe_int(row.get("战功总量_new", 0)),
            "助攻总量": safe_int(row.get("助攻总量_new", 0)),
            "捐献总量": safe_int(row.get("捐献总量_new", 0)),
            "战功增长": war_growth,
            "助攻增长": assist_growth,
            "捐献增长": donate_growth,
            "势力增长": power_growth,
            "执行状态": exec_status,
            "违规": violation,
            "状态": status,
            "建议": advice_text,
            "评分": final_score,
            "风险原因": "，".join(risk_reason) if risk_reason else "正常",
            "分类": category,
            "优先类别": priority_type,
        })

    df_result = pd.DataFrame(result_rows)
    if df_result.empty:
        return pd.DataFrame(columns=result_columns), pd.DataFrame(columns=["分组", "人数"]), empty_advice()

    df_result = df_result.sort_values(
        by=["优先类别", "评分", "战功增长", "助攻增长", "捐献增长"],
        ascending=[True, False, False, False, False],
    ).reset_index(drop=True)
    df_result["优先级排名"] = range(1, len(df_result) + 1)

    advice = {
        "清理名单": df_result[df_result["分类"] == "清理名单"]["成员"].tolist(),
        "警告名单": df_result[df_result["分类"] == "警告名单"]["成员"].tolist(),
        "核心成员": df_result[df_result["分类"] == "核心成员"]["成员"].tolist(),
        "未执行名单": df_result[df_result["执行状态"] == "完全摆烂"]["成员"].tolist(),
    }
    groups = df_result.groupby("分组").size().reset_index(name="人数") if "分组" in df_result.columns else pd.DataFrame(columns=["分组", "人数"])

    conn.close()

    return df_result, groups, advice


def build_kick_text(advice: dict) -> str:
    advice = advice or empty_advice()
    text = ""
    for title in ["清理名单", "警告名单", "核心成员", "未执行名单"]:
        names = advice.get(title, [])
        if names:
            text += f"【{title}】\n" + "\n".join(names) + "\n\n"
    return text.strip()


def save_outputs(result: pd.DataFrame, groups: pd.DataFrame, advice: dict):
    result.to_csv(COMPARE_RESULT_FILE, index=False, encoding="utf-8-sig")
    groups.to_csv(GROUP_SUMMARY_FILE, index=False, encoding="utf-8-sig")
    ADVICE_FILE.write_text(json.dumps(advice, ensure_ascii=False, indent=2), encoding="utf-8")


def load_outputs():
    result = groups = None
    advice = empty_advice()
    if COMPARE_RESULT_FILE.exists():
        result = read_csv_path(COMPARE_RESULT_FILE)
    if GROUP_SUMMARY_FILE.exists():
        groups = read_csv_path(GROUP_SUMMARY_FILE)
    if ADVICE_FILE.exists():
        try:
            advice = json.loads(ADVICE_FILE.read_text(encoding="utf-8"))
        except Exception:
            advice = empty_advice()
    return result, groups, advice


def filter_result_df(df: pd.DataFrame, team_keyword: str = "", pg_min=None, pg_max=None) -> pd.DataFrame:
    out = df.copy()
    if team_keyword and "分组" in out.columns:
        out = out[out["分组"].astype(str).str.contains(team_keyword, na=False)]
    if pg_min is not None and "势力增长" in out.columns:
        out = out[out["势力增长"] >= pg_min]
    if pg_max is not None and "势力增长" in out.columns:
        out = out[out["势力增长"] <= pg_max]
    return out


# =========================
# 路由
# =========================
@app.route("/test")
def test():
    return "OK"


@app.route("/")
def overview():
    print("🔥 进入首页 overview")

    try:
        init_db()
    except Exception as e:
        print("❌ init_db 报错:", e)

    conn = get_conn()

    battle_row = conn.execute("""
        SELECT id, battle_name
        FROM battles
        WHERE is_current = 1
        LIMIT 1
    """).fetchone()

    battle_id = battle_row["id"] if battle_row else 1
    current_battle = battle_row["battle_name"] if battle_row else "未设置战场"

    print("★★★★ 当前战场 =", current_battle, "battle_id =", battle_id)

    conn.close()

    try:
        members = load_current_battle_members()
    except Exception as e:
        print("❌ load_current_battle_members 报错:", e)
        members = pd.DataFrame()

    # 读取当前战场最新 compare_cache
    result_rows = []
    advice = empty_advice()

    try:
        conn = get_conn()

        cache_row = conn.execute("""
            SELECT data_json
            FROM compare_cache
            WHERE battle_id = ?
            ORDER BY id DESC
            LIMIT 1
        """, (battle_id,)).fetchone()

        conn.close()

        if cache_row:
            cache_data = json.loads(cache_row["data_json"])
            result_rows = cache_data.get("data", []) or []
            advice = cache_data.get("advice", empty_advice()) or empty_advice()

    except Exception as e:
        print("❌ 首页读取 compare_cache 失败:", e)
        result_rows = []
        advice = empty_advice()

    total_members = len(members)

    if "power" in members.columns:
        power_col = "power"
    elif "势力值" in members.columns:
        power_col = "势力值"
    else:
        power_col = None

    high_power_count = (
        int((pd.to_numeric(members[power_col], errors="coerce").fillna(0) >= HIGH_POWER).sum())
        if power_col
        else 0
    )

    abnormal_count = 0
    for row in result_rows:
        text = str(row.get("违规", "")) + str(row.get("状态", "")) + str(row.get("执行状态", ""))
        if any(k in text for k in ["疑似偷地", "未执行", "低活跃", "完全摆烂", "违规"]):
            abnormal_count += 1

    snapshot_count = len(list_snapshot_times())

    risk_index = (
        abnormal_count * 100 // total_members
        if total_members > 0
        else 0
    )

    active_rate = (
        (total_members - abnormal_count) * 100 // total_members
        if total_members > 0
        else 0
    )

    if total_members == 0:
        battle_rating = "N/A"
    elif risk_index <= 5:
        battle_rating = "S+"
    elif risk_index <= 10:
        battle_rating = "S"
    elif risk_index <= 20:
        battle_rating = "A"
    elif risk_index <= 35:
        battle_rating = "B"
    else:
        battle_rating = "C"

    stats = {
        "成员总数": total_members,
        "高战人数": high_power_count,
        "快照次数": snapshot_count,
        "最近异常数": abnormal_count,
        "风险指数": risk_index,
        "AI活跃度": active_rate,
        "战场评级": battle_rating,
    }

    if not members.empty and power_col:
        top_members = (
            members.sort_values(by=power_col, ascending=False)
            .head(10)
            .to_dict("records")
        )
    else:
        top_members = []

    top_abnormal = result_rows[:10] if result_rows else []

    advice_summary = [
        f"建议清理：{len(advice.get('清理名单', []))} 人",
        f"重点关注：{len(advice.get('警告名单', []))} 人",
        f"核心稳定：{len(advice.get('核心成员', []))} 人",
        f"未执行：{len(advice.get('未执行名单', []))} 人",
    ]

    return render_template(
        "overview.html",
        current_battle=current_battle,
        stats=stats,
        top_members=top_members,
        top_abnormal=top_abnormal,
        advice=advice,
        advice_summary=advice_summary
    )


@app.route("/snapshots", methods=["GET", "POST"])
def snapshots():
    init_db()
    if request.method == "POST":
        try:
            file = request.files.get("snapshot_file")
            manual_time = request.form.get("snapshot_time", "").strip()
            if not file or not file.filename:
                flash("请选择原始CSV快照", "error")
                return redirect(url_for("snapshots"))

            df = load_game_csv(file)
            snapshot_time = manual_time if manual_time else extract_snapshot_time(file.filename)
            inserted = save_snapshot(df, snapshot_time, file.filename)
            if inserted:

                process_snapshot_pipeline(
                    snapshot_time
                )
            flash(f"快照保存成功：{snapshot_time}，共 {len(df)} 条" if inserted else f"该时间点快照已存在：{snapshot_time}", "success" if inserted else "warning")
            return redirect(url_for("snapshots"))
        except Exception as e:
            print("❌ 快照保存失败:", str(e))
            traceback.print_exc()
            flash(f"快照保存失败：{str(e)}", "error")
            return redirect(url_for("snapshots"))

    try:

        conn = get_conn()

        battle_row = conn.execute("""
            SELECT *
            FROM battles
            WHERE is_current = 1
            LIMIT 1
        """).fetchone()

        battle_id = battle_row["id"] if battle_row else 1

        snapshot_rows = conn.execute("""
            SELECT
                id,
                snapshot_time,
                source_filename,
                created_at,
                battle_id
            FROM snapshots
            WHERE battle_id = ?
              AND is_deleted = 0
            ORDER BY snapshot_time DESC
        """, (battle_id,)).fetchall()

        conn.close()

    except Exception:

        traceback.print_exc()

        snapshot_rows = []

        battle_row = None

    return render_template(
        "snapshots.html",
        snapshots=snapshot_rows,
        battle=battle_row
    )

@app.route("/compare", methods=["GET", "POST"])
def compare():

    import traceback
    import json
    import sqlite3

    print("🚀 进入 compare 路由，method:", request.method)

    init_db()

    times = list_snapshot_times()

    result_rows = []
    group_rows = []

    advice = empty_advice()

    selected_old = ""
    selected_new = ""

    compare_mode = "auto"

    team_keyword = ""
    power_growth_min = ""
    power_growth_max = ""

    kick_text = ""

    page = 1
    total_pages = 1

    # ==================================================
    # GET：优先读取 SQLite 缓存
    # ==================================================
    if request.method == "GET":

        try:

            conn = sqlite3.connect(DB_FILE)

            cur = conn.cursor()

            battle_row = get_conn().execute("""
                SELECT id
                FROM battles
                WHERE is_current = 1
                LIMIT 1
            """).fetchone()

            battle_id = battle_row["id"] if battle_row else 1

            cur.execute("""
                SELECT data_json
                FROM compare_cache
                WHERE battle_id = ?
                ORDER BY id DESC
                LIMIT 1
            """, (battle_id,))

            row = cur.fetchone()

            conn.close()

            if row:

                print("✅ compare GET 使用 SQLite 分页结果")

                cached_data = json.loads(row[0])

                return render_template(
                    "compare.html",
                    **cached_data
                )

        except Exception as e:

            print("❌ compare GET SQLite 读取失败:", str(e))
            traceback.print_exc()

        return render_template(
            "compare.html",

            times=times,

            team_keyword="",

            power_growth_min="",

            power_growth_max="",

            data=[],

            groups=[],

            advice=advice,

            kick_text="",

            selected_old="",

            selected_new="",

            compare_mode="auto",

            page=1,

            total_pages=1,
        )

    # ==================================================
    # POST：执行分析
    # ==================================================
    try:

        team_keyword = request.form.get(
            "team_keyword", ""
        ).strip()

        power_growth_min = request.form.get(
            "power_growth_min", ""
        ).strip()

        power_growth_max = request.form.get(
            "power_growth_max", ""
        ).strip()

        compare_mode = request.form.get(
            "compare_mode",
            "auto"
        )

        # ==================================================
        # A模式 自动分析
        # ==================================================
        if compare_mode == "auto":

            if len(times) < 2:
                raise ValueError("至少需要两次快照")

            selected_new = times[0]
            selected_old = times[1]

        # ==================================================
        # B模式 手动分析
        # ==================================================
        else:

            selected_old = request.form.get(
                "snapshot_old", ""
            )

            selected_new = request.form.get(
                "snapshot_new", ""
            )

            if not selected_old or not selected_new:

                raise ValueError(
                    "请选择两个时间点"
                )

        print("⚡ 使用缓存:", selected_old)
        print("⚡ 使用缓存:", selected_new)

        # ==================================================
        # 加载快照
        # ==================================================
        battle_row = get_conn().execute("""
            SELECT id
            FROM battles
            WHERE is_current = 1
            LIMIT 1
        """).fetchone()

        battle_id = (
            battle_row["id"]
            if battle_row
            else 1
        )

        df_old = load_snapshot_df(
            selected_old,
            battle_id
        )

        df_new = load_snapshot_df(
            selected_new,
            battle_id
        )

        # ==================================================
        # 核心分析
        # ==================================================
        result, groups, advice = compare_snapshots(
            df_old,
            df_new
        )

        # ==================================================
        # 势力过滤
        # ==================================================
        pg_min = (
            int(power_growth_min)
            if power_growth_min
            else None
        )

        pg_max = (
            int(power_growth_max)
            if power_growth_max
            else None
        )

        result = filter_result_df(
            result,
            team_keyword=team_keyword,
            pg_min=pg_min,
            pg_max=pg_max,
        )

        # ==================================================
        # 排序
        # ==================================================
        if (
            not result.empty
            and all(
                c in result.columns
                for c in [
                    "优先类别",
                    "评分",
                    "战功增长",
                ]
            )
        ):

            result = result.sort_values(

                by=[
                    "优先类别",
                    "评分",
                    "战功增长",
                ],

                ascending=[
                    True,
                    False,
                    False,
                ],

            ).reset_index(drop=True)

        # ==================================================
        # 分页
        # ==================================================
        all_rows = result.to_dict(
            orient="records"
        )

        per_page = 50

        result_rows = all_rows[:per_page]

        total_pages = (
            len(all_rows) + per_page - 1
        ) // per_page

        # ==================================================
        # 团队数据
        # ==================================================
        if groups is not None and not groups.empty:

            group_rows = groups.to_dict(
                orient="records"
            )

        kick_text = build_kick_text(advice)

        # ==================================================
        # SQLite 缓存（保留历史趋势）
        # ==================================================
        cache_payload = {

            "times": times,

            "team_keyword": team_keyword,

            "power_growth_min":
            power_growth_min,

            "power_growth_max":
            power_growth_max,

            "data": result_rows,

            "groups": group_rows,

            "advice": advice,

            "kick_text": kick_text,

            "selected_old": selected_old,

            "selected_new": selected_new,

            "compare_mode": compare_mode,

            "page": 1,

            "total_pages": total_pages,
        }

        cache_json = json.dumps(
            cache_payload,
            ensure_ascii=False
        )

        print(
            "缓存大小:",
            len(cache_json)
        )

        # =========================
        # 使用时间组合做趋势ID
        # =========================
        cache_time = (
            f"{selected_old}__{selected_new}"
        )

        conn = sqlite3.connect(DB_FILE)

        cur = conn.cursor()

        # 不再 DELETE
        # 保留历史趋势

        cur.execute(
            """
            INSERT OR REPLACE INTO compare_cache
            (
                battle_id,
                snapshot_time,
                data_json
            )
            VALUES (?, ?, ?)
            """,
            (
                battle_id,
                cache_time,
                cache_json
            )
        )

        conn.commit()

        conn.close()

        print("✅ compare 分析结果已缓存")

        flash("对比分析完成", "success")

    except Exception as e:

        print("❌ compare 报错:", str(e))

        traceback.print_exc()

        flash(
            f"对比失败：{e}",
            "error"
        )

    return render_template(
        "compare.html",

        times=times,

        team_keyword=team_keyword,

        power_growth_min=power_growth_min,

        power_growth_max=power_growth_max,

        data=result_rows,

        groups=group_rows,

        advice=advice,

        kick_text=kick_text,

        selected_old=selected_old,

        selected_new=selected_new,

        compare_mode=compare_mode,

        page=1,

        total_pages=total_pages,
    )

@app.route("/trends")
def trends():

    member_keyword = request.args.get("member_keyword", "").strip()
    group_keyword = request.args.get("group_keyword", "").strip()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    battle_row = conn.execute("""
        SELECT id
        FROM battles
        WHERE is_current = 1
        LIMIT 1
    """).fetchone()

    battle_id = (
       battle_row["id"]
       if battle_row
       else 1
    )

    print("🔥 当前趋势战场ID =", battle_id)

    # =========================
    # 默认不加载全战场趋势，防止一次输出 26MB 页面
    # =========================
    if not member_keyword and not group_keyword:
        conn.close()
        return render_template(
            "trends.html",
            history_data=[],
            trend_rows=[],
            member_keyword="",
            group_keyword="",
            ai_result={
                "level": "等待查询",
                "score": 0,
                "summary": "请输入成员名称或分组后，再查看趋势分析"
            }
        )

    base_query = """
        SELECT
            snapshot_time,
            member,
            group_name,
            battle_total,
            assist_total,
            power_total
        FROM player_records
        WHERE battle_id = ?
        AND is_deleted = 0
    """

    params = [battle_id]

    # =========================
    # 玩家搜索
    # =========================

    if member_keyword:

        exact_query = base_query + """
            AND member = ?
            ORDER BY snapshot_time ASC
        """

        exact_df = pd.read_sql_query(
            exact_query,
            conn,
            params=[battle_id, member_keyword]
        )

        print(f"📈 trends 精准匹配结果: {len(exact_df)}")

        if not exact_df.empty:

            df = exact_df

        else:

            fuzzy_query = base_query + """
                AND member LIKE ?
                ORDER BY snapshot_time ASC
            """

            df = pd.read_sql_query(
                fuzzy_query,
                conn,
                params=[battle_id, f"%{member_keyword}%"]
            )

            print(f"📈 trends 模糊匹配结果: {len(df)}")

    else:

        if group_keyword:

            base_query += " AND group_name LIKE ? "
            params.append(f"%{group_keyword}%")

        base_query += " ORDER BY snapshot_time ASC "

        df = pd.read_sql_query(
            base_query,
            conn,
            params=params
        )

    conn.close()

    # =========================
    # 空数据
    # =========================

    if df.empty:

        return render_template(
            "trends.html",

            history_data=[],
            trend_rows=[],

            member_keyword=member_keyword,
            group_keyword=group_keyword,

            ai_result={
                "level": "暂无数据",
                "score": 0,
                "summary": "当前没有匹配到历史趋势数据"
            }
        )

    # =========================
    # 时间排序
    # =========================

    df["snapshot_time"] = pd.to_datetime(df["snapshot_time"])

    df = df.sort_values("snapshot_time")

    # =========================
    # 趋势分析
    # =========================

    history_data = []

    last_battle_total = None
    last_assist_total = None
    last_power_total = None

    session_id = 0

    for _, row in df.iterrows():

        # =========================
        # 安全数值处理
        # =========================

        battle_raw = row.get("battle_total", 0)
        assist_raw = row.get("assist_total", 0)
        power_raw = row.get("power_total", 0)

        if pd.isna(battle_raw):
            battle_raw = 0

        if pd.isna(assist_raw):
            assist_raw = 0

        if pd.isna(power_raw):
            power_raw = 0

        battle_total = int(battle_raw)
        assist_total = int(assist_raw)
        power_total = int(power_raw)

        is_reset = False

        # =========================
        # 赛季重置检测
        # =========================

        if last_battle_total is not None:

            if (
                battle_total < last_battle_total * 0.35
                or assist_total < last_assist_total * 0.35
            ):

                session_id += 1
                is_reset = True

        # =========================
        # 插入断层
        # =========================

        if is_reset:

            history_data.append({

                "full_time":
                    row["snapshot_time"].strftime("%Y-%m-%d %H:%M:%S"),

                "time":
                    row["snapshot_time"].strftime("%m-%d %H:%M"),

                "member":
                    row["member"],

                "group":
                    row["group_name"],

                "battle_growth":
                    None,

                "assist_growth":
                    None,

                "power_growth":
                    None,

                "battle_total":
                    None,

                "assist_total":
                    None,

                "power_value":
                    None,

                "session_key":
                    f"session_{session_id}",

                "is_reset":
                    True
            })

            last_battle_total = None
            last_assist_total = None
            last_power_total = None

        # =========================
        # 增长计算
        # =========================

        if last_battle_total is None:

            battle_growth = 0
            assist_growth = 0
            power_growth = 0

        else:

            battle_growth = max(
                0,
                battle_total - last_battle_total
            )

            assist_growth = max(
                0,
                assist_total - last_assist_total
            )

            power_growth = max(
                0,
                power_total - last_power_total
            )

        # =========================
        # 写入趋势
        # =========================

        history_data.append({

            "full_time":
                row["snapshot_time"].strftime("%Y-%m-%d %H:%M:%S"),

            "time":
                row["snapshot_time"].strftime("%m-%d %H:%M"),

            "member":
                row["member"],

            "group":
                row["group_name"],

            "battle_growth":
                battle_growth,

            "assist_growth":
                assist_growth,

            "power_growth":
                power_growth,

            "battle_total":
                battle_total,

            "assist_total":
                assist_total,

            "power_value":
                power_total,

            "power_total":
                power_total,

            "session_key":
                f"session_{session_id}",

            "is_reset":
                False
        })

        last_battle_total = battle_total
        last_assist_total = assist_total
        last_power_total = power_total

    # =========================
    # AI分析结果
    # =========================

    ai_result = {
        "level": "历史趋势已完成分析",
        "score": len(history_data),
        "summary": f"当前共匹配 {len(history_data)} 条历史趋势数据"
    }

    # =========================
    # 页面输出
    # =========================

    print("趋势记录数=", len(history_data))

    return render_template(
        "trends.html",

        history_data=history_data,

        trend_rows=history_data,

        member_keyword=member_keyword,
        group_keyword=group_keyword,

        ai_result=ai_result
    )

@app.route("/risk")
def risk_center():

    conn = get_conn()

    high_risk = conn.execute("""
        SELECT *
        FROM member_profiles
        WHERE risk_level='danger'
        ORDER BY av + bs ASC
        LIMIT 50
    """).fetchall()

    warning_risk = conn.execute("""
        SELECT *
        FROM member_profiles
        WHERE risk_level='warning'
        ORDER BY av + bs ASC
        LIMIT 100
    """).fetchall()

    protected = conn.execute("""
        SELECT *
        FROM member_profiles
        WHERE risk_level='protected'
        ORDER BY av + bs DESC
    """).fetchall()

    cleanup_members = conn.execute("""
        SELECT *
        FROM member_profiles
        WHERE risk_level='danger'
        ORDER BY identity_score ASC
        LIMIT 10
    """).fetchall()

    observe_members = conn.execute("""
        SELECT *
        FROM member_profiles
        WHERE risk_level='warning'
        ORDER BY identity_score ASC
        LIMIT 10
    """).fetchall()

    protected_members = conn.execute("""
        SELECT *
        FROM member_profiles
        WHERE risk_level='protected'
        ORDER BY identity_score DESC
        LIMIT 10
    """).fetchall()

    total_members = conn.execute("""
        SELECT COUNT(*)
        FROM member_profiles
    """).fetchone()[0]

    risk_rate = round(
        (
            len(high_risk) +
            len(warning_risk)
        ) * 100 / total_members,
        1
    )

    risk_stats = {
        "活跃不足": 0,
        "长期低贡献": 0,
        "持续下滑": 0,
        "连续停滞": 0
    }

    for m in high_risk:

        reason = m["risk_reason"] or ""

        if "活跃不足" in reason:
            risk_stats["活跃不足"] += 1

        if "长期低贡献" in reason:
            risk_stats["长期低贡献"] += 1

        if "持续下滑" in reason:
            risk_stats["持续下滑"] += 1

        if "连续停滞" in reason:
            risk_stats["连续停滞"] += 1

    risk_members_by_reason = {
        "活跃不足": [],
        "长期低贡献": [],
        "持续下滑": [],
        "连续停滞": []
    }

    for m in high_risk:

        reason = m["risk_reason"] or ""

        if "活跃不足" in reason:
            risk_members_by_reason["活跃不足"].append(
                m["member_name"]
            )

        if "长期低贡献" in reason:
            risk_members_by_reason["长期低贡献"].append(
                m["member_name"]
            )

        if "持续下滑" in reason:
            risk_members_by_reason["持续下滑"].append(
                m["member_name"]
            )

        if "连续停滞" in reason:
            risk_members_by_reason["连续停滞"].append(
                m["member_name"]
            )

    for k in risk_members_by_reason:

        risk_members_by_reason[k] = (
            risk_members_by_reason[k][:5]
        )

    return render_template(
        "risk_center.html",

        high_risk=high_risk,
        warning_risk=warning_risk,
        protected=protected,

        cleanup_members=cleanup_members,
        observe_members=observe_members,
        protected_members=protected_members,

        risk_rate=risk_rate,

        risk_stats=risk_stats,
        risk_members_by_reason=risk_members_by_reason

    )

@app.route("/members")
def members():
    df = load_current_battle_members()
    return render_template("members.html", members=df.to_dict("records"))


@app.route("/identity")
def identity():

    conn = get_conn()

    keyword = request.args.get(
        "keyword",
        ""
    ).strip()

    role = request.args.get(
        "role",
        ""
    ).strip()

    grade = request.args.get(
        "grade",
        ""
    ).strip()

    sql = """
    SELECT
        member_name,
        role_tag,
        role_desc,
        role_rule,
        role_weight,
        identity_score,
        is_protected,
        exempt_stall
    FROM member_profiles
    WHERE 1=1
    """

    params = []

    # =====================
    # 成员搜索
    # =====================

    if keyword:

        sql += """
        AND member_name LIKE ?
        """

        params.append(
            f"%{keyword}%"
        )

    # =====================
    # 身份筛选
    # =====================

    if role:

        sql += """
        AND role_tag = ?
        """

        params.append(
            role
        )

    if grade == "S":

        sql += """
        AND identity_score >= 90
        """

    elif grade == "A":

        sql += """
        AND identity_score >= 70
        AND identity_score < 90
        """

    elif grade == "B":

        sql += """
        AND identity_score >= 50
        AND identity_score < 70
        """

    elif grade == "C":

        sql += """
        AND identity_score >= 30
        AND identity_score < 50
        """

    elif grade == "D":

        sql += """
        AND identity_score < 30
        """
    sql += """
    ORDER BY
        identity_score DESC,
        role_tag,
        member_name
    """

    rows = conn.execute(
        sql,
        params
    ).fetchall()

    # =====================
    # 当前筛选显示
    # =====================

    current_filter = []

    if role == "admin":
        current_filter.append("管理员")

    elif role == "warehouse":
        current_filter.append("仓库号")

    elif role == "core":
        current_filter.append("核心成员")

    if grade == "S":
        current_filter.append("S级核心成员")

    elif grade == "A":
        current_filter.append("A级骨干成员")

    elif grade == "B":
        current_filter.append("B级稳定成员")

    elif grade == "C":
        current_filter.append("C级观察成员")

    elif grade == "D":
        current_filter.append("D级待淘汰成员")

    if not current_filter:
        current_filter = "全部成员"
    else:
        current_filter = " + ".join(current_filter)
    # =====================
    # 身份统计
    # =====================

    admin_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM member_profiles
        WHERE role_tag='admin'
        """
    ).fetchone()[0]

    warehouse_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM member_profiles
        WHERE role_tag='warehouse'
        """
    ).fetchone()[0]

    core_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM member_profiles
        WHERE role_tag='core'
        """
    ).fetchone()[0]

    protected_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM member_profiles
        WHERE is_protected=1
        """
    ).fetchone()[0]

    exempt_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM member_profiles
        WHERE exempt_stall=1
        """
    ).fetchone()[0]

    # =====================
    # 身份评级统计
    # =====================

    s_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM member_profiles
        WHERE identity_score >= 90
        """
    ).fetchone()[0]

    a_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM member_profiles
        WHERE identity_score >= 70
        AND identity_score < 90
        """
    ).fetchone()[0]

    b_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM member_profiles
        WHERE identity_score >= 50
        AND identity_score < 70
        """
    ).fetchone()[0]

    c_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM member_profiles
        WHERE identity_score >= 30
        AND identity_score < 50
        """
    ).fetchone()[0]

    d_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM member_profiles
        WHERE identity_score < 30
        """
    ).fetchone()[0]

    # =====================
    # TOP10身份榜
    # =====================

    top_identity = conn.execute(
        """
        SELECT
            member_name,
            identity_score
        FROM member_profiles
        ORDER BY identity_score DESC
        LIMIT 10
        """
    ).fetchall()

    # =====================
    # 风险榜
    # =====================

    risk_members = conn.execute(
        """
        SELECT
            member_name,
            identity_score,
            risk_reason
        FROM member_profiles
        WHERE identity_score < 50
        ORDER BY identity_score ASC
        LIMIT 10
        """
    ).fetchall()

    # =====================
    # 成长最快TOP10
    # =====================

    grow_members = conn.execute(
        """
        SELECT
            member_name,
            identity_score,
            trend
        FROM member_profiles
        WHERE identity_score >= 60
          AND identity_score < 85
          AND trend IN ('explosive','up')
        ORDER BY identity_score DESC
        LIMIT 10
        """
    ).fetchall()

    # =====================
    # 总人数
    # =====================

    total_members = conn.execute(
        """
        SELECT COUNT(*)
        FROM member_profiles
        """
    ).fetchone()[0]

     # =====================
    # 真实成长/下滑榜
    # =====================

    latest_time_row = conn.execute(
        """
        SELECT snapshot_time
        FROM player_records
        WHERE is_deleted = 0
        ORDER BY snapshot_time DESC
        LIMIT 1
        """
    ).fetchone()

    prev_time_row = conn.execute(
        """
        SELECT snapshot_time
        FROM player_records
        WHERE is_deleted = 0
        AND snapshot_time < (
            SELECT snapshot_time
            FROM player_records
            WHERE is_deleted = 0
            ORDER BY snapshot_time DESC
            LIMIT 1
        )
        ORDER BY snapshot_time DESC
        LIMIT 1
        """
    ).fetchone()

    growth_members = []
    decline_members = []

    if latest_time_row and prev_time_row:

        latest_time = latest_time_row["snapshot_time"]
        prev_time = prev_time_row["snapshot_time"]

    # =====================
    # 成长贡献TOP10
    # =====================

    growth_members = conn.execute(
        """
        SELECT
            member AS member_name,
            (
                battle_gain
                + assist_gain * 2
            ) AS score_change,
            battle_gain,
            assist_gain,
            donate_gain,
            trend
        FROM player_records
        WHERE snapshot_time = ?
        AND is_deleted = 0
        ORDER BY score_change DESC
        LIMIT 10
        """,
        (latest_time,)
    ).fetchall()

    # =====================
    # 重点关注成员TOP10
    # =====================

    focus_raw = conn.execute(
        """
        SELECT

            member AS member_name,

            identity_score,
  
            av,
            bs,

            wv,
            bv,

            trend,
            risk_level,
            risk_reason,

            role_tag,
            is_protected,
            exempt_stall

        FROM player_records

        WHERE snapshot_time = ?
        AND is_deleted = 0

        AND role_tag NOT IN ('admin','warehouse')

        ORDER BY identity_score DESC
        """,
        (latest_time,)
    ).fetchall()

    focus_members = []

    for row in focus_raw:

        row = dict(row)

        risk_score = 0

        # 长期停滞

        if row["trend"] == "dead":
            risk_score += 100

        elif row["trend"] == "down":
            risk_score += 50

        # 活跃不足

        risk_score += max(
            0,
            30 - (row["av"] or 0)
        )

        # 稳定不足

        risk_score += max(
            0,
            30 - (row["bs"] or 0)
        )
 
        # 高价值成员加权

        risk_score += (
            row["identity_score"] or 0
        ) * 0.2

        # 战争价值加权

        risk_score += (
            row["wv"] or 0
        ) * 0.1

        # 建设价值加权

        risk_score += (
            row["bv"] or 0
        ) * 0.05

        row["focus_score"] = round(
            risk_score,
            1
        )

        if (
            row["trend"] in ("dead", "down")
            or row["risk_level"] in ("warning", "danger")
            or (row["av"] or 0) < 20
            or (row["bs"] or 0) < 30
        ):

            focus_members.append(row)

    focus_members.sort(
        key=lambda x: x["focus_score"],
        reverse=True
    )

    focus_members = focus_members[:10]

    print("==========")
    print("focus count =", len(focus_members))

    for x in focus_members[:5]:
        print(
            x["member_name"],
            x["trend"],
            x["risk_level"],
            x["av"],
            x["bs"]
        )

    print("==========")
 
    # =====================
    # 同盟健康度（百分制）
    # =====================

    excellent_count = (
        s_count
        + a_count
        + b_count
    )

    health_score = round(
        excellent_count
        / max(total_members, 1)
        * 100,
        1
    )

    if health_score >= 80:

        health_level = "卓越"

    elif health_score >= 60:

        health_level = "健康"

    elif health_score >= 40:

         health_level = "警戒"

    else:

        health_level = "危险"

    # =====================
    # AI建议
    # =====================

    ai_advice = []

    if s_count == 0:

        ai_advice.append(
            "当前无S级核心成员，核心梯队存在断层风险"
        )

    if a_count < max(total_members * 0.03, 5):

        ai_advice.append(
            "A级骨干占比偏低，建议重点培养成长成员"
        )

    if d_count >= 50:

        ai_advice.append(
            f"D级成员 {d_count} 人，建议启动清理计划"
        )

    elif d_count > total_members * 0.3:

        ai_advice.append(
            "D级成员占比过高，建议开展成员优化"
        )

    if growth_members:

        top = growth_members[0]

        ai_advice.append(
            f"{top['member_name']}近期成长最快，建议重点关注"
        )

    if decline_members:

        top = decline_members[0]

        ai_advice.append(
            f"{top['member_name']}出现明显下滑，建议观察"
        )

    if top_identity:

        top = top_identity[0]

        ai_advice.append(
            f"{top['member_name']}为当前核心战力，建议重点保护"
        )

    if d_count >= 50:

        ai_advice.append(
            f"D级成员 {d_count} 人，建议启动清理计划"
        )

    if a_count <= 5:

        ai_advice.append(
            "A级骨干过少，建议重点培养成长成员"
        )

    if protected_count > 10:

        ai_advice.append(
            "身份保护人数偏多，建议定期复核"
    )

    if len(ai_advice) > 5:
        ai_advice = ai_advice[:5]

        ai_advice.append(
            "当前身份体系运行健康"
    )

    conn.close()

    return render_template(
    "identity.html",

    members=rows,

    keyword=keyword,
    role=role,
    grade=grade,

    current_filter=current_filter,

    admin_count=admin_count,
    warehouse_count=warehouse_count,
    core_count=core_count,

    protected_count=protected_count,
    exempt_count=exempt_count,

    s_count=s_count,
    a_count=a_count,
    b_count=b_count,
    c_count=c_count,
    d_count=d_count,

    total_members=total_members,

    top_identity=top_identity,
    risk_members=risk_members,
    grow_members=grow_members,

    health_score=health_score,
    health_level=health_level,

    growth_members=growth_members,
    focus_members=focus_members,

    ai_advice=ai_advice,
)

@app.route("/talent")
def talent():

    conn = get_conn()

    latest_row = conn.execute(
        """
        SELECT snapshot_time
        FROM player_records
        WHERE is_deleted = 0
        ORDER BY snapshot_time DESC
        LIMIT 1
        """
    ).fetchone()

    if not latest_row:
        conn.close()
        return render_template(
            "talent.html",
            risk_members=[],
            growth_members=[],
            silent_members=[],
            reserve_members=[]
        )

    latest_time = latest_row["snapshot_time"]

    # =====================
    # 1. 核心风险成员TOP10
    # =====================

    risk_raw = conn.execute(
        """
        SELECT
            member AS member_name,
            identity_score,
            av,
            bs,
            wv,
            bv,
            trend,
            risk_level,
            risk_reason
        FROM player_records
        WHERE snapshot_time = ?
        AND is_deleted = 0
        AND role_tag NOT IN ('admin','warehouse')
        """,
        (latest_time,)
    ).fetchall()

    risk_members = []

    for row in risk_raw:
        row = dict(row)

        risk_score = 0

        if row["trend"] == "dead":
            risk_score += 100
        elif row["trend"] == "down":
            risk_score += 60

        if row["risk_level"] == "danger":
            risk_score += 50
        elif row["risk_level"] == "warning":
            risk_score += 25

        risk_score += max(0,40-(row["av"] or 0)) * 1.5

        risk_score += max(0,40-(row["bs"] or 0))

        # 只保留有一定价值、并且有风险的人
        if (
            risk_score >= 60
            and (
                (row["identity_score"] or 0) >= 20
                or (row["wv"] or 0) >= 20
                or row["risk_level"] in ("warning", "danger")
            )
        ):
            row["risk_score"] = round(risk_score, 1)

            if risk_score >= 120:
                row["risk_tag"] = "极高风险"
            elif risk_score >= 90:
                row["risk_tag"] = "高风险"
            elif risk_score >= 60:
                row["risk_tag"] = "需关注"
            else:
                row["risk_tag"] = "观察"

            risk_members.append(row)
    risk_members.sort(
        key=lambda x: x["risk_score"],
        reverse=True
    )

    risk_members = risk_members[:10]

    # =====================
    # 2. 成长新星TOP10
    # =====================

    growth_members = conn.execute(
        """
        SELECT
            member AS member_name,
            (
                battle_gain
                + assist_gain * 2
            ) AS score_change,
            battle_gain,
            assist_gain,
            donate_gain,
            identity_score,
            av,
            bs,
            trend
        FROM player_records
        WHERE snapshot_time = ?
        AND is_deleted = 0
        AND role_tag NOT IN ('admin','warehouse')
        AND identity_score < 80
        AND (
            battle_gain > 0
            OR assist_gain > 0
        )
        ORDER BY score_change DESC
        LIMIT 10
        """,
        (latest_time,)
    ).fetchall()

    # =====================
    # 😴 高价值沉默成员TOP10
    # =====================

    silent_members = conn.execute(
        """
        SELECT
            member AS member_name,
            identity_score,
            av,
            bs,
            trend,
            risk_level
        FROM player_records
        WHERE snapshot_time = ?
        AND is_deleted = 0
        AND role_tag NOT IN ('admin','warehouse')
        AND identity_score >= 30
        AND av < 20
        ORDER BY
        identity_score DESC,
        av ASC
        LIMIT 10
        """,
        (latest_time,)
    ).fetchall()

    # =====================
    # 🏆 后备干部TOP10
    # =====================

    reserve_members = conn.execute(
        """
        SELECT
            member AS member_name,
            identity_score,
            av,
            bs,
            wv,
            bv,
            trend
        FROM player_records
        WHERE snapshot_time = ?
        AND is_deleted = 0
        AND role_tag NOT IN ('admin','warehouse')
        AND identity_score >= 20
        AND identity_score < 50

        AND av >= 40
        AND bs >= 50

        AND trend IN ('up','explosive')
        AND av >= 30
        AND trend IN ('up','explosive')
        ORDER BY

        bs DESC,

        av DESC,

        identity_score DESC
        LIMIT 10
        """,
        (latest_time,)
    ).fetchall()

    core_count = conn.execute("""
    SELECT COUNT(*)
    FROM player_records
    WHERE snapshot_time=?
    AND identity_score>=80
    """,(latest_time,)).fetchone()[0]

    backbone_count = conn.execute("""
    SELECT COUNT(*)
    FROM player_records
    WHERE snapshot_time=?
    AND identity_score>=60
    AND identity_score<80
    """,(latest_time,)).fetchone()[0]

    reserve_count = conn.execute("""
    SELECT COUNT(*)
    FROM player_records
    WHERE snapshot_time=?
    AND is_deleted = 0
    AND role_tag NOT IN ('admin','warehouse')

    AND identity_score >= 20
    AND identity_score < 50

    AND av >= 40
    AND bs >= 50

    AND trend IN ('up','explosive')
    """,(latest_time,)).fetchone()[0]

    risk_count = len(risk_members)

    silent_count = len(silent_members)

    total_members = conn.execute(
        """
        SELECT COUNT(*)
        FROM player_records
        WHERE snapshot_time = ?
        AND is_deleted = 0
        """,
        (latest_time,)
    ).fetchone()[0]

    core_pct = round(core_count / max(total_members,1) * 100, 1)

    backbone_pct = round(backbone_count / max(total_members,1) * 100, 1)

    reserve_pct = round(reserve_count / max(total_members,1) * 100, 1)

    # =====================
    # 人才健康度 V9.2
    # =====================

    health_score = 100

    # 核心梯队

    if core_pct < 2:
        health_score -= 15

    elif core_pct >= 5:
        health_score += 5

    # 骨干梯队

    if backbone_pct < 10:
        health_score -= 10

    elif backbone_pct >= 20:
        health_score += 5

    # 后备梯队

    if reserve_pct < 5:
        health_score -= 15

    elif reserve_pct >= 10:
        health_score += 5

    # 风险成员

    risk_pct = round(
        risk_count / max(total_members,1) * 100,
        1
    )

    if risk_pct > 15:
        health_score -= 20

    elif risk_pct > 10:
         health_score -= 10

    # 沉默成员

    silent_pct = round(
        silent_count / max(total_members,1) * 100,
        1
    )

    if silent_pct > 15:
        health_score -= 15

    elif silent_pct > 10:
        health_score -= 8

    health_score = max(0, min(100, health_score))

    if health_score >= 90:
        health_level = "S"

    elif health_score >= 80:
        health_level = "A"
   
    elif health_score >= 65:
        health_level = "B"

    elif health_score >= 50:
        health_level = "C"

    else:
        health_level = "D"

    conn.close()

    return render_template(
        "talent.html",
        risk_members=risk_members,
        growth_members=growth_members,
        silent_members=silent_members,
        reserve_members=reserve_members,
        core_count=core_count,
        backbone_count=backbone_count,
        reserve_count=reserve_count,
        risk_count=risk_count,
        silent_count=silent_count,
        core_pct=core_pct,
        backbone_pct=backbone_pct,
        reserve_pct=reserve_pct, 
        health_score=health_score,
        health_level=health_level,
    )

    

@app.route("/rules")
def rules():
    return render_template("rules.html", high_power=HIGH_POWER, mid_power=MID_POWER, high_battle_min=HIGH_BATTLE_MIN, mid_battle_min=MID_BATTLE_MIN, core_battle_min=CORE_BATTLE_MIN)

@app.route("/identity/logs")
def identity_logs():

    conn = get_conn()

    logs = conn.execute(
        """
        SELECT *
        FROM identity_logs
        ORDER BY id DESC
        LIMIT 500
        """
    ).fetchall()

    conn.close()

    return render_template(
        "identity_logs.html",
        logs=logs
    )

@app.route("/identity/log/<int:log_id>")
def identity_log_detail(log_id):

    conn = get_conn()

    row = conn.execute(
        """
        SELECT *
        FROM identity_logs
        WHERE id = ?
        """,
        (log_id,)
    ).fetchone()

    conn.close()

    if not row:
        return "日志不存在"

    analysis = []

    # 身份变化

    if row["old_role"] != row["new_role"]:

        role_map = {
            "member": "普通成员",
            "core": "核心成员",
            "warehouse": "仓库号",
            "admin": "管理员"
        }

        old_role_name = role_map.get(
            row["old_role"],
            row["old_role"]
        )

        new_role_name = role_map.get(
            row["new_role"],
            row["new_role"]
        )

        analysis.append(
            f"成员身份由【{old_role_name}】调整为【{new_role_name}】"
        )

        

    # 身份保护

    if row["old_protect"] != row["new_protect"]:

        if row["new_protect"] == 1:
            analysis.append(
                "已开启身份保护，将不会进入自动清理名单"
            )

            analysis.append(
                 "该成员已进入长期保留名单"
            )
        else:
            analysis.append(
                "已取消身份保护"
            )

    else:

        if row["new_protect"] == 1:
            analysis.append(
                "身份保护保持开启"
            )

    # 免停滞

    if row["old_exempt"] != row["new_exempt"]:

        if row["new_exempt"] == 1:
            analysis.append(
                "已开启免停滞处罚"
            )
        else:
            analysis.append(
                "已取消免停滞处罚"
            )

    else:

        if row["new_exempt"] == 1:
            analysis.append(
                "免停滞状态保持开启"
            )

    # 身份分变化

    if row["old_score"] != row["new_score"]:

        analysis.append(
            f"身份分由 {row['old_score']} 调整至 {row['new_score']}"
        )

    else:

        analysis.append(
            f"身份分保持 {row['new_score']}"
        )

    if row["new_role"] == "admin":

        analysis.append(
            "成员已进入管理层序列"
        )

    elif row["new_role"] == "warehouse":

        analysis.append(
            "成员已进入仓储管理序列"
        )

    elif row["new_role"] == "core":

        analysis.append(
            "成员已进入核心成员序列"
        )

    return render_template(
        "identity_log_detail.html",
        row=row,
        analysis=analysis
    )

@app.route(
    "/identity/edit/<member_name>",
    methods=["GET", "POST"]
)
def identity_edit(member_name):

    conn = get_conn()

    if request.method == "POST":

        # ======================
        # 修改前数据
        # ======================

        old_row = conn.execute(
            """
            SELECT
                role_tag,
                identity_score,
                is_protected,
                exempt_stall
            FROM member_profiles
            WHERE member_name = ?
            """,
            (member_name,)
        ).fetchone()

        # ======================
        # 更新身份档案
        # ======================

        conn.execute(
            """
            UPDATE member_profiles
            SET
                role_tag = ?,
                role_desc = ?,
                role_rule = ?,
                role_weight = ?,
                is_protected = ?,
                exempt_stall = ?
            WHERE member_name = ?
            """,
            (
                request.form.get("role_tag"),
                request.form.get("role_desc"),
                request.form.get("role_rule"),
                float(request.form.get("role_weight", 1)),
                1 if request.form.get("is_protected") else 0,
                1 if request.form.get("exempt_stall") else 0,
                member_name
            )
        )

        conn.commit()

        # ======================
        # 修改后数据
        # ======================

        new_row = conn.execute(
            """
            SELECT
                role_tag,
                identity_score,
                is_protected,
                exempt_stall
            FROM member_profiles
            WHERE member_name = ?
            """,
            (member_name,)
        ).fetchone()

        # ======================
        # 写入操作日志
        # ======================

        conn.execute(
            """
            INSERT INTO identity_logs (
                member_name,
                old_role,
                new_role,
                old_score,
                new_score,
                old_protect,
                new_protect,
                old_exempt,
                new_exempt,
                operator,
                created_at
            )
            VALUES (
                ?,?,?,?,?,?,?,?,?,?,datetime('now')
            )
            """,
            (
                member_name,
                old_row["role_tag"],
                new_row["role_tag"],
                old_row["identity_score"],
                new_row["identity_score"],
                old_row["is_protected"],
                new_row["is_protected"],
                old_row["exempt_stall"],
                new_row["exempt_stall"],
                "admin"
            )
        )

        conn.commit()

        # ======================
        # 同步 player_records
        # ======================

        conn.execute(
            """
            UPDATE player_records
            SET
                role_tag = (
                    SELECT role_tag
                    FROM member_profiles
                    WHERE member_name = ?
                ),
                role_desc = (
                    SELECT role_desc
                    FROM member_profiles
                    WHERE member_name = ?
                ),
                role_rule = (
                    SELECT role_rule
                    FROM member_profiles
                    WHERE member_name = ?
                ),
                role_weight = (
                    SELECT role_weight
                    FROM member_profiles
                    WHERE member_name = ?
                ),
                is_protected = (
                    SELECT is_protected
                    FROM member_profiles
                    WHERE member_name = ?
                ),
                exempt_stall = (
                    SELECT exempt_stall
                    FROM member_profiles
                    WHERE member_name = ?
                )
            WHERE member = ?
            """,
            (
                member_name,
                member_name,
                member_name,
                member_name,
                member_name,
                member_name,
                member_name
            )
        )

        conn.commit()

        # ======================
        # 重新计算风险
        # ======================

        battle_row = conn.execute(
            """
            SELECT id
            FROM battles
            WHERE is_current = 1
            LIMIT 1
            """
        ).fetchone()

        battle_id = (
            battle_row["id"]
            if battle_row
            else 1
        )

        latest_snapshot = conn.execute(
            """
            SELECT snapshot_time
            FROM snapshots
            WHERE is_deleted = 0
            AND battle_id = ?
            ORDER BY snapshot_time DESC
            LIMIT 1
            """,
            (
                battle_id,
            )
        ).fetchone()

        latest_time = (
            latest_snapshot["snapshot_time"]
            if latest_snapshot
            else None
        )

        conn.close()

        if latest_time:

            calculate_risk(
                battle_id,
                latest_time
            )

            sync_member_profiles(
                battle_id,
                latest_time
            )

        return redirect("/identity")

    row = conn.execute(
        """
        SELECT *
        FROM member_profiles
        WHERE member_name = ?
        """,
        (
            member_name,
        )
    ).fetchone()

    conn.close()

    return render_template(
        "identity_edit.html",
        row=row
    )

@app.route("/identity/view/<member_name>")
def identity_view(member_name):

    source = request.args.get("from")
    group_name = request.args.get("group")

    conn = get_conn()

    try:

        profile = conn.execute(
            """
            SELECT *
            FROM member_profiles
            WHERE member_name = ?
            """,
            (
                member_name,
            )
        ).fetchone()

        if not profile:

            return "成员不存在"

        records = conn.execute(
            """
            SELECT
                snapshot_time,
                av,
                bs,
                identity_score,
                trend,
                risk_level
            FROM identity_history
            WHERE member_name = ?
            ORDER BY snapshot_time DESC
            LIMIT 10
            """,
            (
                member_name,
            )
        ).fetchall()

        history_logs = conn.execute(
            """
            SELECT *
            FROM identity_logs
            WHERE member_name = ?
            ORDER BY created_at DESC
            LIMIT 20
            """,
            (
                member_name,
            )
        ).fetchall()

    finally:

        conn.close()

    profile = dict(profile)

    identity_score = float(
        profile.get(
            "identity_score",
            0
        ) or 0
    )

    # =====================
    # 中文映射
    # =====================

    role_map = {
        "member": "普通成员",
        "admin": "管理员",
        "warehouse": "仓库号",
        "core": "核心成员"
    }

    trend_map = {
        "explosive": "爆发增长",
        "up": "持续增长",
        "stable": "稳定",
        "down": "持续下降",
        "dead": "停滞"
    }

    risk_map = {
        "protected": "身份保护",
        "safe": "安全",
        "warning": "警告",
        "danger": "危险",
        "clear": "清理"
    }

    # =====================
    # 趋势分析
    # =====================

    scores = []

    for r in records:

        if r["identity_score"] is not None:

            scores.append(
                float(
                    r["identity_score"]
                )
            )

    if scores:

        current_score = scores[0]

        max_score = max(scores)

        min_score = min(scores)

        score_range = round(
            max_score - min_score,
            1
        )

        change_score = round(
            scores[0] - scores[-1],
            1
        )

        volatility = round(
            max_score - min_score,
            1
        )

        growth_rate = 0

        if scores and scores[-1] != 0:

            growth_rate = round(
                (
                   current_score - scores[-1]
                )
                / abs(scores[-1])
                * 100,
                1
            )

    else:

        current_score = 0
        max_score = 0
        min_score = 0
        change_score = 0
        volatility = 0
        growth_rate = 0

    # =====================
    # 成长跨度
    # =====================

    score_range = round(
        max_score - min_score,
        1
    )

    # =====================
    # 真实波动指数
    # =====================

    jumps = []

    for i in range(len(scores) - 1):

        jumps.append(
            abs(scores[i] - scores[i + 1])
        )

    if jumps:

       volatility = round(
           sum(jumps) / len(jumps),
           1
        )

    else:

        volatility = 0

    # =====================
    # 趋势评级
    # =====================

    if change_score >= 20:

        trend_level = "爆发增长"

    elif change_score >= 10:

        trend_level = "持续增长"

    elif change_score >= -10:

        trend_level = "稳定"

    elif change_score >= -20:

        trend_level = "下滑"

    else:

        trend_level = "崩盘风险"

    profile["risk_name"] = risk_map.get(
        profile.get("risk_level"),
        "未知"
    )

    # =====================
    # V9.3成员画像引擎
    # =====================

    tags = []

    # 成长标签

    if change_score >= 20:
        tags.append("高速成长")

    elif change_score >= 10:
        tags.append("持续成长")

    elif change_score <= -20:
        tags.append("明显下滑")

    # 贡献标签

    bs_value = float(
        profile.get("bs", 0) or 0
    )

    if bs_value >= 70:
        tags.append("高贡献")

    elif bs_value <= 20:
        tags.append("低贡献")

    # 活跃标签

    av_value = float(
        profile.get("av", 0) or 0
    )

    if av_value >= 70:
        tags.append("高活跃")

    elif av_value <= 20:
        tags.append("低活跃")

    # 稳定标签

    if volatility <= 10:
        tags.append("稳定")

    elif volatility >= 30:
        tags.append("波动大")

    # 风险标签

    risk_name = profile.get("risk_name", "")

    if risk_name == "安全":
        tags.append("安全")

    elif risk_name == "警告":
        tags.append("警告")

    elif risk_name == "危险":
        tags.append("危险")

    elif risk_name == "身份保护":
        tags.append("身份保护")

    #最终画像

    member_style = tags

    # =====================
    # V9.4 智能画像引擎
    # =====================

    member_type = "普通成员"
    member_advice = "持续观察"

    if "高速成长" in tags and "高贡献" in tags:

        member_type = "核心培养对象"
        member_advice = "优先培养"

    elif "高贡献" in tags and "高活跃" in tags:

        member_type = "主力战将"
        member_advice = "重点扶持"

    elif "高速成长" in tags:

        member_type = "潜力新星"
        member_advice = "持续培养"

    elif "危险" in tags:

        member_type = "风险成员"
        member_advice = "重点观察"

    elif "警告" in tags:

        member_type = "观察成员"
        member_advice = "跟踪表现"

    elif "低贡献" in tags:

        member_type = "边缘成员"
        member_advice = "限制资源"

    elif "身份保护" in tags:

        member_type = "特殊成员"
        member_advice = "避免误判"

    # =====================
    # V9.5 管理等级引擎
    # =====================

    management_level = "B级"
    management_action = "持续观察"

    if member_type == "核心培养对象":

        management_level = "S级"
        management_action = "重点培养"

    elif member_type == "主力战将":

        management_level = "A级"
        management_action = "重点扶持"

    elif member_type == "潜力新星":

        management_level = "A级"
        management_action = "持续培养"

    elif member_type == "观察成员":

        management_level = "C级"
        management_action = "持续观察"

    elif member_type == "边缘成员":

        management_level = "D级"
        management_action = "限制资源"

    elif member_type == "风险成员":

        management_level = "F级"
        management_action = "进入清理观察"

    # =====================
    # 稳定评级
    # =====================

    if volatility <= 5:

        stability_level = "⭐⭐⭐⭐⭐ 非常稳定"

    elif volatility <= 10:

        stability_level = "⭐⭐⭐⭐ 稳定"

    elif volatility <= 15:

        stability_level = "⭐⭐⭐ 波动明显"

    elif volatility <= 25:

        stability_level = "⭐⭐ 风险较高"

    else:

        stability_level = "⭐ 极不稳定"

    # =====================
    # AI点评
    # =====================

    if change_score >= 20:

        ai_comment = (
            "身份价值持续快速增长，"
            "🌱 潜力成员名单。"
        )

    elif change_score >= 10:

        ai_comment = (
            "近期成长明显，"
            "具备核心成员潜力。"
        )

    elif change_score >= -10:

        ai_comment = (
            "整体表现稳定，"
            "暂时无明显风险。"
        )

    elif change_score >= -20:

        ai_comment = (
            "身份价值出现下滑，"
            "建议持续观察。"
        )

    else:

        ai_comment = (
            "身份价值连续下降，"
            "存在流失风险。"
        )

    # =====================
    # 身份拆解
    # =====================

    profile["score_av"] = round(
        float(profile.get("av", 0)) * 0.6,
        1
    )

    profile["score_bs"] = round(
        float(profile.get("bs", 0)) * 0.6,
        1
    )

    trend_bonus = {
        "explosive": 10,
        "up": 5,
        "stable": 0,
        "down": -5,
        "dead": -10
    }

    role_bonus = {
        "admin": 15,
        "core": 10,
        "warehouse": 5,
        "member": 0
    }

    profile["score_trend"] = trend_bonus.get(
        profile.get("trend"),
        0
    )

    profile["score_role"] = role_bonus.get(
        profile.get("role_tag"),
        0
    )

    profile["score_protect"] = (
        5 if profile.get("is_protected") else 0
    )

    # =====================
    # 身份等级
    # =====================

    if identity_score >= 90:

        profile["grade"] = "S级核心成员"
        profile["advice"] = "优先资源支持"

    elif identity_score >= 70:

        profile["grade"] = "A级骨干成员"
        profile["advice"] = "重点培养"

    elif identity_score >= 50:

        profile["grade"] = "B级稳定成员"
        profile["advice"] = "持续观察"

    elif identity_score >= 30:

        profile["grade"] = "C级观察成员"
        profile["advice"] = "关注活跃变化"

    else:

        profile["grade"] = "D级待淘汰成员"
        profile["advice"] = "考虑清理"

    profile["role_name"] = role_map.get(
        profile.get("role_tag"),
        "普通成员"
    )

    profile["trend_name"] = trend_map.get(
        profile.get("trend"),
        "未知"
    )

    profile["risk_name"] = risk_map.get(
        profile.get("risk_level"),
        "未知"
    )

    # =====================
    # 决策建议
    # =====================

    if profile.get("is_protected"):

        profile["decision_star"] = "★★★★★"
        profile["decision_title"] = "战略保护成员"
        profile["decision_color"] = "purple"
        profile["decision_text"] = "已进入身份保护名单，不参与自动清理。"
        profile["decision_action"] = "长期保留｜资源支持｜禁止清理"

    elif identity_score >= 90:

        profile["decision_star"] = "★★★★★"
        profile["decision_title"] = "核心战力"
        profile["decision_color"] = "green"
        profile["decision_text"] = "贡献与成长表现优秀。"
        profile["decision_action"] = "重点培养｜资源倾斜"

    elif identity_score >= 70:

        profile["decision_star"] = "★★★★☆"
        profile["decision_title"] = "A级骨干"
        profile["decision_color"] = "blue"
        profile["decision_text"] = "具备持续成长空间。"
        profile["decision_action"] = "持续培养"

    elif identity_score >= 50:

        profile["decision_star"] = "★★★☆☆"
        profile["decision_title"] = "稳定成员"
        profile["decision_color"] = "gray"
        profile["decision_text"] = "整体状态正常。"
        profile["decision_action"] = "持续观察"

    elif identity_score >= 30:

        profile["decision_star"] = "★★☆☆☆"
        profile["decision_title"] = "观察成员"
        profile["decision_color"] = "orange"
        profile["decision_text"] = "存在活跃下降风险。"
        profile["decision_action"] = "重点观察"

    else:

        profile["decision_star"] = "★☆☆☆☆"
        profile["decision_title"] = "清理候选"
        profile["decision_color"] = "red"
        profile["decision_text"] = "已接近清理阈值。"
        profile["decision_action"] = "准备清理"

    records_cn = []

    for r in records:

        item = dict(r)

        item["trend_name"] = trend_map.get(
            item["trend"],
            "未知"
        )

        item["risk_name"] = risk_map.get(
            item["risk_level"],
            "未知"
        )

        records_cn.append(item)
    # =====================
    # AI幕僚决策
    # =====================

    ai_decision = None

    member_strategy = {
        "talent":"普通成员",
        "actions":[]
    }

    conn = get_conn()

    try:

        report = build_staff_report(conn)

        for item in report.get(
            "decision_list",
            []
        ):

            if item["member"] == member_name:

                ai_decision = item

                break
    finally:

        conn.close()

    # AI人才画像

    member_strategy = build_member_strategy(
        records_cn[0]
    )

    # =====================
    # 成长履历
    # =====================

    growth_events = []

    if len(scores) >= 2:

        # 晋升A级
        if current_score >= 70:
            growth_events.append(
                "🏅 晋升A级骨干成员"
            )

        # 晋升B级
        elif current_score >= 60:
            growth_events.append(
                "⭐ 晋升B级稳定成员"
            )

        # 摆脱危险
        if records_cn[0]["risk_name"] in ["安全", "身份保护"]:

            for r in records_cn[1:]:

                if r["risk_name"] in ["危险", "清理", "警告"]:

                    growth_events.append(
                        "🛡️ 脱离风险名单"
                    )
                    break

        # 身份值突破
        if current_score >= 60 and min_score < 60:

            growth_events.append(
                "📈 身份值突破60"
            )

        # 爆发增长
        if change_score >= 20:

            growth_events.append(
                "🚀 进入爆发增长阶段"
            )

    if not growth_events:

        growth_events.append(
            "暂无重大成长事件"
        )

    return render_template(
        "identity_view.html",
        profile=profile,
        ai_decision=ai_decision,
        member_strategy=member_strategy,
        source=source,
        group_name=group_name,
        records=records_cn,
        tags=tags,
        history_logs=history_logs,
        current_score=current_score,
        max_score=max_score,
        min_score=min_score,
        score_range=score_range,
        change_score=change_score,
        member_style=member_style,
        member_tags=member_style,
        member_type=member_type,
        member_advice=member_advice,
        management_level=management_level,
        management_action=management_action,
        volatility=volatility,
        growth_rate=growth_rate,
        growth_events=growth_events,
        trend_level=trend_level,
        stability_level=stability_level,
        ai_comment=ai_comment
    )

@app.route("/battles")
def battles():

    conn = get_conn()

    battle_rows = conn.execute("""
        SELECT *
        FROM battles
        ORDER BY id DESC
    """).fetchall()

    battle_stats = {}

    for b in battle_rows:

        snapshot_count = conn.execute("""
            SELECT COUNT(*)
            FROM snapshots
            WHERE battle_id = ?
            AND is_deleted = 0
        """, (b["id"],)).fetchone()[0]

        last_upload = conn.execute("""
            SELECT snapshot_time
            FROM snapshots
            WHERE battle_id = ?
            AND is_deleted = 0
            ORDER BY id DESC
            LIMIT 1
        """, (b["id"],)).fetchone()

        # 成员数量
        member_count = 0

        try:

            if last_upload:

                df = load_snapshot_df(
                    last_upload["snapshot_time"],
                    b["id"]
                )

                member_count = len(df)

        except Exception as e:

            print(
                f"成员数量统计失败 battle={b['id']}:",
                e
            )

        battle_stats[b["id"]] = {

            "snapshot_count": snapshot_count,

            "member_count": member_count,

            "last_upload": (
                last_upload["snapshot_time"]
                if last_upload
                else "-"
            )

        }

    conn.close()

    return render_template(
        "battles.html",
        battles=battle_rows,
        battle_stats=battle_stats
    )

@app.route("/battle/create", methods=["POST"])
def battle_create():

    battle_name = request.form.get("battle_name", "").strip()
    script_type = request.form.get("script_type", "").strip()
    alliance_name = request.form.get("alliance_name", "").strip()

    if not battle_name:
        return redirect("/battles")

    conn = get_conn()

    conn.execute("""
        INSERT INTO battles
        (
            battle_name,
            script_type,
            alliance_name,
            is_current,
            created_at
        )
        VALUES (?, ?, ?, 0, ?)
    """, (
        battle_name,
        script_type,
        alliance_name,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()

    return redirect("/battles")

@app.route("/battle/delete/<int:battle_id>")
def battle_delete(battle_id):

    conn = get_conn()

    # 不允许删除当前战场
    current = conn.execute("""
        SELECT is_current
        FROM battles
        WHERE id=?
    """, (battle_id,)).fetchone()

    if current and current["is_current"]:
        conn.close()
        return redirect("/battles")

    conn.execute("""
        DELETE FROM battles
        WHERE id=?
    """, (battle_id,))

    conn.execute("""
        DELETE FROM snapshots
        WHERE battle_id=?
    """, (battle_id,))

    conn.execute("""
        DELETE FROM player_records
        WHERE battle_id=?
    """, (battle_id,))

    conn.commit()
    conn.close()

    return redirect("/battles")

@app.route("/battle/select/<int:battle_id>")
def battle_select(battle_id):

    conn = get_conn()

    # 清空当前战场
    conn.execute("""
        UPDATE battles
        SET is_current = 0
    """)

    # 设置新战场
    conn.execute("""
        UPDATE battles
        SET is_current = 1
        WHERE id = ?
    """, (battle_id,))

    conn.commit()
    conn.close()

    return redirect("/battles")

@app.route("/snapshot/view/<int:snapshot_id>")
def snapshot_view(snapshot_id):

    conn = get_conn()

    row = conn.execute("""
        SELECT *
        FROM snapshots
        WHERE id = ?
    """, (snapshot_id,)).fetchone()

    conn.close()

    if not row:
        flash("快照不存在", "error")
        return redirect("/snapshots")

    data = json.loads(row["data"])

    return render_template(
        "snapshot_view.html",
        snapshot=row,
        rows=data[:50]
    )       

@app.route(
    "/snapshot/delete/<int:snapshot_id>",
    methods=["POST"]
)

def snapshot_delete(snapshot_id):

    conn = get_conn()

    snapshot = conn.execute(
        """
        SELECT
            id,
            snapshot_time,
            battle_id
        FROM snapshots
        WHERE id = ?
        """,
        (snapshot_id,)
    ).fetchone()

    if not snapshot:

        conn.close()

        flash(
            "快照不存在",
            "error"
        )

        return redirect("/snapshots")

    snapshot_time = snapshot["snapshot_time"]

    battle_id = snapshot["battle_id"]

    # =========================
    # 删除玩家记录
    # =========================

    conn.execute(
        """
        UPDATE player_records
        SET is_deleted = 1
        WHERE snapshot_time = ?
        AND battle_id = ?
        """,
        (
            snapshot_time,
            battle_id
        )
    )

    # =========================
    # 删除快照
    # =========================

    conn.execute(
        """
        UPDATE snapshots
        SET is_deleted = 1
        WHERE id = ?
        """,
        (
            snapshot_id,
        )
    )

    # =========================
    # 清理 compare 缓存
    # =========================

    conn.execute(
        """
        DELETE FROM compare_cache
        WHERE battle_id = ?
        """,
        (
            battle_id,
        )
    )

    conn.commit()

    conn.close()

    flash(
        f"快照已删除：{snapshot_time}",
        "success"
    )

    return redirect("/snapshots")  

# =========================
# V9.2 战场档案库入口
# =========================

@app.route("/archives/players")
def archive_players():
    return render_template(
        "archive_players.html",
        title="人物档案库"
    )


@app.route("/archives/alliances")
def archive_alliances():

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    groups = conn.execute("""
        SELECT
            group_name,
            COUNT(DISTINCT member) AS member_count
        FROM player_records
        WHERE snapshot_time = (
            SELECT MAX(snapshot_time)
            FROM player_records
            WHERE is_deleted = 0
        )
          AND is_deleted = 0
          AND group_name IS NOT NULL
          AND group_name != ''
        GROUP BY group_name
        HAVING COUNT(DISTINCT member) >= 1
        ORDER BY member_count DESC
    """).fetchall()

    conn.close()

    return render_template(
        "archive_alliances.html",
        title="分组驾驶舱",
        groups=groups
    )

@app.route("/archives/group/<group_name>")
def group_detail(group_name):

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    members = conn.execute("""
        SELECT
            member,
            role_tag,
            identity_score,
            risk_level,
            av,
            bs
        FROM player_records
        WHERE snapshot_time = (
            SELECT MAX(snapshot_time)
            FROM player_records
            WHERE is_deleted = 0
        )
          AND is_deleted = 0
          AND group_name = ?
        ORDER BY identity_score DESC
    """, (group_name,)).fetchall()

    conn.close()

    member_count = len(members)

    avg_identity = 0
    if member_count > 0:
        avg_identity = round(
            sum(float(m["identity_score"] or 0) for m in members) / member_count,
            1
        )

    risk_members = [
        m for m in members
        if m["risk_level"] in ["warning", "danger"]
    ]

    leaders = [
        m for m in members
        if m["role_tag"] == "admin"
    ]

    a_count = sum(
        1 for m in members
        if float(m["identity_score"] or 0) >= 70
    )

    return render_template(
        "group_detail.html",
        title="分组详情",
        group_name=group_name,
        members=members,
        member_count=member_count,
        avg_identity=avg_identity,
        risk_count=len(risk_members),
        a_count=a_count,
        leaders=leaders,
        risk_members=risk_members
    )


@app.route("/archives/friends")
def archive_friends():
    return render_template(
        "archive_friends.html",
        title="友盟档案库"
    )

@app.route("/archives/enemies")
def archive_enemies():
    return render_template(
        "archive_enemies.html",
        title="敌军档案库"
    )


@app.route("/archives/events")
def archive_events():
    return render_template(
        "archive_events.html",
        title="战场事件库"
    )


# =========================
# V9.2 AI幕僚中心入口
# =========================

@app.route("/ai/daily")
def ai_daily():

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    members = cur.execute("""
        SELECT
            member_name,
            av,
            bs,
            trend,
            risk_level,
            risk_reason,
            role_tag,
            identity_score,
            is_protected,
            exempt_stall
        FROM member_profiles
    """).fetchall()

    conn.close()

    train_members = []
    watch_members = []
    clean_members = []

    for m in members:
        av = m["av"] or 0
        bs = m["bs"] or 0
        score = m["identity_score"] or 0
        risk = m["risk_level"] or "安全"
        role = m["role_tag"] or "member"
        protected = m["is_protected"] or 0
        exempt_stall = m["exempt_stall"] or 0

        if (
            score >= 65
            and av >= 50
            and bs >= 60
        ):
            train_members.append(m)

        if (
            risk == "danger"
            and protected == 0
            and not (
                av < 20
                and bs < 30
                and role not in ["leader", "admin"]
            )
        ):
            watch_members.append(m)

        if (
            risk == "danger"
            and av < 20
            and bs < 30
            and protected == 0
            and role not in ["leader", "admin"]
        ):
            clean_members.append(m)

            top_train = "、".join(
                [m["member_name"] for m in train_members[:3]]
            )

            top_clean = "\n".join([
                f"{m['member_name']}（{m['risk_reason']}）"
                for m in clean_members[:3]
            ])

            risk_stats = {
                "活跃不足": 0,
                "连续停滞": 0,
                "长期低贡献": 0,
                "综合健康分过低": 0
            }

            for m in watch_members:

                reason = str(m["risk_reason"] or "")

                if "活跃不足" in reason:
                    risk_stats["活跃不足"] += 1

                if "连续停滞" in reason:
                    risk_stats["连续停滞"] += 1

                if "长期低贡献" in reason:
                    risk_stats["长期低贡献"] += 1

                if "综合健康分" in reason:
                 risk_stats["综合健康分过低"] += 1

            risk_report = f"""
            活跃不足：{risk_stats['活跃不足']}人
            连续停滞：{risk_stats['连续停滞']}人
            长期低贡献：{risk_stats['长期低贡献']}人
            综合健康分过低：{risk_stats['综合健康分过低']}人
            """

            summary = f"""
            📊 联盟状态日报

            联盟当前共有 {len(members)} 名成员。

            🌱 重点培养成员
            共发现 {len(train_members)} 人。

            代表成员：
            {top_train}

            👀 重点观察成员
            共发现 {len(watch_members)} 人。

            风险结构分析：

            {risk_report}

            🚨 建议清理成员
            共发现 {len(clean_members)} 人。

            建议优先核查：

            {top_clean}。

            📌 综合评估

            联盟整体运行稳定，
            当前风险成员占比可控，
            建议持续关注观察名单变化。
            """

    return render_template(
        "ai_daily.html",

        member_count=len(members),
        train_count=len(train_members),
        watch_count=len(watch_members),
        clean_count=len(clean_members),

        train_members=train_members[:10],
        watch_members=watch_members[:10],
        clean_members=clean_members[:10],

        summary=summary
    )

@app.route("/ai/weekly")
def ai_weekly():
    return render_template(
        "archive_events.html",
        title="AI周报"
    )


@app.route("/ai/decision")
def ai_decision():
    return render_template(
        "archive_events.html",
        title="AI决策"
    )

@app.route("/usage")
def usage():
    return render_template("usage.html")


@app.route("/export/compare_result")
def export_compare_result():
    if not COMPARE_RESULT_FILE.exists():
        flash("暂无对比结果可导出", "warning")
        return redirect(url_for("compare"))
    return send_file(COMPARE_RESULT_FILE, as_attachment=True, download_name="compare_result.csv")


@app.route("/export/group_summary")
def export_group_summary():
    if not GROUP_SUMMARY_FILE.exists():
        flash("暂无分团统计可导出", "warning")
        return redirect(url_for("compare"))
    return send_file(GROUP_SUMMARY_FILE, as_attachment=True, download_name="group_summary.csv")


@app.route("/export_members")
def export_members():

    df = load_current_battle_members()

    output = io.StringIO()

    df.to_csv(
        output,
        index=False
    )

    output.seek(0)

    return send_file(
        io.BytesIO(
            output.getvalue().encode("utf-8-sig")
        ),
        mimetype="text/csv",
        as_attachment=True,
        download_name="members_export.csv"
    )

@app.route("/staff")
def staff_center():
    conn = sqlite3.connect("data/snapshots.db")
    report = build_staff_report(conn)
    conn.close()

    return render_template(
        "staff_center.html",
        report=report
    )


@app.route("/strategic")
def strategic_center():
    conn = sqlite3.connect("data/snapshots.db")
    report = build_staff_report(conn)
    conn.close()

    return render_template(
        "strategic_center.html",
        report=report,
        title="AI战略推演中心"
    )




@app.route("/leaders/mapping/save", methods=["POST"])
def save_leader_mapping():
    from flask import request, redirect
    from services.v14_leader_mapping_store import (
        upsert_leader_mapping
    )

    group_name = request.form.get("group_name", "").strip()
    leader_name = request.form.get("leader_name", "").strip()
    leader_role = request.form.get("leader_role", "组长").strip()
    note = request.form.get("note", "").strip()
    next_url = request.form.get("next", "/leaders").strip()

    if not next_url.startswith("/leaders"):
        next_url = "/leaders"

    conn = sqlite3.connect("data/snapshots.db")

    upsert_leader_mapping(
        conn,
        group_name=group_name,
        leader_name=leader_name,
        leader_role=leader_role,
        note=note
    )

    conn.close()

    return redirect(next_url)



@app.route("/leaders/mapping/delete", methods=["POST"])
def delete_leader_mapping():
    from flask import request, redirect
    from services.v14_leader_mapping_store import (
        deactivate_leader_mapping
    )

    group_name = request.form.get("group_name", "").strip()
    next_url = request.form.get("next", "/leaders").strip()

    if not next_url.startswith("/leaders"):
        next_url = "/leaders"

    conn = sqlite3.connect("data/snapshots.db")

    deactivate_leader_mapping(
        conn,
        group_name=group_name
    )

    conn.close()

    return redirect(next_url)




@app.route("/leaders/group/<path:group_name>")
def leader_group_risk_detail(group_name):
    from urllib.parse import unquote
    from services.engines.risk_drilldown_engine import (
        build_group_risk_detail_report
    )

    decoded_group_name = unquote(group_name)

    conn = sqlite3.connect("data/snapshots.db")

    report = {
        "v15_group_risk_detail": build_group_risk_detail_report(
            conn,
            decoded_group_name
        )
    }

    conn.close()


    # v15_leader_group_return_url
    return_url = request.args.get("next", "/leaders").strip()

    if (
        not return_url.startswith("/")
        or return_url.startswith("//")
        or return_url.startswith("/logout")
    ):
        return_url = "/leaders"

    report["v15_return_url"] = return_url


    return render_template(
        "leader_group_risk_detail.html",
        report=report,
        title="分组异常人员详情"
    )


@app.route("/leaders/owner/<path:owner_name>")
def leader_owner_detail(owner_name):
    from urllib.parse import unquote
    from services.engines.leader_center_engine import (
        build_leader_center_report
    )
    from services.engines.leader_owner_detail_engine import (
        build_leader_owner_detail_report
    )

    decoded_owner_name = unquote(owner_name)

    conn = sqlite3.connect("data/snapshots.db")
    report = build_staff_report(conn)

    report["v14_leader_center"] = (
        build_leader_center_report(
            conn,
            report
        )
    )

    report["v14_leader_owner_detail"] = (
        build_leader_owner_detail_report(
            report["v14_leader_center"],
            decoded_owner_name
        )
    )

    conn.close()


    # v15_leader_owner_return_url
    return_url = request.args.get("next", "/leaders").strip()

    if (
        not return_url.startswith("/")
        or return_url.startswith("//")
        or return_url.startswith("/logout")
    ):
        return_url = "/leaders"

    report["v15_return_url"] = return_url


    return render_template(
        "leader_owner_detail.html",
        report=report,
        title="负责人详情"
    )





@app.route("/command/action/log", methods=["POST"])
def command_action_log():
    from flask import request, redirect
    from services.v15_command_store import (
        save_command_action_log
    )

    action_key = request.form.get("action_key", "").strip()
    action_label = request.form.get("action_label", "").strip()
    status = request.form.get("status", "").strip()
    note = request.form.get("note", "").strip()
    next_url = request.form.get("next", "/command").strip()

    if (
        next_url != "/command"
        and not next_url.startswith("/command/action/")
    ):
        next_url = "/command"

    conn = sqlite3.connect("data/snapshots.db")

    save_command_action_log(
        conn,
        action_key=action_key,
        action_label=action_label,
        status=status,
        note=note
    )

    conn.close()

    return redirect(next_url)


@app.route("/command/action/<path:action_key>")
def command_action_detail(action_key):
    from urllib.parse import unquote
    from services.engines.leader_center_engine import (
        build_leader_center_report
    )
    from services.engines.command_center_engine import (
        build_command_center_report
    )
    from services.v15_command_store import (
        load_command_action_logs
    )
    from services.engines.command_action_engine import (
        build_command_action_report
    )
    from services.v15_command_store import (
        load_command_action_logs_by_key
    )

    decoded_action_key = unquote(action_key)

    conn = sqlite3.connect("data/snapshots.db")
    report = build_staff_report(conn)

    report["v14_leader_center"] = (
        build_leader_center_report(
            conn,
            report
        )
    )

    report["v15_command_center"] = (
        build_command_center_report(
            report,
            report["v14_leader_center"]
        )
    )

    report["v15_command_action"] = (
        build_command_action_report(
            report["v15_command_center"],
            decoded_action_key
        )
    )

    report["v15_command_action_logs"] = load_command_action_logs_by_key(
        conn,
        decoded_action_key,
        limit=20
    )

    conn.close()

    return render_template(
        "command_action_detail.html",
        report=report,
        title="指挥动作详情"
    )


@app.route("/command")
def command_center():
    from services.engines.leader_center_engine import (
        build_leader_center_report
    )
    from services.engines.command_center_engine import (
        build_command_center_report
    )
    from services.v15_command_store import (
        load_command_action_logs
    )
    from services.engines.risk_drilldown_engine import (
        build_risk_drilldown_report,
        attach_risk_members_to_groups
    )

    conn = sqlite3.connect("data/snapshots.db")
    report = build_staff_report(conn)

    report["v14_leader_center"] = (
        build_leader_center_report(
            conn,
            report
        )
    )

    report["v15_command_center"] = (
        build_command_center_report(
            report,
            report["v14_leader_center"]
        )
    )

    report["v15_risk_drilldown"] = build_risk_drilldown_report(conn)

    attach_risk_members_to_groups(
        report["v15_command_center"].get("high_pressure_groups", []),
        report["v15_risk_drilldown"],
        limit_per_group=5
    )


    report["v15_command_logs"] = load_command_action_logs(
        conn,
        limit=12
    )

    conn.close()

    return render_template(
        "command_center.html",
        report=report,
        title="盟务指挥中枢"
    )


@app.route("/leaders")
def leader_center():
    from services.engines.risk_drilldown_engine import (
        build_risk_drilldown_report,
        attach_risk_members_to_groups
    )
    from flask import request
    from services.engines.leader_center_engine import (
        build_leader_center_report
    )
    from services.engines.leader_filter_engine import (
        build_leader_filter_report
    )

    conn = sqlite3.connect("data/snapshots.db")
    report = build_staff_report(conn)

    report["v14_leader_center"] = (
        build_leader_center_report(
            conn,
            report
        )
    )

    report["v15_risk_drilldown"] = build_risk_drilldown_report(conn)

    attach_risk_members_to_groups(
        report["v14_leader_center"].get("high_pressure_groups", []),
        report["v15_risk_drilldown"],
        limit_per_group=5
    )


    leader_filters = {
        "pressure": request.args.get("pressure", "all"),
        "responsibility": request.args.get("responsibility", "all"),
        "sort": request.args.get("sort", "pressure_desc"),
        "keyword": request.args.get("keyword", ""),
    }

    report["v14_leader_filter"] = (
        build_leader_filter_report(
            report["v14_leader_center"],
            leader_filters
        )
    )


    # v15_leader_filter_cards_sync
    # 统一筛选统计与卡片明细使用的数据源，避免“筛选显示有结果，但卡片为空”
    _leader_filter = report.get("v14_leader_filter", {}) or {}
    _leader_center = report.get("v14_leader_center", {}) or {}

    _filter_cards = (
        _leader_filter.get("filtered_groups")
        or _leader_filter.get("groups")
        or _leader_filter.get("items")
        or _leader_center.get("filtered_groups")
        or _leader_center.get("groups")
        or []
    )

    if "v14_leader_center" in report:
        report["v14_leader_center"]["filter_cards"] = _filter_cards
        report["v14_leader_center"]["filtered_groups"] = _filter_cards



    # v15_leader_filter_cards_sync_v2
    # 统一筛选统计与卡片明细数据源：
    # leader_center_engine 当前真实分组卡片来源是 group_cards，
    # 不是 filtered_groups / groups。
    from flask import request as _v15_request

    _leader_center = report.get("v14_leader_center", {}) or {}
    _leader_filter = report.get("v14_leader_filter", {}) or {}

    def _is_group_card_list(value):
        if not isinstance(value, list):
            return False
        if not value:
            return True
        first = value[0]
        return isinstance(first, dict) and (
            "group_name" in first
            or "leader_display" in first
            or "pressure_score" in first
        )

    _cards = []

    # 优先使用筛选引擎已经算好的结果
    for _key in [
        "filtered_groups",
        "filtered_cards",
        "filter_cards",
        "matched_groups",
        "result_groups",
        "group_cards",
        "cards",
        "results",
        "items",
        "groups",
    ]:
        _value = _leader_filter.get(_key)
        if _is_group_card_list(_value):
            _cards = list(_value)
            break

    # 如果筛选引擎没有返回卡片，就使用组长中心真实卡片源
    if not _cards:
        _cards = list(
            _leader_center.get("group_cards")
            or _leader_center.get("filtered_groups")
            or _leader_center.get("groups")
            or []
        )

    # 兜底手动筛选，确保页面卡片与筛选条件一致
    _pressure = (
        _v15_request.args.get("pressure")
        or _v15_request.args.get("pressure_status")
        or _v15_request.args.get("pressure_level")
        or "all"
    )

    _responsibility = (
        _v15_request.args.get("responsibility")
        or _v15_request.args.get("leader_status")
        or _v15_request.args.get("owner_status")
        or "all"
    )

    _sort = (
        _v15_request.args.get("sort")
        or _v15_request.args.get("sort_by")
        or "pressure_desc"
    )

    _q = (
        _v15_request.args.get("q")
        or _v15_request.args.get("keyword")
        or _v15_request.args.get("search")
        or ""
    ).strip()

    def _text(value):
        return str(value or "").strip()

    def _is_unassigned(card):
        leader = _text(
            card.get("leader_display")
            or card.get("leader_name")
            or card.get("owner")
        )
        return leader in ("", "-", "待指定", "待指定组长")

    def _is_manual(card):
        source = _text(card.get("leader_source") or card.get("source"))
        note = _text(card.get("leader_note") or card.get("note"))
        return "手动" in source or "手动" in note or bool(card.get("leader_name"))

    def _is_auto(card):
        source = _text(card.get("leader_source") or card.get("source"))
        return "自动" in source or "识别" in source

    def _is_manager_proxy(card):
        role = _text(card.get("leader_role") or card.get("role"))
        return "代管" in role or "管理" in role

    def _pressure_label(card):
        return _text(card.get("pressure_label") or card.get("pressure_status"))

    def _pressure_score(card):
        try:
            return float(card.get("pressure_score") or card.get("pressure") or 0)
        except Exception:
            return 0.0

    def _danger_count(card):
        try:
            return int(card.get("danger_count") or card.get("danger_members") or 0)
        except Exception:
            return 0

    def _pending_count(card):
        try:
            return int(card.get("pending_count") or card.get("pending_task_count") or 0)
        except Exception:
            return 0

    if _pressure not in ("all", "全部", ""):
        if _pressure in ("high", "high_pressure", "高压"):
            _cards = [c for c in _cards if _pressure_label(c) == "高压"]
        elif _pressure in ("normal", "正常"):
            _cards = [c for c in _cards if _pressure_label(c) == "正常"]
        elif _pressure in ("watch", "attention", "关注"):
            _cards = [c for c in _cards if _pressure_label(c) == "关注"]

    if _responsibility not in ("all", "全部", ""):
        if _responsibility in ("unassigned", "pending", "待指定", "待指定组长"):
            _cards = [c for c in _cards if _is_unassigned(c)]
        elif _responsibility in ("manual", "manual_assigned", "手动指定"):
            _cards = [c for c in _cards if _is_manual(c)]
        elif _responsibility in ("auto", "auto_detected", "自动识别"):
            _cards = [c for c in _cards if _is_auto(c)]
        elif _responsibility in ("manager_proxy", "manager", "管理代管"):
            _cards = [c for c in _cards if _is_manager_proxy(c)]

    if _q:
        _cards = [
            c for c in _cards
            if _q in _text(c.get("group_name"))
            or _q in _text(c.get("leader_display"))
            or _q in _text(c.get("leader_name"))
        ]

    if _sort in ("pressure_desc", "压力从高到低", "pressure_high"):
        _cards = sorted(_cards, key=_pressure_score, reverse=True)
    elif _sort in ("pressure_asc", "压力从低到高", "pressure_low"):
        _cards = sorted(_cards, key=_pressure_score)
    elif _sort in ("danger_desc", "危险最多"):
        _cards = sorted(_cards, key=_danger_count, reverse=True)
    elif _sort in ("pending_desc", "待反馈最多"):
        _cards = sorted(_cards, key=_pending_count, reverse=True)

    _leader_center["filter_cards"] = _cards
    _leader_center["filtered_groups"] = _cards

    if isinstance(_leader_filter, dict):
        _leader_filter["filter_cards"] = _cards
        _leader_filter["filtered_groups"] = _cards
        _leader_filter["matched_count"] = len(_cards)
        _leader_filter["matched_groups"] = len(_cards)
        _leader_filter["total_matched"] = len(_cards)

    report["v14_leader_center"] = _leader_center
    report["v14_leader_filter"] = _leader_filter


    conn.close()

    return render_template(
        "leader_center.html",
        report=report,
        title="组长协同驾驶舱"
    )


@app.route("/tasks/detail/<path:task_key>")
def task_detail(task_key):
    from flask import request
    from urllib.parse import unquote
    from services.v12_feedback_store import (
        load_feedback_logs_by_task_key
    )
    from services.engines.task_detail_engine import (
        build_task_detail_report
    )

    decoded_task_key = unquote(task_key)

    conn = sqlite3.connect("data/snapshots.db")
    report = build_staff_report(conn)

    logs = load_feedback_logs_by_task_key(
        conn,
        decoded_task_key
    )

    conn.close()

    report["v13_task_detail"] = (
        build_task_detail_report(
            report,
            decoded_task_key,
            logs
        )
    )

    return_url = request.args.get("next", "/tasks").strip()

    if (
        return_url != "/tasks"
        and not return_url.startswith("/tasks?")
        and not return_url.startswith("/tasks#")
    ):
        return_url = "/tasks"

    report["v13_task_return_url"] = return_url

    return render_template(
        "task_detail.html",
        report=report,
        title="任务详情"
    )


@app.route("/tasks")
def task_center():
    from flask import request
    from services.engines.task_filter_engine import (
        build_task_filter_report
    )

    conn = sqlite3.connect("data/snapshots.db")
    report = build_staff_report(conn)
    conn.close()

    task_filters = {
        "priority": request.args.get("priority", "all"),
        "status": request.args.get("status", "all"),
        "phase": request.args.get("phase", "all"),
        "owner": request.args.get("owner", "all"),
        "preset": request.args.get("preset", "all"),
        "sort": request.args.get("sort", "smart"),
    }

    report["v13_task_filter"] = (
        build_task_filter_report(
            report,
            task_filters
        )
    )

    return render_template(
        "task_center.html",
        report=report,
        title="战场任务协同中心"
    )


@app.route("/strategic/feedback", methods=["POST"])
def strategic_feedback():
    from flask import request, redirect
    from services.v12_feedback_store import save_execution_feedback

    allowed_status = {
        "pending",
        "confirmed",
        "completed",
        "protected",
        "ignored",
        "failed",
    }

    task_key = request.form.get("task_key", "").strip()
    status = request.form.get("status", "").strip()
    feedback_note = request.form.get("feedback_note", "").strip()
    next_url = request.form.get("next", "/strategic").strip()

    if (
        next_url not in ("/strategic", "/tasks")
        and not next_url.startswith("/tasks?")
        and not next_url.startswith("/tasks#")
        and not next_url.startswith("/tasks/detail/")
    ):
        next_url = "/strategic"

    if status not in allowed_status:
        return redirect(next_url)

    conn = sqlite3.connect("data/snapshots.db")

    report = build_staff_report(conn)

    snapshot_key = report.get("current_v11_snapshot_key")
    fb = report.get("v12_execution_feedback", {}) or {}
    tasks = fb.get("tasks", []) or []

    target_task = None

    for task in tasks:
        if task.get("task_key") == task_key:
            target_task = task
            break

    if snapshot_key and target_task:
        save_execution_feedback(
            conn,
            snapshot_key,
            target_task,
            status,
            feedback_note
        )

    conn.close()

    return redirect(next_url)
    
@app.errorhandler(500)
def error_500(e):
    return f"服务器错误：{str(e)}", 500


# =========================
# 启动
# =========================
init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)


# =========================
# V15.5 战场档案库基础闭环
# =========================

@app.route("/archives")
def v155_archive_home():
    import sqlite3
    from flask import render_template
    from services.v155_archive_store import (
        get_archive_overview,
        list_events,
    )

    conn = sqlite3.connect("data/snapshots.db")
    conn.row_factory = sqlite3.Row

    overview = get_archive_overview(conn)
    recent_events = list_events(conn, limit=5)

    conn.close()

    return render_template(
        "archive_home.html",
        overview=overview,
        recent_events=recent_events,
        title="战场档案库",
    )


@app.route("/archives/players")
@app.route("/archive_players")
def v155_archive_players():
    import sqlite3
    from flask import render_template, request
    from services.v155_archive_store import list_players

    q = request.args.get("q", "").strip()

    conn = sqlite3.connect("data/snapshots.db")
    conn.row_factory = sqlite3.Row

    players = list_players(conn, q)

    conn.close()

    return render_template(
        "archive_players.html",
        players=players,
        q=q,
        title="人物档案",
    )


@app.route("/archives/events")
@app.route("/archive_events")
def v155_archive_events():
    import sqlite3
    from flask import render_template, request
    from services.v155_archive_store import list_events

    q = request.args.get("q", "").strip()

    conn = sqlite3.connect("data/snapshots.db")
    conn.row_factory = sqlite3.Row

    events = list_events(conn, q)

    conn.close()

    return render_template(
        "archive_events.html",
        events=events,
        q=q,
        title="战场事件",
    )


@app.route("/archives/events/save", methods=["POST"])
def v155_archive_event_save():
    import sqlite3
    from flask import request, redirect
    from services.v155_archive_store import save_event

    title = request.form.get("title", "").strip()

    if not title:
        return redirect("/archives/events")

    conn = sqlite3.connect("data/snapshots.db")
    conn.row_factory = sqlite3.Row

    event_id = save_event(conn, dict(request.form))

    conn.close()

    return redirect(f"/archives/events/{event_id}")


@app.route("/archives/events/<int:event_id>")
def v155_archive_event_detail(event_id):
    import sqlite3
    from flask import render_template
    from services.v155_archive_store import get_event

    conn = sqlite3.connect("data/snapshots.db")
    conn.row_factory = sqlite3.Row

    event = get_event(conn, event_id)

    conn.close()

    return render_template(
        "archive_event_detail.html",
        event=event,
        title="战场事件详情",
    )


@app.route("/archives/events/<int:event_id>/update", methods=["POST"])
def v155_archive_event_update(event_id):
    import sqlite3
    from flask import request, redirect
    from services.v155_archive_store import update_event

    conn = sqlite3.connect("data/snapshots.db")
    conn.row_factory = sqlite3.Row

    update_event(conn, event_id, dict(request.form))

    conn.close()

    return redirect(f"/archives/events/{event_id}")


@app.route("/archives/friends")
@app.route("/archives/allies")
@app.route("/archive_friends")
@app.route("/archive_alliances")
def v155_archive_friends():
    import sqlite3
    from flask import render_template
    from services.v155_archive_store import list_alliances

    conn = sqlite3.connect("data/snapshots.db")
    conn.row_factory = sqlite3.Row

    alliances = list_alliances(conn)

    conn.close()

    return render_template(
        "archive_friends.html",
        alliances=alliances,
        title="友盟档案",
    )


@app.route("/archives/friends/save", methods=["POST"])
@app.route("/archives/allies/save", methods=["POST"])
def v155_archive_friend_save():
    import sqlite3
    from flask import request, redirect
    from services.v155_archive_store import save_alliance

    name = request.form.get("name", "").strip()

    if not name:
        return redirect("/archives/friends")

    conn = sqlite3.connect("data/snapshots.db")
    conn.row_factory = sqlite3.Row

    save_alliance(conn, dict(request.form))

    conn.close()

    return redirect("/archives/friends")


@app.route("/archives/enemies")
@app.route("/archive_enemies")
def v155_archive_enemies():
    import sqlite3
    from flask import render_template
    from services.v155_archive_store import list_enemies

    conn = sqlite3.connect("data/snapshots.db")
    conn.row_factory = sqlite3.Row

    enemies = list_enemies(conn)

    conn.close()

    return render_template(
        "archive_enemies.html",
        enemies=enemies,
        title="敌军档案",
    )


@app.route("/archives/enemies/save", methods=["POST"])
def v155_archive_enemy_save():
    import sqlite3
    from flask import request, redirect
    from services.v155_archive_store import save_enemy

    name = request.form.get("name", "").strip()

    if not name:
        return redirect("/archives/enemies")

    conn = sqlite3.connect("data/snapshots.db")
    conn.row_factory = sqlite3.Row

    save_enemy(conn, dict(request.form))

    conn.close()

    return redirect("/archives/enemies")



# =========================
# V15.5 档案库旧入口接管与显示修复 A1
# =========================

@app.route("/archive_enemies/save", methods=["POST"])
def v155_archive_enemy_save_legacy_a1():
    return v155_archive_enemy_save()


@app.route("/archive_friends/save", methods=["POST"])
@app.route("/archive_alliances/save", methods=["POST"])
def v155_archive_friend_save_legacy_a1():
    return v155_archive_friend_save()


@app.route("/archive_events/save", methods=["POST"])
def v155_archive_event_save_legacy_a1():
    return v155_archive_event_save()


def _v155_archive_route_takeover_a1():
    """
    接管历史旧入口，避免旧 route 渲染新模板但不传数据，
    导致保存成功后页面仍显示为空。
    """
    route_targets = {
        "/archives": v155_archive_home,

        "/archives/players": v155_archive_players,
        "/archive_players": v155_archive_players,

        "/archives/events": v155_archive_events,
        "/archive_events": v155_archive_events,
        "/archives/events/save": v155_archive_event_save,
        "/archive_events/save": v155_archive_event_save_legacy_a1,

        "/archives/friends": v155_archive_friends,
        "/archives/allies": v155_archive_friends,
        "/archive_friends": v155_archive_friends,
        "/archive_alliances": v155_archive_friends,
        "/archives/friends/save": v155_archive_friend_save,
        "/archives/allies/save": v155_archive_friend_save,
        "/archive_friends/save": v155_archive_friend_save_legacy_a1,
        "/archive_alliances/save": v155_archive_friend_save_legacy_a1,

        "/archives/enemies": v155_archive_enemies,
        "/archive_enemies": v155_archive_enemies,
        "/archives/enemies/save": v155_archive_enemy_save,
        "/archive_enemies/save": v155_archive_enemy_save_legacy_a1,
    }

    for rule in list(app.url_map.iter_rules()):
        target = route_targets.get(rule.rule)
        if target:
            app.view_functions[rule.endpoint] = target


_v155_archive_route_takeover_a1()


# =========================
# V15.5-A2 友盟 / 敌军详情与编辑路由
# =========================

@app.route("/archives/friends/<int:alliance_id>")
@app.route("/archive_friends/<int:alliance_id>")
@app.route("/archive_alliances/<int:alliance_id>")
def v155_archive_friend_detail_a2(alliance_id):
    import sqlite3
    from flask import render_template
    from services.v155_archive_store import get_alliance

    conn = sqlite3.connect("data/snapshots.db")
    conn.row_factory = sqlite3.Row

    alliance = get_alliance(conn, alliance_id)

    conn.close()

    return render_template(
        "archive_friend_detail.html",
        alliance=alliance,
        title="友盟档案详情",
    )


@app.route("/archives/friends/<int:alliance_id>/update", methods=["POST"])
@app.route("/archive_friends/<int:alliance_id>/update", methods=["POST"])
@app.route("/archive_alliances/<int:alliance_id>/update", methods=["POST"])
def v155_archive_friend_update_a2(alliance_id):
    import sqlite3
    from flask import request, redirect
    from services.v155_archive_store import update_alliance

    conn = sqlite3.connect("data/snapshots.db")
    conn.row_factory = sqlite3.Row

    update_alliance(conn, alliance_id, dict(request.form))

    conn.close()

    return redirect(f"/archives/friends/{alliance_id}")


@app.route("/archives/enemies/<int:enemy_id>")
@app.route("/archive_enemies/<int:enemy_id>")
def v155_archive_enemy_detail_a2(enemy_id):
    import sqlite3
    from flask import render_template
    from services.v155_archive_store import get_enemy

    conn = sqlite3.connect("data/snapshots.db")
    conn.row_factory = sqlite3.Row

    enemy = get_enemy(conn, enemy_id)

    conn.close()

    return render_template(
        "archive_enemy_detail.html",
        enemy=enemy,
        title="敌军档案详情",
    )


@app.route("/archives/enemies/<int:enemy_id>/update", methods=["POST"])
@app.route("/archive_enemies/<int:enemy_id>/update", methods=["POST"])
def v155_archive_enemy_update_a2(enemy_id):
    import sqlite3
    from flask import request, redirect
    from services.v155_archive_store import update_enemy

    conn = sqlite3.connect("data/snapshots.db")
    conn.row_factory = sqlite3.Row

    update_enemy(conn, enemy_id, dict(request.form))

    conn.close()

    return redirect(f"/archives/enemies/{enemy_id}")


# =========================
# V15.5-A3 战场事件关联对象路由
# =========================

def v155_archive_event_detail_a3(event_id):
    import sqlite3
    from flask import render_template
    from services.v155_archive_store import (
        get_event,
        list_event_relations,
    )

    conn = sqlite3.connect("data/snapshots.db")
    conn.row_factory = sqlite3.Row

    event = get_event(conn, event_id)
    relations = list_event_relations(conn, event_id)

    conn.close()

    return render_template(
        "archive_event_detail.html",
        event=event,
        relations=relations,
        title="战场事件详情",
    )


@app.route("/archive_events/<int:event_id>")
def v155_archive_event_detail_legacy_a3(event_id):
    return v155_archive_event_detail_a3(event_id)


@app.route("/archives/events/<int:event_id>/relations/save", methods=["POST"])
@app.route("/archive_events/<int:event_id>/relations/save", methods=["POST"])
def v155_archive_event_relation_save_a3(event_id):
    import sqlite3
    from flask import request, redirect
    from services.v155_archive_store import save_event_relation

    conn = sqlite3.connect("data/snapshots.db")
    conn.row_factory = sqlite3.Row

    save_event_relation(conn, event_id, dict(request.form))

    conn.close()

    return redirect(f"/archives/events/{event_id}#relations")


@app.route("/archives/events/<int:event_id>/relations/<int:relation_id>/delete", methods=["POST"])
@app.route("/archive_events/<int:event_id>/relations/<int:relation_id>/delete", methods=["POST"])
def v155_archive_event_relation_delete_a3(event_id, relation_id):
    import sqlite3
    from flask import redirect
    from services.v155_archive_store import delete_event_relation

    conn = sqlite3.connect("data/snapshots.db")
    conn.row_factory = sqlite3.Row

    delete_event_relation(conn, event_id, relation_id)

    conn.close()

    return redirect(f"/archives/events/{event_id}#relations")


def _v155_archive_event_detail_takeover_a3():
    """
    接管原 /archives/events/<id> 详情路由，
    让详情页可以拿到 relations 数据。
    """
    for rule in list(app.url_map.iter_rules()):
        if rule.rule == "/archives/events/<int:event_id>":
            app.view_functions[rule.endpoint] = v155_archive_event_detail_a3


_v155_archive_event_detail_takeover_a3()


# =========================
# V15.5-A3.2 档案全局检索路由
# =========================

@app.route("/archives/search")
@app.route("/archive_search")
def v155_archive_search_a32():
    import sqlite3
    from flask import render_template, request
    from services.v155_archive_store import search_archive_global

    q = request.args.get("q", "").strip()

    conn = sqlite3.connect("data/snapshots.db")
    conn.row_factory = sqlite3.Row

    result = search_archive_global(conn, q)

    conn.close()

    return render_template(
        "archive_search.html",
        q=q,
        result=result,
        title="档案检索中枢",
    )


# =========================
# V15.5-A3.4 分组档案独立占位页
# =========================

@app.route("/archives/groups")
@app.route("/archive_groups")
def v155_archive_groups_a34():
    from flask import render_template

    return render_template(
        "archive_groups.html",
        title="分组档案",
    )



# =========================
# V15.5-S0 基础安全日志与异常检测
# =========================

@app.before_request
def v155_security_before_request():
    import time
    from flask import request, g
    from services.v155_security_store import is_static_path

    g.v155_security_start_time = time.time()

    if is_static_path(request.path):
        g.v155_security_skip = True
    else:
        g.v155_security_skip = False


@app.after_request
def v155_security_after_request(response):
    import time
    import sqlite3
    from flask import request, g
    from services.v155_security_store import (
        get_client_ip,
        detect_suspicious,
        save_access_log,
        cleanup_security_logs,
        is_static_path,
    )

    try:
        if getattr(g, "v155_security_skip", False):
            return response

        if is_static_path(request.path):
            return response

        start_time = getattr(g, "v155_security_start_time", time.time())
        duration_ms = round((time.time() - start_time) * 1000, 2)

        ip = get_client_ip(request.headers, request.remote_addr)
        method = request.method
        path = request.path
        query_string = request.query_string.decode("utf-8", errors="ignore")
        user_agent = request.headers.get("User-Agent", "")
        status_code = response.status_code

        conn = sqlite3.connect("data/snapshots.db")
        conn.row_factory = sqlite3.Row

        if path.startswith("/security/"):
            # V15.5-S2.5 管理员安全后台访问降噪：
            # 安全后台访问仍记录，但不参与异常攻击判断，避免管理员自查污染风险统计。
            is_suspicious, reason = False, ""
        else:
            is_suspicious, reason = detect_suspicious(
                conn=conn,
                ip=ip,
                method=method,
                path=path,
                query_string=query_string,
                user_agent=user_agent,
                status_code=status_code,
            )

        save_access_log(
            conn=conn,
            ip=ip,
            method=method,
            path=path,
            query_string=query_string,
            user_agent=user_agent,
            status_code=status_code,
            duration_ms=duration_ms,
            is_suspicious=is_suspicious,
            suspicious_reason=reason,
        )

        # 每 100 条请求触发一次简单清理，避免日志无限增长
        cur = conn.execute("SELECT COUNT(*) AS c FROM v155_security_access_logs")
        total = int(cur.fetchone()["c"] or 0)

        if total % 100 == 0:
            cleanup_security_logs(conn, keep_days=7)

        conn.close()

    except Exception as e:
        print("⚠️ V15.5-S0 security log error:", e)

    return response





# =========================
# V15.5-S1.1 clean security routes
# =========================

@app.route("/security/logs")
def v155_security_logs():
    import sqlite3
    from pathlib import Path
    from flask import request, render_template, abort
    from services.v155_security_store import get_security_report_paginated

    token_path = Path("data/security_admin_token.txt")
    saved_token = token_path.read_text().strip() if token_path.exists() else ""

    input_token = request.args.get("token", "").strip()
    cookie_token = request.cookies.get("v155_security_admin", "").strip()

    if not saved_token or (
        input_token != saved_token
        and cookie_token != saved_token
    ):
        abort(403)

    conn = sqlite3.connect("data/snapshots.db")
    conn.row_factory = sqlite3.Row

    try:
        page = int(request.args.get("page", "1") or 1)
    except Exception:
        page = 1

    report = get_security_report_paginated(conn, page=page, per_page=30)

    conn.close()

    return render_template(
        "security_logs.html",
        report=report,
        title="安全日志",
    )


@app.route("/security/login", methods=["GET", "POST"])
def v155_security_login():
    from pathlib import Path
    from flask import request, render_template, redirect, make_response

    token_path = Path("data/security_admin_token.txt")
    saved_token = token_path.read_text().strip() if token_path.exists() else ""

    error = ""

    if request.method == "POST":
        input_token = request.form.get("token", "").strip()

        if saved_token and input_token == saved_token:
            try:
                v155_record_security_admin_action(
                    "security_login",
                    "安全后台登录",
                    "success",
                    "管理员 token 登录成功",
                )
            except Exception:
                pass

            resp = make_response(redirect("/security/logs"))
            resp.set_cookie(
                "v155_security_admin",
                saved_token,
                max_age=60 * 60 * 12,
                httponly=True,
                samesite="Strict",
            )
            return resp

        error = "安全 token 错误，请重新输入。"

    return render_template(
        "security_login.html",
        error=error,
        title="安全后台登录",
    )





@app.route("/security/ip")
def v155_security_ip_detail():
    import sqlite3
    from pathlib import Path
    from flask import request, render_template, abort
    from services.v155_security_store import get_ip_detail_report

    token_path = Path("data/security_admin_token.txt")
    saved_token = token_path.read_text().strip() if token_path.exists() else ""

    input_token = request.args.get("token", "").strip()
    cookie_token = request.cookies.get("v155_security_admin", "").strip()

    if not saved_token or (
        input_token != saved_token
        and cookie_token != saved_token
    ):
        abort(403)

    ip = request.args.get("ip", "").strip()

    if not ip:
        abort(400)

    conn = sqlite3.connect("data/snapshots.db")
    conn.row_factory = sqlite3.Row

    report = get_ip_detail_report(conn, ip)

    conn.close()

    return render_template(
        "security_ip_detail.html",
        report=report,
        title="IP访问明细",
    )


@app.route("/security/logout")
def v155_security_logout():
    from flask import redirect, make_response

    resp = make_response(redirect("/security/login"))
    resp.delete_cookie("v155_security_admin")
    return resp



# =========================
# V15.5-S2 runtime security guard
# =========================

@app.before_request
def v155_runtime_security_guard_before_request():
    import sqlite3
    from flask import request
    from services.v155_runtime_guard import (
        get_client_ip,
        check_ip_blocklist,
        check_read_only,
        check_search_quota,
    )

    path = request.path or ""

    if path.startswith("/static/"):
        return None

    if path.startswith("/favicon"):
        return None

    if path.startswith("/security/"):
        return None

    ip = get_client_ip(request)
    method = request.method or "GET"
    query_string = request.query_string.decode("utf-8", errors="ignore")
    user_agent = request.headers.get("User-Agent", "")

    if path.startswith("/security/logs") and "token=" in query_string:
        query_string = "[hidden]"

    conn = sqlite3.connect("data/snapshots.db")
    conn.row_factory = sqlite3.Row

    try:
        ok, reason, status_code = check_ip_blocklist(
            conn,
            ip=ip,
            method=method,
            path=path,
            query_string=query_string,
            user_agent=user_agent,
        )

        if not ok:
            return (
                "访问已被安全策略拦截。",
                status_code,
            )

        ok, reason, status_code = check_read_only(
            conn,
            ip=ip,
            method=method,
            path=path,
            query_string=query_string,
            user_agent=user_agent,
        )

        if not ok:
            return (
                "档案库当前处于只读保护模式，写入请求已被安全闸门拦截。",
                status_code,
            )

        ok, reason, status_code = check_search_quota(
            conn,
            ip=ip,
            method=method,
            path=path,
            query_string=query_string,
            user_agent=user_agent,
        )

        if not ok:
            return (
                "搜索访问过于频繁，已触发后端安全额度保护。请稍后再试。",
                status_code,
            )

    finally:
        conn.close()

    return None



@app.route("/security/guard", methods=["GET", "POST"])
def v155_security_guard_console():
    import sqlite3
    from pathlib import Path
    from flask import request, render_template, abort, redirect
    from services.v155_runtime_guard import (
        build_guard_report,
        update_guard_config,
        add_whitelist_ip,
        remove_whitelist_ip,
    )

    token_path = Path("data/security_admin_token.txt")
    saved_token = token_path.read_text().strip() if token_path.exists() else ""

    input_token = request.args.get("token", "").strip()
    cookie_token = request.cookies.get("v155_security_admin", "").strip()

    if not saved_token or (
        input_token != saved_token
        and cookie_token != saved_token
    ):
        abort(403)

    conn = sqlite3.connect("data/snapshots.db")
    conn.row_factory = sqlite3.Row

    if request.method == "POST":
        action = request.form.get("action", "").strip()

        if action == "set_read_only":
            value = request.form.get("archive_read_only", "0").strip()
            update_guard_config(conn, "archive_read_only", value)

        elif action == "set_quota":
            enabled = request.form.get("search_quota_enabled", "0").strip()
            limit = request.form.get("daily_search_limit", "120").strip()

            update_guard_config(conn, "search_quota_enabled", enabled)
            update_guard_config(conn, "daily_search_limit", limit)

        elif action == "add_whitelist":
            ip = request.form.get("ip", "").strip()
            note = request.form.get("note", "").strip()
            add_whitelist_ip(conn, ip, note)

        elif action == "remove_whitelist":
            ip = request.form.get("ip", "").strip()
            remove_whitelist_ip(conn, ip)

        conn.close()

        return redirect("/security/guard")

    report = build_guard_report(conn)

    conn.close()

    return render_template(
        "security_guard.html",
        report=report,
        title="安全闸门",
    )



@app.route("/security/cleanup", methods=["GET", "POST"])
def v155_security_cleanup():
    import sqlite3
    from pathlib import Path
    from flask import request, render_template, abort
    from services.v155_security_store import (
        build_security_cleanup_report,
        cleanup_security_logs,
    )

    token_path = Path("data/security_admin_token.txt")
    saved_token = token_path.read_text().strip() if token_path.exists() else ""

    input_token = request.args.get("token", "").strip()
    cookie_token = request.cookies.get("v155_security_admin", "").strip()

    if not saved_token or (
        input_token != saved_token
        and cookie_token != saved_token
    ):
        abort(403)

    conn = sqlite3.connect("data/snapshots.db")
    conn.row_factory = sqlite3.Row

    result = None

    if request.method == "POST":
        action = request.form.get("action", "").strip()
        result = cleanup_security_logs(conn, action)

    report = build_security_cleanup_report(conn)

    conn.close()

    return render_template(
        "security_cleanup.html",
        report=report,
        result=result,
        title="安全日志清理",
    )



@app.route("/security/blocks", methods=["GET", "POST"])
def v155_security_blocks():
    import sqlite3
    from pathlib import Path
    from flask import request, render_template, abort, redirect
    from services.v155_runtime_guard import (
        build_ip_blocklist_report,
        add_block_ip,
        remove_block_ip,
    )

    token_path = Path("data/security_admin_token.txt")
    saved_token = token_path.read_text().strip() if token_path.exists() else ""

    input_token = request.args.get("token", "").strip()
    cookie_token = request.cookies.get("v155_security_admin", "").strip()

    if not saved_token or (
        input_token != saved_token
        and cookie_token != saved_token
    ):
        abort(403)

    conn = sqlite3.connect("data/snapshots.db")
    conn.row_factory = sqlite3.Row

    if request.method == "POST":
        action = request.form.get("action", "").strip()
        ip = request.form.get("ip", "").strip()
        reason = request.form.get("reason", "").strip()

        if action == "add_block":
            add_block_ip(conn, ip, reason or "后台手动封禁", "manual")

        elif action == "add_candidate":
            add_block_ip(conn, ip, reason or "高风险候选确认封禁", "candidate")

        elif action == "remove_block":
            remove_block_ip(conn, ip)

        conn.close()
        return redirect("/security/blocks")

    report = build_ip_blocklist_report(conn)

    conn.close()

    return render_template(
        "security_blocks.html",
        report=report,
        title="IP封禁池",
    )



# =========================
# V15.5-S2.8 nginx blocklist sync admin
# =========================

def _v155_security_admin_allowed():
    from pathlib import Path
    from flask import request

    token_path = Path("data/security_admin_token.txt")
    saved_token = token_path.read_text().strip() if token_path.exists() else ""

    input_token = request.args.get("token", "").strip()
    cookie_token = request.cookies.get("v155_security_admin", "").strip()

    return bool(saved_token and (input_token == saved_token or cookie_token == saved_token))


def _v155_build_nginx_sync_report():
    import sqlite3
    from pathlib import Path
    from datetime import datetime

    snippet_path = Path("/etc/nginx/snippets/ai-tool-ip-blocklist.conf")

    conn = sqlite3.connect("data/snapshots.db")
    conn.row_factory = sqlite3.Row

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS v155_security_ip_blocklist (
            ip TEXT PRIMARY KEY,
            reason TEXT,
            source TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )

    active_blocks = conn.execute(
        """
        SELECT ip, reason, source, updated_at
        FROM v155_security_ip_blocklist
        WHERE is_active=1
        ORDER BY updated_at DESC
        LIMIT 50
        """
    ).fetchall()

    active_block_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM v155_security_ip_blocklist
        WHERE is_active=1
        """
    ).fetchone()[0]

    conn.close()

    snippet_exists = snippet_path.exists()
    snippet_text = snippet_path.read_text(encoding="utf-8") if snippet_exists else ""

    deny_lines = [
        line.strip()
        for line in snippet_text.splitlines()
        if line.strip().startswith("deny ")
    ]

    snippet_mtime = ""

    if snippet_exists:
        snippet_mtime = datetime.fromtimestamp(
            snippet_path.stat().st_mtime
        ).strftime("%Y-%m-%d %H:%M:%S")

    return {
        "active_block_count": active_block_count,
        "active_blocks": [dict(row) for row in active_blocks],
        "snippet_path": str(snippet_path),
        "snippet_exists": snippet_exists,
        "snippet_mtime": snippet_mtime,
        "nginx_deny_count": len(deny_lines),
        "deny_lines": deny_lines[:80],
        "snippet_preview": snippet_text[:5000],
    }


def _v155_run_fixed_command(cmd, cwd="/home/admin/ai-tool", timeout=15):
    import subprocess

    try:
        p = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        return {
            "cmd": " ".join(cmd),
            "returncode": p.returncode,
            "stdout": p.stdout[-4000:],
            "stderr": p.stderr[-4000:],
            "ok": p.returncode == 0,
        }

    except Exception as e:
        return {
            "cmd": " ".join(cmd),
            "returncode": -1,
            "stdout": "",
            "stderr": str(e),
            "ok": False,
        }


@app.route("/security/nginx")
def v155_security_nginx_sync_page():
    from flask import render_template, redirect

    if not _v155_security_admin_allowed():
        return redirect("/security/login")

    report = _v155_build_nginx_sync_report()

    return render_template(
        "security_nginx_sync.html",
        report=report,
        result=None,
        title="Nginx封禁同步",
    )


@app.route("/security/nginx/sync", methods=["POST"])
def v155_security_nginx_sync_action():
    from flask import render_template, redirect

    if not _v155_security_admin_allowed():
        return redirect("/security/login")

    steps = []

    steps.append(
        _v155_run_fixed_command(
            ["python3", "scripts/sync_nginx_blocklist.py"]
        )
    )

    if steps[-1]["ok"]:
        steps.append(
            _v155_run_fixed_command(
                ["nginx", "-t"],
                cwd="/home/admin/ai-tool"
            )
        )

    if steps[-1]["ok"]:
        steps.append(
            _v155_run_fixed_command(
                ["systemctl", "reload", "nginx"],
                cwd="/home/admin/ai-tool"
            )
        )

    ok = all(step["ok"] for step in steps)

    result = {
        "ok": ok,
        "steps": steps,
        "message": "Nginx 封禁名单已同步并重载生效。" if ok else "同步失败，请查看下方错误输出。",
    }

    try:
        step_summary = "；".join(
            [
                f"{step.get('cmd')}={step.get('returncode')}"
                for step in steps
            ]
        )

        v155_record_security_admin_action(
            "nginx_sync",
            "同步 Nginx 封禁名单",
            "success" if ok else "failed",
            step_summary,
        )
    except Exception:
        pass

    report = _v155_build_nginx_sync_report()

    return render_template(
        "security_nginx_sync.html",
        report=report,
        result=result,
        title="Nginx封禁同步",
    )



# =========================
# V15.5-S2.9 nginx sync status enhanced report
# =========================

def _v155_build_nginx_sync_report():
    import sqlite3
    import ipaddress
    from pathlib import Path
    from datetime import datetime

    snippet_path = Path("/etc/nginx/snippets/ai-tool-ip-blocklist.conf")

    def can_export_to_nginx(ip: str) -> bool:
        ip = str(ip or "").strip()
        if not ip:
            return False

        try:
            obj = ipaddress.ip_address(ip)
        except Exception:
            return False

        if obj.is_loopback or obj.is_private or obj.is_link_local or obj.is_reserved:
            return False

        return True

    conn = sqlite3.connect("data/snapshots.db")
    conn.row_factory = sqlite3.Row

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS v155_security_ip_blocklist (
            ip TEXT PRIMARY KEY,
            reason TEXT,
            source TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS v155_security_ip_whitelist (
            ip TEXT PRIMARY KEY,
            note TEXT,
            created_at TEXT
        )
        """
    )

    active_blocks = conn.execute(
        """
        SELECT ip, reason, source, updated_at
        FROM v155_security_ip_blocklist
        WHERE is_active=1
        ORDER BY updated_at DESC
        LIMIT 80
        """
    ).fetchall()

    all_active_blocks = conn.execute(
        """
        SELECT ip, reason, source, updated_at
        FROM v155_security_ip_blocklist
        WHERE is_active=1
        ORDER BY updated_at DESC
        """
    ).fetchall()

    whitelist = {
        row["ip"]
        for row in conn.execute(
            "SELECT ip FROM v155_security_ip_whitelist"
        ).fetchall()
    }

    conn.close()

    syncable_blocks = []

    for row in all_active_blocks:
        ip = str(row["ip"] or "").strip()

        if ip in whitelist:
            continue

        if not can_export_to_nginx(ip):
            continue

        syncable_blocks.append(dict(row))

    snippet_exists = snippet_path.exists()
    snippet_text = snippet_path.read_text(encoding="utf-8") if snippet_exists else ""

    deny_lines = [
        line.strip()
        for line in snippet_text.splitlines()
        if line.strip().startswith("deny ")
    ]

    nginx_ips = set()

    for line in deny_lines:
        parts = line.replace(";", " ").split()
        if len(parts) >= 2 and parts[0] == "deny":
            nginx_ips.add(parts[1].strip())

    expected_ips = {row["ip"] for row in syncable_blocks}

    missing_in_nginx = sorted(expected_ips - nginx_ips)
    extra_in_nginx = sorted(nginx_ips - expected_ips)

    is_synced = len(missing_in_nginx) == 0 and len(extra_in_nginx) == 0

    snippet_mtime = ""

    if snippet_exists:
        snippet_mtime = datetime.fromtimestamp(
            snippet_path.stat().st_mtime
        ).strftime("%Y-%m-%d %H:%M:%S")

    if is_synced:
        sync_label = "已同步"
        sync_level = "safe"
        sync_message = "数据库封禁名单与 Nginx deny 配置一致。"
    else:
        sync_label = "待同步"
        sync_level = "warning"
        sync_message = "数据库封禁名单与 Nginx deny 配置不一致，建议立即同步。"

    return {
        "active_block_count": len(all_active_blocks),
        "syncable_block_count": len(syncable_blocks),
        "active_blocks": [dict(row) for row in active_blocks],
        "syncable_blocks": syncable_blocks[:80],
        "snippet_path": str(snippet_path),
        "snippet_exists": snippet_exists,
        "snippet_mtime": snippet_mtime,
        "nginx_deny_count": len(deny_lines),
        "deny_lines": deny_lines[:80],
        "snippet_preview": snippet_text[:5000],
        "is_synced": is_synced,
        "sync_label": sync_label,
        "sync_level": sync_level,
        "sync_message": sync_message,
        "missing_in_nginx": missing_in_nginx[:50],
        "extra_in_nginx": extra_in_nginx[:50],
    }



# =========================
# V15.5-S3-A security admin audit
# =========================

def _v155_get_request_ip():
    from flask import request

    forwarded_for = request.headers.get("X-Forwarded-For", "").strip()

    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    return request.remote_addr or ""


def v155_record_security_admin_action(
    action_key,
    action_label,
    result_status="success",
    note="",
):
    import sqlite3
    from flask import request
    from services.v155_security_admin_audit import record_admin_action

    conn = sqlite3.connect("data/snapshots.db")
    conn.row_factory = sqlite3.Row

    try:
        record_admin_action(
            conn,
            admin_ip=_v155_get_request_ip(),
            user_agent=request.headers.get("User-Agent", ""),
            action_key=action_key,
            action_label=action_label,
            result_status=result_status,
            note=note,
            request_path=request.path,
        )
    finally:
        conn.close()


@app.route("/security/audit")
def v155_security_admin_audit_page():
    import sqlite3
    from flask import request, render_template, redirect
    from services.v155_security_admin_audit import list_admin_actions

    if not _v155_security_admin_allowed():
        return redirect("/security/login")

    try:
        page = int(request.args.get("page", "1") or 1)
    except Exception:
        page = 1

    conn = sqlite3.connect("data/snapshots.db")
    conn.row_factory = sqlite3.Row

    report = list_admin_actions(conn, page=page, per_page=30)

    conn.close()

    return render_template(
        "security_audit.html",
        report=report,
        title="安全操作审计",
    )
