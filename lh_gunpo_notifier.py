"""
LH청약플러스 - 군포 지역 임대주택(행복주택/공공주택 등) 신규 공고 텔레그램 알림 스크립트

동작 방식
- LH청약플러스 "임대주택 > 공고문" 목록(mi=1026)을 가져와서
- 공고명 또는 지역에 "군포"가 포함된 공고만 추려낸 뒤
- 이전에 알림을 보낸 적 없는(seen.json에 없는) 새 공고만 텔레그램으로 전송합니다.

필요 환경변수
- TELEGRAM_BOT_TOKEN : @BotFather 에서 발급받은 봇 토큰
- TELEGRAM_CHAT_ID   : 알림을 받을 채팅방(개인 chat_id 등)

필터 지역/키워드를 바꾸고 싶으면 아래 KEYWORDS 리스트를 수정하세요.
"""

import os
import re
import json
import sys
import requests
from bs4 import BeautifulSoup

LH_URL = "https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancList.do?mi=1026"
KEYWORDS = ["군포"]  # 필요하면 ["군포", "산본"] 처럼 지역명을 추가하세요
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seen.json")

BADGE_PATTERN = re.compile(r"(D-\d+|\d+일전|오늘|마감임박|NEW)\s*$")

HEADER_KEYMAP = {
    "유형": "type",
    "공고명": "title",
    "지역": "region",
    "게시일": "posted",
    "마감일": "deadline",
    "상태": "status",
}


def fetch_listings():
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )
    }
    res = requests.get(LH_URL, headers=headers, timeout=30)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")

    table = soup.find("table")
    if table is None:
        raise RuntimeError("공고 목록 테이블을 찾지 못했습니다. 페이지 구조가 바뀌었을 수 있습니다.")

    # 헤더에서 컬럼 순서 파악 (사이트 구조가 바뀌어도 최대한 안전하게 동작하도록)
    header_cells = table.find("thead").find_all("th") if table.find("thead") else []
    col_map = {}
    for idx, th in enumerate(header_cells):
        text = th.get_text(strip=True)
        for kr, key in HEADER_KEYMAP.items():
            if kr in text:
                col_map[key] = idx

    body = table.find("tbody")
    if body is None:
        return []

    rows = []
    for tr in body.find_all("tr"):
        cells = tr.find_all("td")
        if not cells:
            continue

        def cell_text(key, default_idx=None):
            idx = col_map.get(key, default_idx)
            if idx is None or idx >= len(cells):
                return ""
            return cells[idx].get_text(" ", strip=True)

        title = cell_text("title", 2)
        title = BADGE_PATTERN.sub("", title).strip()

        row = {
            "type": cell_text("type", 1),
            "title": title,
            "region": cell_text("region", 3),
            "posted": cell_text("posted", 5),
            "deadline": cell_text("deadline", 6),
            "status": cell_text("status", 7),
        }
        if row["title"]:
            rows.append(row)

    return rows


def load_seen():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            try:
                return set(json.load(f))
            except json.JSONDecodeError:
                return set()
    return set()


def save_seen(seen):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f, ensure_ascii=False, indent=2)


def send_telegram(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    res = requests.post(
        url,
        data={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
        timeout=30,
    )
    res.raise_for_status()


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 환경변수가 필요합니다.", file=sys.stderr)
        sys.exit(1)

    rows = fetch_listings()
    matches = [
        r for r in rows
        if any(kw in r["title"] or kw in r["region"] for kw in KEYWORDS)
    ]

    seen = load_seen()
    new_items = []
    for m in matches:
        key = f"{m['title']}|{m['posted']}"
        if key not in seen:
            new_items.append((key, m))

    if not new_items:
        print("새로운 군포 관련 공고가 없습니다.")
        return

    for key, item in new_items:
        text = (
            f"[{item['type']}] 군포 관련 공고\n"
            f"{item['title']}\n"
            f"지역: {item['region']} | 상태: {item['status']}\n"
            f"게시일: {item['posted']} ~ 마감일: {item['deadline']}\n"
            f"목록 확인: {LH_URL}"
        )
        send_telegram(token, chat_id, text)
        seen.add(key)

    save_seen(seen)
    print(f"{len(new_items)}건 알림 발송 완료")


if __name__ == "__main__":
    main()
