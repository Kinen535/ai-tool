from pathlib import Path
import subprocess
import sqlite3
from datetime import datetime

ROOT = Path("/home/admin/ai-tool")
DB = ROOT / "data" / "snapshots.db"
OUT = ROOT / "docs" / "V15.6_reputation_release_summary.md"

OUT.parent.mkdir(parents=True, exist_ok=True)


def run(cmd):
    return subprocess.check_output(cmd, cwd=str(ROOT), text=True).strip()


def count(conn, sql):
    row = conn.execute(sql).fetchone()
    return int(row[0] or 0) if row else 0


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    subject_total = count(conn, "SELECT COUNT(*) FROM v156_reputation_subjects")
    event_total = count(conn, "SELECT COUNT(*) FROM v156_reputation_events")
    relation_total = count(conn, "SELECT COUNT(*) FROM v156_reputation_event_relations")
    merge_log_total = count(conn, "SELECT COUNT(*) FROM v156_reputation_merge_logs")

    risk_subject_total = count(conn, """
        SELECT COUNT(*)
        FROM v156_reputation_subjects
        WHERE risk_level IN ('warning','danger','black')
           OR trust_level IN ('risky','black')
    """)

    high_event_total = count(conn, """
        SELECT COUNT(*)
        FROM v156_reputation_events
        WHERE impact_level IN ('high','severe','critical')
    """)

    unlinked_event_total = count(conn, """
        SELECT COUNT(*)
        FROM v156_reputation_events e
        LEFT JOIN v156_reputation_event_relations r ON r.event_id = e.id
        WHERE r.id IS NULL
    """)

    conn.close()

    git_log = run(["git", "log", "--oneline", "--decorate", "-20"])

    lines = []
    lines.append("# V15.6 信誉档案库阶段收口报告")
    lines.append("")
    lines.append(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append("## 一、当前阶段结论")
    lines.append("")
    lines.append("V15.6 信誉档案库已经完成一轮核心闭环。")
    lines.append("")
    lines.append("- 独立信誉档案库首页")
    lines.append("- 信誉主体库")
    lines.append("- 信誉事件库")
    lines.append("- 主体与事件证据链关联")
    lines.append("- 重复主体检测")
    lines.append("- 合并日志")
    lines.append("- 安全备份状态页")
    lines.append("- 备份导出、校验、恢复预检")
    lines.append("- 全链路自检")
    lines.append("- 页面安全防泄露")
    lines.append("- 中文状态显示")
    lines.append("- 核心页面巡检")
    lines.append("")
    lines.append("## 二、当前数据概况")
    lines.append("")
    lines.append("| 项目 | 数量 |")
    lines.append("|---|---:|")
    lines.append(f"| 信誉主体 | {subject_total} |")
    lines.append(f"| 风险主体 | {risk_subject_total} |")
    lines.append(f"| 信誉事件 | {event_total} |")
    lines.append(f"| 高影响事件 | {high_event_total} |")
    lines.append(f"| 证据链关联 | {relation_total} |")
    lines.append(f"| 未关联事件 | {unlinked_event_total} |")
    lines.append(f"| 合并日志 | {merge_log_total} |")
    lines.append("")
    lines.append("## 三、已完成的关键安全措施")
    lines.append("")
    lines.append("- 备份状态页无 token 直接访问返回 404")
    lines.append("- 备份状态页不暴露服务器绝对路径")
    lines.append("- 备份状态页不暴露备份文件名")
    lines.append("- 备份状态页不暴露维护命令")
    lines.append("- full check 输出不暴露真实路径、token、备份文件名")
    lines.append("- 首页不暴露维护页真实地址")
    lines.append("- 核心页面巡检已加入 full check")
    lines.append("")
    lines.append("## 四、已完成的中文化")
    lines.append("")
    lines.append("- 首页状态中文化")
    lines.append("- 主体列表状态中文化")
    lines.append("- 事件列表状态中文化")
    lines.append("- 重复检测页状态中文化")
    lines.append("- 主体详情页与事件详情页中文化检查")
    lines.append("- 检索页中文化检查")
    lines.append("- 主体关联事件摘要影响等级中文化")
    lines.append("")
    lines.append("## 五、核心自检命令")
    lines.append("")
    lines.append("cd /home/admin/ai-tool")
    lines.append("python3 scripts/reputation_full_check.py")
    lines.append("")
    lines.append("通过标准：")
    lines.append("")
    lines.append("- 首页安全检查通过")
    lines.append("- 备份状态页安全检查通过")
    lines.append("- 列表页中文化检查通过")
    lines.append("- 详情页与检索页中文化检查通过")
    lines.append("- 核心页面巡检通过")
    lines.append("- V15.6 信誉档案库全链路自检通过")
    lines.append("")
    lines.append("## 六、最近提交记录")
    lines.append("")
    lines.append(git_log)
    lines.append("")
    lines.append("## 七、下一阶段建议")
    lines.append("")
    lines.append("建议进入 V15.7：信誉档案库业务增强。")
    lines.append("")
    lines.append("优先方向：")
    lines.append("")
    lines.append("1. 主体详情页增加处置建议")
    lines.append("2. 事件详情页增加影响评估")
    lines.append("3. 检索页增加风险结论卡")
    lines.append("4. 高风险主体支持人工复核状态")
    lines.append("5. 信誉档案库接入 AI 总结，但只做解释，不直接决策")

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"✅ 已生成 V15.6 收口报告：{OUT}")


if __name__ == "__main__":
    main()
