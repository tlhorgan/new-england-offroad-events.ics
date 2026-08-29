import hashlib
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from icalendar import Calendar, Event

OUTPUT = Path("new-england-offroad-events.ics")
NEBN_URL = "https://www.northeastbronconation.com/events-1"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; NewEnglandOffroadCalendar/2.0)"}


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def norm(value):
    return re.sub(r"[^a-z0-9]+", " ", clean(value).lower()).strip()


def parse_date_range(text, year):
    text = clean(text).replace("–", "-").replace("—", "-")
    m = re.search(
        r"(?P<month>January|February|March|April|May|June|July|August|September|October|November|December)\s+"
        r"(?P<start>\d{1,2})(?:\s*-\s*(?P<end>\d{1,2}))?(?:,)?\s*(?P<year>20\d{2})?",
        text,
        re.I,
    )
    if not m:
        return None, None
    y = int(m.group("year") or year)
    month = datetime.strptime(m.group("month")[:3], "%b").month
    start = datetime(y, month, int(m.group("start")), 9, 0)
    end = datetime(y, month, int(m.group("end") or m.group("start")), 17, 0)
    return start, end


def fetch_events():
    response = requests.get(NEBN_URL, headers=HEADERS, timeout=45)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    lines = [clean(x) for x in soup.stripped_strings if clean(x)]
    year = datetime.now().year
    today = datetime.now().date() - timedelta(days=1)
    records = []

    for i, line in enumerate(lines):
        if len(line) < 5 or len(line) > 100:
            continue
        window = lines[i + 1:i + 8]
        date_line = next((x for x in window if re.search(
            r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}", x, re.I
        )), None)
        if not date_line:
            continue
        start, end = parse_date_range(date_line, year)
        if not start or start.date() < today:
            continue
        if any(x in line.lower() for x in ("join ", "sign up", "get muddy", "cruise with", "leaf peeping", "hit the beach", "get festive")):
            continue
        if not any(k in line.lower() for k in (
            "bronco", "may-it", "catskill", "rhode island", "maine lighthouse",
            "fall foliage", "acadia", "feud", "sunday ride", "lobster trap"
        )):
            continue

        location = ""
        for x in window:
            if x != date_line and re.search(r"\b(?:MA|ME|NH|VT|CT|RI)\b", x) and len(x) <= 100:
                location = x
                break

        records.append({"title": line, "start": start, "end": end, "location": location})

    unique = {}
    for record in records:
        unique[(record["start"].date(), norm(record["title"]))] = record
    result = list(unique.values())
    print(f"Northeast Bronco Nation: {len(result)} future New England events")
    return result


def main():
    if not OUTPUT.exists():
        raise RuntimeError(f"{OUTPUT} does not exist")

    cal = Calendar.from_ical(OUTPUT.read_bytes())
    existing = set()
    for ev in cal.walk("VEVENT"):
        try:
            start = ev.decoded("DTSTART")
            day = start.date() if hasattr(start, "date") else start
        except Exception:
            continue
        existing.add((day, norm(ev.get("SUMMARY", ""))))

    added = 0
    for item in fetch_events():
        key = (item["start"].date(), norm(item["title"]))
        if key in existing:
            continue
        ev = Event()
        seed = f"{item['title']}|{item['start'].date()}|{item['location']}"
        ev.add("uid", hashlib.sha256(seed.encode()).hexdigest()[:30] + "@northeast-bronco-nation")
        ev.add("dtstamp", datetime.now(timezone.utc))
        ev.add("summary", item["title"])
        ev.add("dtstart", item["start"])
        ev.add("dtend", item["end"])
        if item["location"]:
            ev.add("location", item["location"])
        ev.add("url", NEBN_URL)
        ev.add("description", f"Northeast Bronco Nation event.\n\nSource: Northeast Bronco Nation\n{NEBN_URL}")
        cal.add_component(ev)
        existing.add(key)
        added += 1

    OUTPUT.write_bytes(cal.to_ical())
    print(f"Added {added} Northeast Bronco Nation events to {OUTPUT}")


if __name__ == "__main__":
    main()
