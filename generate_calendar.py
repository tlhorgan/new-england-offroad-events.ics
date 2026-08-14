from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dtparser
from icalendar import Calendar, Event


OUTPUT = Path("new-england-offroad-events.ics")

ATJ_URL = "https://addictedtojeeps.com/events"
MARS_URL = "https://www.massroversociety.com/events"
MLO_URL = "https://mainlineoverland.com/products/mlo-new-england-2026-trail-ride-series"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/142.0.0.0 Safari/537.36"
    )
}


def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def get(url):
    r = requests.get(url, headers=HEADERS, timeout=45)
    r.raise_for_status()
    return r.text


def make_item(title, start, end, location, description, url, source):
    return {
        "title": clean(title),
        "start": start,
        "end": end,
        "location": clean(location),
        "description": clean(description),
        "url": url,
        "source": source,
    }


def fetch_addicted_to_jeeps():
    html = get(ATJ_URL)
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    lines = [clean(x) for x in text.splitlines() if clean(x)]

    items = []
    current_title = None

    for i, line in enumerate(lines):
        if re.search(r"\b2026\b", line) and (
            "Saturday" in line
            or "Sunday" in line
            or "Friday" in line
            or re.search(
                r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)",
                line,
                re.I,
            )
        ):
            current_title = line

        if not current_title:
            continue

        m = re.search(
            r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)?"
            r"\s*,?\s*"
            r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
            r"[a-z]*\s+\d{1,2})(?:st|nd|rd|th)?"
            r"(?:\s*[-–]\s*"
            r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)?"
            r"\s*,?\s*"
            r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
            r"[a-z]*\s+\d{1,2})(?:st|nd|rd|th)?)?",
            line,
            re.I,
        )

        if not m:
            continue

        try:
            start = dtparser.parse(f"{m.group(1)} 2026").date()
            end = (
                dtparser.parse(f"{m.group(2)} 2026").date()
                if m.group(2)
                else start
            )
        except Exception:
            continue

        title = re.sub(
            r"\s*[-–]\s*(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday).*$",
            "",
            current_title,
            flags=re.I,
        )
        title = re.sub(r"\s*[-–]\s*\d.*$", "", title).strip()

        nearby = " ".join(lines[i:i + 10])

        loc_match = re.search(
            r"Location:\s*(.+?)(?:Tickets|More info|http|$)",
            nearby,
            re.I,
        )
        location = loc_match.group(1).strip() if loc_match else ""

        items.append(
            make_item(
                title=title,
                start=start,
                end=end + timedelta(days=1),
                location=location,
                description="",
                url=ATJ_URL,
                source="Addicted to Jeeps",
            )
        )

        current_title = None

    print(f"Addicted to Jeeps: {len(items)} events")
    return items


def fetch_mars():
    html = get(MARS_URL)
    soup = BeautifulSoup(html, "html.parser")

    urls = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/events/" not in href:
            continue

        url = urljoin(MARS_URL, href).split("?")[0].split("#")[0]

        if url.rstrip("/") != MARS_URL.rstrip("/"):
            urls.add(url)

    items = []

    for url in sorted(urls):
        try:
            page = BeautifulSoup(get(url), "html.parser")

            h1 = page.find("h1")
            if not h1:
                continue

            title = clean(h1.get_text(" ", strip=True))
            text = clean(page.get_text(" ", strip=True))

            date_match = re.search(
                r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+"
                r"([A-Za-z]+\s+\d{1,2},\s+2026)"
                r"\s+(\d{1,2}:\d{2}\s*[AP]M)"
                r".*?"
                r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+"
                r"([A-Za-z]+\s+\d{1,2},\s+2026)"
                r"\s+(\d{1,2}:\d{2}\s*[AP]M)",
                text,
                re.I,
            )

            if date_match:
                start = dtparser.parse(
                    f"{date_match.group(2)} {date_match.group(3)}"
                )
                end = dtparser.parse(
                    f"{date_match.group(5)} {date_match.group(6)}"
                )
            else:
                single_match = re.search(
                    r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+"
                    r"([A-Za-z]+\s+\d{1,2},\s+2026)"
                    r"\s+(\d{1,2}:\d{2}\s*[AP]M)"
                    r"\s+(\d{1,2}:\d{2}\s*[AP]M)",
                    text,
                    re.I,
                )

                if not single_match:
                    continue

                start = dtparser.parse(
                    f"{single_match.group(2)} {single_match.group(3)}"
                )
                end = dtparser.parse(
                    f"{single_match.group(2)} {single_match.group(4)}"
                )

            location = ""

            map_match = re.search(
                r"\b([A-Za-z0-9 .'-]+,\s*(?:MA|ME|NH|VT|CT|RI)(?:\s+USA)?)\s*\(map\)",
                text,
                re.I,
            )

            if map_match:
                location = map_match.group(1)

            items.append(
                make_item(
                    title=title,
                    start=start,
                    end=end,
                    location=location,
                    description="",
                    url=url,
                    source="Massachusetts Rover Society",
                )
            )

        except Exception as exc:
            print(f"MARS skip {url}: {exc}")

    print(f"Massachusetts Rover Society: {len(items)} events")
    return items


def fetch_main_line_overland():
    html = get(MLO_URL)
    soup = BeautifulSoup(html, "html.parser")
    text = clean(soup.get_text(" ", strip=True))

    entries = [
        ("April 26, 2026", "New Hampshire", "Green Ride"),
        ("May 9, 2026", "Vermont", "Green Ride"),
        ("June 20, 2026", "", "Blue Ride"),
        ("July 11, 2026", "New Hampshire", "Blue Ride"),
        ("July 12, 2026", "New Hampshire", "Green Ride"),
        ("August 22, 2026", "", "Blue Ride"),
        ("September 26, 2026", "Vermont", "Blue Ride"),
        ("September 27, 2026", "Vermont", "Green Ride"),
        ("October 25, 2026", "New Hampshire", "Green Ride"),
        ("November 21, 2026", "", "Blue Ride"),
        ("December 5, 2026", "Vermont", "Blue/Black Ride"),
    ]

    items = []

    for date_text, location, ride_type in entries:
        d = dtparser.parse(date_text)

        start = d.replace(hour=8, minute=30)
        end = d.replace(hour=17, minute=0)

        items.append(
            make_item(
                title=f"MLO New England Trail Ride - {ride_type}",
                start=start,
                end=end,
                location=location,
                description=(
                    "Main Line Overland New England Trail Ride Series "
                    "with Ridgeback Guide Service."
                ),
                url=MLO_URL,
                source="Main Line Overland",
            )
        )

    print(f"Main Line Overland: {len(items)} events")
    return items


def normalize(text):
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def dedupe(items):
    seen = set()
    output = []

    for item in sorted(items, key=lambda x: (str(x["start"]), x["title"])):
        start_key = str(item["start"])[:10]
        key = (
            start_key,
            normalize(item["title"]),
            normalize(item["location"]),
        )

        if key in seen:
            continue

        seen.add(key)
        output.append(item)

    return output


def build_calendar(items):
    cal = Calendar()
    cal.add("prodid", "-//New England Offroad Events//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("x-wr-calname", "New England Off-Road Events")
    cal.add("x-wr-timezone", "America/New_York")

    for item in items:
        ev = Event()

        uid_source = (
            f"{item['title']}|{item['start']}|"
            f"{item['location']}|{item['source']}"
        )

        ev.add(
            "uid",
            hashlib.sha256(uid_source.encode()).hexdigest()[:30]
            + "@new-england-offroad",
        )

        ev.add("dtstamp", datetime.now(timezone.utc))
        ev.add("summary", item["title"])
        ev.add("dtstart", item["start"])
        ev.add("dtend", item["end"])

        if item["location"]:
            ev.add("location", item["location"])

        ev.add("url", item["url"])

        desc = item["description"]

        if desc:
            desc += "\n\n"

        desc += f"Source: {item['source']}\n{item['url']}"

        ev.add("description", desc)

        cal.add_component(ev)

    OUTPUT.write_bytes(cal.to_ical())

    print(f"Wrote {OUTPUT} with {len(items)} events")


def main():
    all_items = []

    for name, fn in [
        ("Addicted to Jeeps", fetch_addicted_to_jeeps),
        ("Massachusetts Rover Society", fetch_mars),
        ("Main Line Overland", fetch_main_line_overland),
    ]:
        try:
            all_items.extend(fn())
        except Exception as exc:
            print(f"ERROR loading {name}: {exc}")

    if not all_items:
        raise RuntimeError(
            "No events collected; existing calendar was not replaced."
        )

    unique = dedupe(all_items)

    print(
        f"Collected {len(all_items)} source events; "
        f"{len(unique)} after deduplication"
    )

    if len(unique) < 10:
        raise RuntimeError(
            f"Only {len(unique)} unique events generated; "
            "refusing to publish a bad feed."
        )

    build_calendar(unique)


if __name__ == "__main__":
    main()
