#!/usr/bin/env python3
"""
Darmowy monitor fanpage'y na Facebooku (zamiennik rss.app).

Co robi:
  - wczytuje liste adresow fanpage'y z pages.txt
  - dla kazdej strony otwiera ja w headless Chromium (Playwright),
    zamyka baner cookies, przewija, wyciaga widoczne posty
  - dopisuje nowe posty do data/feed.json (bez duplikatow)
  - zapisuje data/status.json z informacja o stanie kazdej strony
    (ok / brak_postow / blokada / blad) - to pokazuje dashboard

Ograniczenia, o ktorych trzeba wiedziec:
  - Facebook NIE udostepnia oficjalnego, darmowego API do stron,
    ktorych nie jestes adminem. To narzedzie dziala przez "czytanie"
    publicznie widocznej strony tak, jak widzialaby ja przegladarka
    bez zalogowania - czyli dokladnie to, co "pod maska" robia
    platne serwisy typu rss.app.
  - Facebook regularnie zmienia znaczniki HTML i bywa, ze wymusza
    logowanie do czesci tresci. Jesli dla jakiejs strony w
    data/status.json pojawi sie "blokada" albo "brak_postow" -
    zobacz zrzut ekranu w debug/<strona>.png, zeby sprawdzic co
    faktycznie zwrocil Facebook, i daj znac / popraw selektory w
    funkcji extract_posts_from_page ponizej.
  - To nie jest oficjalnie wspierane przez Facebooka - traktuj jako
    prywatne, male narzedzie do wlasnego uzytku, a nie produkt do
    masowej skali.
"""

import json
import os
import re
import sys
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

BASE_DIR = Path(__file__).parent
PAGES_FILE = BASE_DIR / "pages.txt"
DATA_DIR = BASE_DIR / "data"
FEED_FILE = DATA_DIR / "feed.json"
STATUS_FILE = DATA_DIR / "status.json"
DEBUG_DIR = BASE_DIR / "debug"

MAX_ITEMS_TOTAL = 500      # ile ostatnich postow trzymamy lacznie w feed.json
MAX_ITEMS_PER_PAGE = 60    # limit na jedna strone (zeby jedna aktywna strona nie zdominowala feedu)
SCROLL_STEPS = 4           # ile razy przewijamy strone, zeby doladowac wiecej postow
NAV_TIMEOUT_MS = 45_000

COOKIE_BUTTON_TEXTS = [
    "Zezwól na wszystkie pliki cookie",
    "Zezwol na wszystkie pliki cookie",
    "Akceptuję wszystkie",
    "Zaakceptuj wszystkie",
    "Allow all cookies",
    "Accept all",
    "Accept All",
    "Only allow essential cookies",
]

LOGIN_WALL_MARKERS = [
    "log in to facebook",
    "zaloguj się do facebooka",
    "zaloguj sie do facebooka",
    "you must log in",
    "musisz się zalogować",
]


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def load_pages() -> list[str]:
    if not PAGES_FILE.exists():
        log(f"BLAD: brak pliku {PAGES_FILE}")
        return []
    urls = []
    for line in PAGES_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(line)
    return urls


def page_slug(url: str) -> str:
    path = urlparse(url).path.strip("/")
    return path.split("/")[0] if path else url


def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log(f"UWAGA: {path} jest uszkodzony, zaczynam od nowa")
    return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def make_id(page_slug_: str, permalink: str | None, text: str) -> str:
    if permalink:
        return hashlib.sha1(permalink.encode("utf-8")).hexdigest()
    basis = f"{page_slug_}|{text[:200]}"
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()


def dismiss_cookie_banner(page) -> None:
    for text in COOKIE_BUTTON_TEXTS:
        try:
            btn = page.get_by_role("button", name=text, exact=False)
            if btn.count() > 0:
                btn.first.click(timeout=3000)
                log(f"  cookies: kliknieto '{text}'")
                page.wait_for_timeout(1000)
                return
        except Exception:
            continue


def looks_like_login_wall(page) -> bool:
    try:
        content = page.content().lower()
    except Exception:
        return False
    return any(marker in content for marker in LOGIN_WALL_MARKERS)


def extract_posts_from_page(page, url: str) -> list[dict]:
    """
    Facebook zmienia nazwy klas CSS na losowe, ale posty niemal zawsze
    maja role="article" w drzewie dostepnosci (accessibility tree) -
    to najbardziej stabilny hak, jaki mamy.
    """
    articles = page.locator('[role="article"]')
    count = articles.count()
    results = []
    slug = page_slug(url)

    for i in range(min(count, MAX_ITEMS_PER_PAGE)):
        art = articles.nth(i)
        try:
            text = art.inner_text(timeout=2000).strip()
        except Exception:
            continue
        if not text or len(text) < 3:
            continue

        permalink = None
        try:
            links = art.locator("a[href]")
            for j in range(min(links.count(), 15)):
                href = links.nth(j).get_attribute("href") or ""
                if any(marker in href for marker in ("/posts/", "/videos/", "/photos/", "story_fbid", "permalink.php", "/reel/")):
                    permalink = href.split("?")[0]
                    if permalink.startswith("/"):
                        permalink = "https://www.facebook.com" + permalink
                    break
        except Exception:
            pass

        snippet = text.replace("\n", " ").strip()
        snippet = re.sub(r"\s+", " ", snippet)[:600]

        results.append({
            "id": make_id(slug, permalink, snippet),
            "page": slug,
            "page_url": url,
            "text": snippet,
            "post_url": permalink,
            "scraped_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })

    return results


def scrape_page(browser, url: str) -> tuple[list[dict], str, str]:
    """Zwraca (posty, status, komunikat) dla jednej strony."""
    slug = page_slug(url)
    context = browser.new_context(
        locale="pl-PL",
        viewport={"width": 1280, "height": 1600},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
    )
    page = context.new_page()
    page.set_default_timeout(NAV_TIMEOUT_MS)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
        page.wait_for_timeout(2000)
        dismiss_cookie_banner(page)

        if looks_like_login_wall(page):
            DEBUG_DIR.mkdir(exist_ok=True)
            page.screenshot(path=str(DEBUG_DIR / f"{slug}.png"), full_page=True)
            (DEBUG_DIR / f"{slug}.html").write_text(page.content(), encoding="utf-8")
            return [], "blokada", "Facebook pokazal ekran logowania zamiast tresci strony"

        for _ in range(SCROLL_STEPS):
            page.mouse.wheel(0, 2200)
            page.wait_for_timeout(1200)

        posts = extract_posts_from_page(page, url)

        if not posts:
            DEBUG_DIR.mkdir(exist_ok=True)
            page.screenshot(path=str(DEBUG_DIR / f"{slug}.png"), full_page=True)
            (DEBUG_DIR / f"{slug}.html").write_text(page.content(), encoding="utf-8")
            return [], "brak_postow", "Nie znaleziono elementow [role=article] - sprawdz debug/"

        return posts, "ok", f"znaleziono {len(posts)} widocznych postow"

    except PlaywrightTimeoutError:
        return [], "blad", "timeout przy ladowaniu strony"
    except Exception as exc:
        return [], "blad", f"{type(exc).__name__}: {exc}"
    finally:
        context.close()


def main() -> int:
    urls = load_pages()
    if not urls:
        log("Brak stron w pages.txt - dodaj przynajmniej jeden adres i uruchom ponownie.")
        return 1

    existing_feed = load_json(FEED_FILE, [])
    existing_ids = {item["id"] for item in existing_feed}
    status_report = {}
    new_count = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=os.environ.get("HEADFUL") != "1")
        for url in urls:
            slug = page_slug(url)
            log(f"Sprawdzam: {url}")
            posts, status, message = scrape_page(browser, url)
            status_report[slug] = {
                "url": url,
                "status": status,
                "message": message,
                "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            log(f"  -> {status}: {message}")

            for post in posts:
                if post["id"] not in existing_ids:
                    existing_feed.append(post)
                    existing_ids.add(post["id"])
                    new_count += 1

            time.sleep(2)  # male odstepy miedzy stronami, zeby nie walic requestow seria
        browser.close()

    existing_feed.sort(key=lambda x: x["scraped_at"], reverse=True)
    existing_feed = existing_feed[:MAX_ITEMS_TOTAL]

    save_json(FEED_FILE, existing_feed)
    save_json(STATUS_FILE, status_report)

    log(f"Gotowe. Nowych postow: {new_count}. Lacznie w feed.json: {len(existing_feed)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
