from __future__ import annotations
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask import send_file
import io
# ====== 评分系统 ======

def calc_growth_score(growth):
    if growth > 20000:
        return 100
    elif growth > 10000:
        return 80
    elif growth > 3000:
        return 60
    elif growth > 0:
        return 40
    else:
        return 10


def calc_execution_score(status):
    if status == "已执行":
        return 100
    elif status == "部分执行":
        return 60
    else:
        return 10


def calc_power_score(power, avg_power):
    if avg_power == 0:
        return 50
    ratio = power / avg_power
    if ratio > 1.5:
        return 100
    elif ratio > 1.2:
        return 80
    elif ratio > 0.8:
        return 60
    else:
        return 30


def calc_stability_score(growth):
    if abs(growth) > 30000:
        return 30
    return 80


def classify(score):
    if score >= 80:
        return "核心成员"
    elif score >= 50:
        return "正常成员"
    elif score >= 30:
        return "警告名单"
    else:
        return "清理名单"


def get_reason(growth, status):
    reasons = []

    if growth <= 0:
        reasons.append("无增长")

    if status != "已执行":
        reasons.append("未执行任务")

    if growth > 30000:
        reasons.append("异常增长")

    return reasons

from pathlib import Path
import sqlite3
import json
from datetime import datetime
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, send_file, flash

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

MEMBERS_FILE = DATA_DIR / "members.csv"
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
app.secret_key = "alliance-manager-v7-ab"

def get_conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    import os

DB_PATH = "data/snapshots.db"

if os.path.exists(DB_PATH):
    os.remove(DB_PATH)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_time TEXT NOT NULL,
            member TEXT NOT NULL,
            team_name TEXT,
            state_name TEXT,
            contribution_rank INTEGER,
            contribution_week INTEGER,
            battle_week INTEGER,
            assist_week INTEGER,
            donate_week INTEGER,
            contribution_total INTEGER,
            battle_total INTEGER,
            assist_total INTEGER,
            donate_total INTEGER,
            power_value INTEGER,
            UNIQUE(snapshot_time, member)
        )
    """)
    conn.commit()
    conn.close()

def ensure_default_files():
    if not MEMBERS_FILE.exists():
        pd.DataFrame(columns=["nickname", "power", "team_name", "role", "notes"]).to_csv(
            MEMBERS_FILE, index=False, encoding="utf-8-sig"
        )

def load_members():
    ensure_default_files()
    try:
        df = pd.read_csv(MEMBERS_FILE, encoding="utf-8-sig")
    except Exception:
        df = pd.read_csv(MEMBERS_FILE)
        # 兼容新赛季字段
# 兼容新赛季字段
if "门阀" in df.columns and "分组" not in df.columns:
    df["分组"] = df["门阀"]

if "分组" not in df.columns:
    raise Exception("周表缺少字段：分组")
    expected = ["nickname", "power", "team_name", "role", "notes"]
    for col in expected:
        if col not in df.columns:
            df[col] = ""
    df["nickname"] = df["nickname"].astype(str).fillna("").str.strip()
    df["power"] = pd.to_numeric(df["power"], errors="coerce").fillna(0).astype(int)
    return df[expected]

def save_members(df):
    expected = ["nickname", "power", "team_name", "role", "notes"]
    for col in expected:
        if col not in df.columns:
            df[col] = ""
    df = df[expected].copy()
    df["nickname"] = df["nickname"].astype(str).fillna("").str.strip()
    df["power"] = pd.to_numeric(df["power"], errors="coerce").fillna(0).astype(int)
    df = df.drop_duplicates(subset=["nickname"], keep="last")
    df.to_csv(MEMBERS_FILE, index=False, encoding="utf-8-sig")

def load_game_csv(file_storage):
    df = read_csv_flexible(file_storage)
    df.columns = [str(c).strip() for c in df.columns]

    if "成员" not in df.columns:
        unnamed_cols = [c for c in df.columns if "Unnamed" in str(c)]
        if unnamed_cols:
            df = df.rename(columns={unnamed_cols[0]: "成员"})

    # ⭐关键：门阀 → 分组
    if "门阀" in df.columns and "分组" not in df.columns:
        df["分组"] = df["门阀"]

    required = [
        "成员","贡献排行","贡献本周","战功本周","助攻本周","捐献本周",
        "贡献总量","战功总量","助攻总量","捐献总量","势力值","所属州","分组"
    ]

    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"周表缺少字段：{', '.join(missing)}")

    numeric_cols = [
        "贡献排行","贡献本周","战功本周","助攻本周","捐献本周",
        "贡献总量","战功总量","助攻总量","捐献总量","势力值"
    ]

    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    df["成员"] = df["成员"].astype(str).str.strip()
    df["所属州"] = df["所属州"].astype(str).str.strip()
    df["分组"] = df["分组"].astype(str).str.strip()

    return df
    
def save_snapshot(df, snapshot_time):
    conn = get_conn()
    cur = conn.cursor()
    inserted = 0
    for _, row in df.iterrows():
        cur.execute("""
            INSERT OR REPLACE INTO snapshots (
                snapshot_time, member, team_name, state_name,
                contribution_rank, contribution_week, battle_week, assist_week, donate_week,
                contribution_total, battle_total, assist_total, donate_total, power_value
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            snapshot_time,
            str(row["成员"]).strip(),
            str(row["分组"]).strip(),
            str(row["所属州"]).strip(),
            int(row["贡献排行"]), int(row["贡献本周"]), int(row["战功本周"]),
            int(row["助攻本周"]), int(row["捐献本周"]), int(row["贡献总量"]),
            int(row["战功总量"]), int(row["助攻总量"]), int(row["捐献总量"]), int(row["势力值"])
        ))
        inserted += 1
    conn.commit()
    conn.close()
    return inserted

def list_snapshot_times():
    conn = get_conn()
    rows = conn.execute("SELECT DISTINCT snapshot_time FROM snapshots ORDER BY snapshot_time DESC").fetchall()
    conn.close()
    return [r["snapshot_time"] for r in rows]

def load_snapshot_df(snapshot_time):
    conn = get_conn()
    rows = conn.execute("""
        SELECT
            member AS 成员,
            team_name AS 分组,
            state_name AS 所属州,
            contribution_rank AS 贡献排行,
            contribution_week AS 贡献本周,
            battle_week AS 战功本周,
            assist_week AS 助攻本周,
            donate_week AS 捐献本周,
            contribution_total AS 贡献总量,
            battle_total AS 战功总量,
            assist_total AS 助攻总量,
            donate_total AS 捐献总量,
            power_value AS 势力值
        FROM snapshots
        WHERE snapshot_time = ?
    """, (snapshot_time,)).fetchall()
    conn.close()
    return pd.DataFrame([dict(r) for r in rows])

def compare_snapshots(df_old, df_new):
    # ===== 只保留两张表共同成员，做总量对比 =====
    df = pd.merge(df_old, df_new, on="成员", how="outer", suffixes=("_old", "_new"))
    df = df.fillna(0)
    if df.empty:
        empty_result = pd.DataFrame(columns=[
            "成员", "分组", "所属州", "势力值", "贡献排行",
            "战功本周", "助攻本周", "捐献本周",
            "战功增长", "助攻增长", "捐献增长", "势力增长",
            "执行状态", "违规", "状态", "建议",
            "评分", "风险原因", "分类", "优先类别"
        ])
        empty_groups = pd.DataFrame(columns=["分组", "人数"])
        empty_advice = {
            "清理名单": [],
            "警告名单": [],
            "核心成员": [],
            "未执行名单": []
        }
        return empty_result, empty_groups, empty_advice

    # ===== 计算增长（核心升级：全部按总量差值）=====
    df["战功增长"] = pd.to_numeric(df["战功总量_new"], errors="coerce").fillna(0) - pd.to_numeric(df["战功总量_old"], errors="coerce").fillna(0)
    df["助攻增长"] = pd.to_numeric(df["助攻总量_new"], errors="coerce").fillna(0) - pd.to_numeric(df["助攻总量_old"], errors="coerce").fillna(0)
    df["捐献增长"] = pd.to_numeric(df["捐献总量_new"], errors="coerce").fillna(0) - pd.to_numeric(df["捐献总量_old"], errors="coerce").fillna(0)
    df["势力增长"] = pd.to_numeric(df["势力值_new"], errors="coerce").fillna(0) - pd.to_numeric(df["势力值_old"], errors="coerce").fillna(0)

    # ===== 当前最新势力均值（用于战力评分）=====
    avg_power = pd.to_numeric(df["势力值_new"], errors="coerce").fillna(0).mean()
    if pd.isna(avg_power):
        avg_power = 0

    result_rows = []

    for _, row in df.iterrows():
        name = str(row.get("成员", "")).strip()

        team_name = str(row.get("分组_new", "")).strip()
        state_name = str(row.get("所属州_new", "")).strip()

        power_value = int(pd.to_numeric(row.get("势力值_new", 0), errors="coerce") or 0)
        contribution_rank = int(pd.to_numeric(row.get("贡献排行_new", 0), errors="coerce") or 0)

        battle_week = int(pd.to_numeric(row.get("战功本周_new", 0), errors="coerce") or 0)
        assist_week = int(pd.to_numeric(row.get("助攻本周_new", 0), errors="coerce") or 0)
        donate_week = int(pd.to_numeric(row.get("捐献本周_new", 0), errors="coerce") or 0)

        war_growth = int(pd.to_numeric(row.get("战功增长", 0), errors="coerce") or 0)
        assist_growth = int(pd.to_numeric(row.get("助攻增长", 0), errors="coerce") or 0)
        donate_growth = int(pd.to_numeric(row.get("捐献增长", 0), errors="coerce") or 0)
        power_growth = int(pd.to_numeric(row.get("势力增长", 0), errors="coerce") or 0)

        # ===== 行为识别（以增长为准）=====
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

        # ===== 违规识别 =====
        violation = "正常"
        if row["势力值_new"] == 0:
            violation = "成员消失"
        if power_growth > 5000 and assist_growth == 0 and war_growth < 5000:
            violation = "疑似偷地"
        elif war_growth == 0 and assist_growth == 0 and power_growth == 0 and donate_growth == 0:
            violation = "未执行"
        elif war_growth < 3000 and assist_growth < 300 and power_growth <= 0:
            violation = "低活跃"

        # ===== 四项评分（0~100）=====

        # 1. 势力增长评分
        if power_growth > 20000:
            growth_score = 100
        elif power_growth > 10000:
            growth_score = 85
        elif power_growth > 5000:
            growth_score = 75
        elif power_growth > 0:
            growth_score = 60
        elif power_growth > -2000:
            growth_score = 40
        else:
            growth_score = 20

        # 2. 执行评分
        if exec_status == "主力打架":
            execution_score = 100
        elif exec_status == "参与攻城":
            execution_score = 90
        elif exec_status == "打地发育":
            execution_score = 75
        elif exec_status == "仅捐献":
            execution_score = 55
        elif exec_status == "低活跃":
            execution_score = 40
        else:  # 完全摆烂
            execution_score = 20

        # 3. 战力评分（按当前势力值相对平均值）
        if avg_power == 0:
            power_score = 50
        else:
            ratio = power_value / avg_power
            if ratio > 1.5:
                power_score = 100
            elif ratio > 1.2:
                power_score = 85
            elif ratio > 1.0:
                power_score = 70
            elif ratio > 0.8:
                power_score = 55
            else:
                power_score = 35

        # 4. 贡献行为评分（战功/助攻/捐献综合）
        behavior_raw = war_growth + assist_growth * 2 + donate_growth * 0.2
        if behavior_raw > 20000:
            behavior_score = 100
        elif behavior_raw > 10000:
            behavior_score = 85
        elif behavior_raw > 5000:
            behavior_score = 70
        elif behavior_raw > 1000:
            behavior_score = 55
        elif behavior_raw > 0:
            behavior_score = 40
        else:
            behavior_score = 20

        # ===== 基础评分 =====
        base_score = int(
            growth_score * 0.30 +
            execution_score * 0.30 +
            power_score * 0.20 +
            behavior_score * 0.20
        )

        # ===== 风险系统 =====
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

        # 去重，保持顺序
        dedup_reason = []
        for x in risk_reason:
            if x not in dedup_reason:
                dedup_reason.append(x)
        risk_reason = dedup_reason

        # ===== 最终评分（统一在 0~100 左右）=====
        final_score = max(0, int(base_score - risk_level * 12))

        # ===== 分类逻辑 =====
        if violation == "疑似偷地":
            status = "违规"
            advice = "建议清理"
            category = "清理名单"
            priority_type = 1

        elif final_score < 35:
            status = "低活跃"
            advice = "建议清理"
            category = "清理名单"
            priority_type = 2

        elif final_score < 65:
            status = "待警告"
            advice = "重点关注"
            category = "警告名单"
            priority_type = 3

        elif final_score >= 85:
            status = "核心"
            advice = "优先资源"
            category = "核心成员"
            priority_type = 99

        else:
            status = "正常"
            advice = "保持"
            category = "正常成员"
            priority_type = 50

        risk_reason_str = "，".join(risk_reason) if risk_reason else "正常"

        result_rows.append({
    "成员": name,
    "分组": team_name,
    "所属州": state_name,

    # ===== 当前数据（补回来）=====
    "势力值": power_value,
    "贡献排行": contribution_rank,
    "战功本周": battle_week,
    "助攻本周": assist_week,
    "捐献本周": donate_week,

    "战功总量": int(row.get("战功总量_new", 0)),
    "助攻总量": int(row.get("助攻总量_new", 0)),
    "捐献总量": int(row.get("捐献总量_new", 0)),

    # ===== 增长数据 =====
    "战功增长": war_growth,
    "助攻增长": assist_growth,
    "捐献增长": donate_growth,
    "势力增长": power_growth,

    # ===== 行为判断 =====
    "执行状态": exec_status,
    "违规": violation,

    # ===== 结论 =====
    "状态": status,
    "建议": advice,
    "评分": final_score,
    "风险原因": risk_reason_str,

    # ===== 分类 =====
    "分类": category,
    "优先类别": priority_type
})
    df_result = pd.DataFrame(result_rows)

    # ===== 排序 =====
    df_result = df_result.sort_values(
        by=["优先类别", "评分", "战功增长", "助攻增长", "捐献增长"],
        ascending=[True, False, False, False, False]
    ).reset_index(drop=True)

    df_result["优先级排名"] = range(1, len(df_result) + 1)

    advice = {
        "清理名单": df_result[df_result["分类"] == "清理名单"]["成员"].tolist(),
        "警告名单": df_result[df_result["分类"] == "警告名单"]["成员"].tolist(),
        "核心成员": df_result[df_result["分类"] == "核心成员"]["成员"].tolist(),
        "未执行名单": df_result[df_result["执行状态"] == "完全摆烂"]["成员"].tolist()
    }

    groups = df_result.groupby("分组").size().reset_index(name="人数")

    return df_result, groups, advice
def build_kick_text(advice):
    text = ""

    if advice["清理名单"]:
        text += "【清理名单】\n"
        text += "\n".join(advice["清理名单"]) + "\n\n"

    if advice["警告名单"]:
        text += "【警告名单】\n"
        text += "\n".join(advice["警告名单"]) + "\n\n"

    if advice["核心成员"]:
        text += "【核心成员】\n"
        text += "\n".join(advice["核心成员"]) + "\n\n"

    return text.strip()
def save_outputs(result, groups, advice):
    result.to_csv(COMPARE_RESULT_FILE, index=False, encoding="utf-8-sig")
    groups.to_csv(GROUP_SUMMARY_FILE, index=False, encoding="utf-8-sig")
    ADVICE_FILE.write_text(json.dumps(advice, ensure_ascii=False, indent=2), encoding="utf-8")

def load_outputs():
    result = groups = None
    advice = {"清理名单": [], "警告名单": [], "核心成员": [], "未执行名单": []}
    if COMPARE_RESULT_FILE.exists():
        result = pd.read_csv(COMPARE_RESULT_FILE, encoding="utf-8-sig")
    if GROUP_SUMMARY_FILE.exists():
        groups = pd.read_csv(GROUP_SUMMARY_FILE, encoding="utf-8-sig")
    if ADVICE_FILE.exists():
        advice = json.loads(ADVICE_FILE.read_text(encoding="utf-8"))
    return result, groups, advice

def filter_result_df(df, team_keyword="", pg_min=None, pg_max=None):
    out = df.copy()
    if team_keyword:
        out = out[out["分组"].astype(str).str.contains(team_keyword, na=False)]
    if pg_min is not None:
        out = out[out["势力增长"] >= pg_min]
    if pg_max is not None:
        out = out[out["势力增长"] <= pg_max]
    return out

@app.route("/")
def overview():
    init_db()
    members = load_members()
    result, _, advice = load_outputs()

    stats = {
        "成员总数": len(members),
        "高战人数": int((members["power"] >= HIGH_POWER).sum()),
        "快照次数": len(list_snapshot_times()),
        "最近异常数": 0 if result is None else int(
            result["违规"].astype(str).str.contains("疑似偷地|未执行|低活跃", na=False).sum()
        ),
    }

    top_members = (
        members.sort_values(by="power", ascending=False)
        .head(10)
        .to_dict(orient="records")
    )

    top_abnormal = []
    if result is not None:
        top_abnormal = (
            result.sort_values(by=["优先类别", "评分"], ascending=[True, False])
            .head(10)
            .to_dict(orient="records")
        )

    if advice is None:
        advice = {
            "清理名单": [],
            "警告名单": [],
            "核心成员": [],
            "未执行名单": []
        }

    advice_summary = [
        f"建议清理：{len(advice['清理名单'])} 人",
        f"重点关注：{len(advice['警告名单'])} 人",
        f"核心稳定：{len(advice['核心成员'])} 人",
        f"未执行：{len(advice['未执行名单'])} 人"
    ]

    return render_template(
        "overview.html",
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
        file = request.files.get("snapshot_file")
        snapshot_time = request.form.get("snapshot_time", "").strip()
        if not file or not file.filename:
            flash("请先选择原始CSV快照", "error")
            return redirect(url_for("snapshots"))
        if not snapshot_time:
            snapshot_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        try:
            df = load_game_csv(file)
            save_snapshot(df, snapshot_time)
            update_members_from_snapshot(df)
            flash(f"快照保存成功：{snapshot_time}，共 {len(df)} 条", "success")
        except Exception as e:
            flash(f"快照保存失败：{e}", "error")
        return redirect(url_for("snapshots"))
    return render_template("snapshots.html", times=list_snapshot_times())

@app.route("/compare", methods=["GET", "POST"])
def compare():
    init_db()
    times = list_snapshot_times()

    result_rows, group_rows = [], []
    advice = {"清理名单": [], "警告名单": [], "核心成员": [], "未执行名单": []}
    selected_old = selected_new = ""

    compare_mode = "auto"
    team_keyword = ""
    power_growth_min = ""
    power_growth_max = ""
    kick_text = ""

    if request.method == "POST":
        compare_mode = request.form.get("compare_mode", "auto")
        team_keyword = request.form.get("team_keyword", "").strip()
        power_growth_min = request.form.get("power_growth_min", "").strip()
        power_growth_max = request.form.get("power_growth_max", "").strip()
        # ===== 新增筛选参数（必须加） =====
        war_min = request.form.get("war_min", "").strip()
        war_max = request.form.get("war_max", "").strip()

        assist_min = request.form.get("assist_min", "").strip()
        assist_max = request.form.get("assist_max", "").strip()

        donate_min = request.form.get("donate_min", "").strip()
        donate_max = request.form.get("donate_max", "").strip()

        try:
            if compare_mode == "manual":
                selected_old = request.form.get("snapshot_old", "")
                selected_new = request.form.get("snapshot_new", "")
            else:
                if len(times) < 2:
                    raise ValueError("至少需要两次快照才能自动对比")
                selected_new, selected_old = times[0], times[1]

            df_old = load_snapshot_df(selected_old)
            df_new = load_snapshot_df(selected_new)

            result, groups, advice = compare_snapshots(df_old, df_new)

            # 分组筛选
            if team_keyword:
                result = result[
                    result["分组"].astype(str).str.strip().str.contains(team_keyword, na=False)
                ]
                groups = groups[
                    groups["分组"].astype(str).str.strip().str.contains(team_keyword, na=False)
                ]

            # 势力增长筛选
            pg_min = int(power_growth_min) if power_growth_min else None
            pg_max = int(power_growth_max) if power_growth_max else None
            result = filter_result_df(result, pg_min=pg_min, pg_max=pg_max)
            # ===== 多维筛选（直接写，不定义函数） =====
            war_min_v = int(war_min) if war_min else None
            war_max_v = int(war_max) if war_max else None
            assist_min_v = int(assist_min) if assist_min else None
            assist_max_v = int(assist_max) if assist_max else None
            donate_min_v = int(donate_min) if donate_min else None
            donate_max_v = int(donate_max) if donate_max else None

            if war_min_v is not None:
                result = result[result["战功增长"] >= war_min_v]

            if war_max_v is not None:
                result = result[result["战功增长"] <= war_max_v]

            if assist_min_v is not None:
                result = result[result["助攻增长"] >= assist_min_v]

            if assist_max_v is not None:
                result = result[result["助攻增长"] <= assist_max_v]

            if donate_min_v is not None:
                result = result[result["捐献增长"] >= donate_min_v]

            if donate_max_v is not None:
                result = result[result["捐献增长"] <= donate_max_v]

            # 筛选后重建建议名单
            advice = {
    "清理名单": result[result["分类"] == "清理名单"]["成员"].tolist(),
    "警告名单": result[result["分类"] == "警告名单"]["成员"].tolist(),
    "核心成员": result[result["分类"] == "核心成员"]["成员"].tolist(),
    "未执行名单": result[result["执行状态"] == "未参战"]["成员"].tolist()
}

            kick_text = build_kick_text(advice)

            # 最终排序
            result = result.sort_values(
    by=["优先类别", "评分", "战功增长"],
    ascending=[True, False, False]
).reset_index(drop=True)
            result["优先级排名"] = range(1, len(result) + 1)

            save_outputs(result, groups, advice)

            result_rows = result.to_dict(orient="records")
            group_rows = groups.to_dict(orient="records")

            flash("对比分析完成", "success")

        except Exception as e:
            flash(f"对比失败：{e}", "error")

    else:
        result, groups, advice = load_outputs()

        if result is not None:
            result_rows = result.to_dict(orient="records")

        if groups is not None:
            group_rows = groups.to_dict(orient="records")

        kick_text = build_kick_text(advice)

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
        compare_mode=compare_mode
    )
@app.route("/trends")
def trends():
    init_db()
    member_keyword = request.args.get("member_keyword", "").strip()
    team_keyword = request.args.get("team_keyword", "").strip()
    trend_rows = []
    conn = get_conn()
    if member_keyword:
        rows = conn.execute("""
            SELECT snapshot_time, member, team_name, battle_total, assist_total, power_value
            FROM snapshots
            WHERE member LIKE ?
            ORDER BY snapshot_time ASC
        """, (f"%{member_keyword}%",)).fetchall()
        trend_rows = [dict(r) for r in rows]
    elif team_keyword:
        rows = conn.execute("""
            SELECT snapshot_time, team_name,
                   SUM(battle_total) AS battle_total_sum,
                   SUM(assist_total) AS assist_total_sum,
                   SUM(power_value) AS power_value_sum,
                   COUNT(*) AS members_count
            FROM snapshots
            WHERE team_name LIKE ?
            GROUP BY snapshot_time, team_name
            ORDER BY snapshot_time ASC
        """, (f"%{team_keyword}%",)).fetchall()
        trend_rows = [dict(r) for r in rows]
    conn.close()
    return render_template("trends.html", trend_rows=trend_rows, member_keyword=member_keyword, team_keyword=team_keyword)

@app.route("/members", methods=["GET", "POST"])
def members():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "add_member":
            nickname = request.form.get("nickname", "").strip()
            power = request.form.get("power", "0").strip()
            team_name = request.form.get("team_name", "").strip()
            role = request.form.get("role", "成员").strip()
            notes = request.form.get("notes", "").strip()
            if not nickname:
                flash("昵称不能为空", "error")
                return redirect(url_for("members"))
            df = load_members()
            if nickname in df["nickname"].astype(str).tolist():
                flash("该成员已存在", "warning")
                return redirect(url_for("members"))
            new_row = pd.DataFrame([{"nickname": nickname, "power": int(float(power or 0)), "team_name": team_name, "role": role or "成员", "notes": notes}])
            save_members(pd.concat([df, new_row], ignore_index=True))
            flash("成员新增成功", "success")
            return redirect(url_for("members"))
        elif action == "import_members":
            file = request.files.get("file")
            if not file or not file.filename:
                flash("请先选择CSV文件", "error")
                return redirect(url_for("members"))
            try:
                imported = read_csv_flexible(file)
                imported.columns = [str(c).strip() for c in imported.columns]
                required = ["nickname", "power", "team_name", "role", "notes"]
                missing = [c for c in required if c not in imported.columns]
                if missing:
                    raise ValueError(f"成员表缺少字段：{', '.join(missing)}")
                imported = imported[required].copy()
                imported["nickname"] = imported["nickname"].astype(str).str.strip()
                imported["power"] = pd.to_numeric(imported["power"], errors="coerce").fillna(0).astype(int)
                df = load_members()
                save_members(pd.concat([df, imported], ignore_index=True))
                flash(f"成功导入 {len(imported)} 名成员", "success")
            except Exception as e:
                flash(f"导入失败：{e}", "error")
            return redirect(url_for("members"))
    members_df = load_members().sort_values(by="power", ascending=False)
    return render_template("members.html", members=members_df.to_dict(orient="records"))

@app.route("/members/delete/<nickname>", methods=["POST"])
def delete_member(nickname):
    df = load_members()
    df = df[df["nickname"] != nickname].copy()
    save_members(df)
    flash("成员已删除", "success")
    return redirect(url_for("members"))

@app.route("/rules")
def rules():
    return render_template("rules.html", high_power=HIGH_POWER, mid_power=MID_POWER, high_battle_min=HIGH_BATTLE_MIN, mid_battle_min=MID_BATTLE_MIN, core_battle_min=CORE_BATTLE_MIN)

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

@app.route('/export_members')
def export_members():
    import pandas as pd
    
    file_path = MEMBERS_FILE
    
    df = pd.read_csv(file_path)
    
    output = io.StringIO()
    df.to_csv(output, index=False)
    
    output.seek(0)
    
    return send_file(
        io.BytesIO(output.getvalue().encode()),
        mimetype='text/csv',
        as_attachment=True,
        download_name='members_export.csv'
    )


if __name__ == "__main__":
    ensure_default_files()
    init_db()
    app.run(host="127.0.0.1", port=8080, debug=True)
