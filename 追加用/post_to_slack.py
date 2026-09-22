"""
毎日GitHub Actionsから実行されるスクリプト。

1. data/settings.json から「月報提出日（何日か）」を読み込む
2. 今日（日本時間）がその日と一致するかを確認する
3. 一致すれば data/reports/YYYY-MM.json（フロントエンドが同期した当月の月報）を読み込み、
   指定フォーマットに整形してSlackに投稿する
4. 一致しない、または当月の月報データがまだ無い場合は何もしない（月報が無い場合はリマインドのみ送る）
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

JST = ZoneInfo("Asia/Tokyo")

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


def build_report_text(report: dict) -> str:
    lines = []
    for key in ("list1", "list2", "list3", "list4"):
        lines.append(SECTION_TITLES[key])
        for item in report.get(key, []):
            if item and item.strip():
                lines.append(f"・{item.strip()}")
        lines.append("")
    return "\n".join(lines).strip()


def post_to_slack(text: str):
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        print("SLACK_WEBHOOK_URL が設定されていません。投稿をスキップします。")
        return
    res = requests.post(webhook_url, json={"text": text}, timeout=10)
    if res.status_code != 200:
        print(f"Slackへの投稿に失敗しました: {res.status_code} {res.text}")
        sys.exit(1)
    print("Slackへの投稿が完了しました。")


def main():
    today = datetime.now(JST)

    settings = load_json(SETTINGS_PATH)
    due_day = settings.get("dueDay") if settings else None

    if not due_day:
        print("月報提出日が設定されていません。何もしません。")
        return

    if today.day != int(due_day):
        print(f"今日は{today.day}日、提出日は{due_day}日のため何もしません。")
        return

    month_str = f"{today.year}-{today.month:02d}"
    report_path = REPORTS_DIR / f"{month_str}.json"
    report = load_json(report_path)

    if not report:
        # 提出日なのに月報データがまだ無い場合は、リマインドだけ送る
        post_to_slack(
            f"本日は月報提出日（{today.month}月{today.day}日）ですが、"
            f"{today.year}年{today.month}月分の月報がまだ作成されていません。"
        )
        return

    text = build_report_text(report)
    header = f"【{today.year}年{today.month}月 月報】\n\n"
    post_to_slack(header + text)


if __name__ == "__main__":
    main()
