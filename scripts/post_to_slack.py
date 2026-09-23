"""
15分おきにGitHub Actionsから実行されるスクリプト。

1. data/settings.json から「月報提出日」「投稿時刻」を読み込む
2. 今日（日本時間）が提出日と一致し、かつ現在時刻が設定した投稿時刻の15分枠に入っているかを確認する
3. 一致すれば以下の優先順位で月報データを用意する
   a. data/reports/YYYY-MM.json （monthly-report.htmlで手動作成・同期した「確定版」）があればそれを使う
   b. 無ければ data/daily/YYYY-MM-DD.json （report.htmlが保存のたびに自動同期した日報）を
      当月分すべて集めて自動集計する
4. 整形してSlackに投稿し、二重投稿を防ぐため data/posted/YYYY-MM.json にマーカーを書き込む
   （このマーカーがあれば、同じ月はその後何度スクリプトが動いても再投稿しない）
5. 提出日なのにデータが全く無い場合は、投稿の代わりにリマインドメッセージのみ送る
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
SETTINGS_PATH = REPO_ROOT / "data" / "settings.json"
REPORTS_DIR = REPO_ROOT / "data" / "reports"
DAILY_DIR = REPO_ROOT / "data" / "daily"
POSTED_DIR = REPO_ROOT / "data" / "posted"

JST = ZoneInfo("Asia/Tokyo")

# 月報のセクションキー(list1〜4) <-> 日報のフィールド名 の対応
FIELD_MAP = {
    "list1": "tasks",
    "list2": "goodPoints",
    "list3": "issues",
    "list4": "nextGoals",
}

SECTION_TITLES = {
    "list1": "①今月の実績・成果（業務内容や作業、取り組んでいること）",
    "list2": "②良かった点・学び",
    "list3": "③課題・反省点",
    "list4": "④来月の目標・注力事項（学んでいこうとしていること）",
}


def load_json(path: Path):
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def is_same_15min_bucket(now: datetime, post_time: str) -> bool:
    try:
        hh, mm = post_time.split(":")
        target_minutes = int(hh) * 60 + int(mm)
    except (ValueError, AttributeError):
        target_minutes = 9 * 60  # デフォルト 09:00
    now_minutes = now.hour * 60 + now.minute
    return (target_minutes // 15) == (now_minutes // 15)


def dedupe(values):
    seen = set()
    result = []
    for v in values:
        v = (v or "").strip()
        if v and v not in seen:
            seen.add(v)
            result.append(v)
    return result


def build_report_from_manual(report: dict) -> dict:
    return {key: dedupe(report.get(key, [])) for key in FIELD_MAP}


def build_report_from_daily(year: int, month: int) -> dict:
    collected = {key: [] for key in FIELD_MAP}
    if not DAILY_DIR.exists():
        return collected

    prefix = f"{year}-{month:02d}-"
    for path in sorted(DAILY_DIR.glob(f"{prefix}*.json")):
        daily = load_json(path)
        if not daily:
            continue
        for list_key, field in FIELD_MAP.items():
            for item in daily.get(field, []):
                if item and item.strip():
                    collected[list_key].append(item.strip())

    return {key: dedupe(values) for key, values in collected.items()}


def has_any_content(report: dict) -> bool:
    return any(report.get(key) for key in FIELD_MAP)


def build_report_text(report: dict) -> str:
    lines = []
    for key in ("list1", "list2", "list3", "list4"):
        lines.append(SECTION_TITLES[key])
        for item in report.get(key, []):
            lines.append(f"・{item}")
        lines.append("")
    return "\n".join(lines).strip()


def post_to_slack(text: str):
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        print("SLACK_WEBHOOK_URL が設定されていません。投稿をスキップします。")
        sys.exit(1)
    res = requests.post(webhook_url, json={"text": text}, timeout=10)
    if res.status_code != 200:
        print(f"Slackへの投稿に失敗しました: {res.status_code} {res.text}")
        sys.exit(1)
    print("Slackへの投稿が完了しました。")


def main():
    now = datetime.now(JST)

    settings = load_json(SETTINGS_PATH)
    due_day = settings.get("dueDay") if settings else None
    post_time = (settings.get("postTime") if settings else None) or "09:00"

    if not due_day:
        print("月報提出日が設定されていません。何もしません。")
        return

    if now.day != int(due_day):
        print(f"今日は{now.day}日、提出日は{due_day}日のため何もしません。")
        return

    if not is_same_15min_bucket(now, post_time):
        print(f"現在時刻は{now.strftime('%H:%M')}、投稿時刻は{post_time}のため何もしません。")
        return

    month_str = f"{now.year}-{now.month:02d}"
    posted_marker_path = POSTED_DIR / f"{month_str}.json"

    if posted_marker_path.exists():
        print(f"{month_str} は投稿済みマーカーがあるため、再投稿しません。")
        return

    manual_report = load_json(REPORTS_DIR / f"{month_str}.json")

    if manual_report and has_any_content(manual_report):
        report = build_report_from_manual(manual_report)
        source = "手動で作成・同期された月報"
    else:
        report = build_report_from_daily(now.year, now.month)
        source = "日報からの自動集計"

    if not has_any_content(report):
        # 提出日なのにデータが全く無い場合は、リマインドだけ送る
        post_to_slack(
            f"本日は月報提出日（{now.month}月{now.day}日）ですが、"
            f"{now.year}年{now.month}月分の日報・月報がまだ作成されていません。"
        )
        save_json(posted_marker_path, {"postedAt": now.isoformat(), "type": "reminder"})
        return

    text = build_report_text(report)
    header = f"【{now.year}年{now.month}月 月報】（{source}）\n\n"
    post_to_slack(header + text)

    save_json(posted_marker_path, {"postedAt": now.isoformat(), "type": "report", "source": source})


if __name__ == "__main__":
    main()
