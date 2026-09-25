"""Collect NFL news from ESPN (free) and X insiders (paid API, optional).

Every source is wrapped so a failure is logged and skipped instead of stopping the run.
Each item is normalized to: id, source, author, time (ISO UTC), text, url, teams (list of abbrs).
"""
import os, re, json, datetime as dt
import requests
from . import config

UA = {"User-Agent": "Mozilla/5.0 (nfl-model personal research)"}
TIMEOUT = 20
NAME_TO_ABBR = {}
for abbr, names in config.TEAMS.items():
    for n in names:
        NAME_TO_ABBR[n.lower()] = abbr


def teams_in_text(text):
    t = text.lower()
    found = []
    for name, abbr in NAME_TO_ABBR.items():
        if re.search(r"\b" + re.escape(name) + r"\b", t) and abbr not in found:
            found.append(abbr)
    return found


def _log(msg):
    print(f"[news] {msg}")


def espn_contributor(slug):
    """ESPN contributor 'shortstop' posts (short insider updates), e.g. Adam Schefter."""
    url = f"https://site.web.api.espn.com/apis/v2/flex?contributor={slug}&limit=50&pubkey=contributor-page"
    data = requests.get(url, headers=UA, timeout=TIMEOUT).json()
    items = []
    for col in data.get("columns", []):
        for block in col.get("items", []):
            for f in block.get("feed", []) or []:
                text = (f.get("payload") or f.get("descriptions", {}).get("headline") or "").strip()
                if not text:
                    continue
                teams = [NAME_TO_ABBR[c["description"].lower()] for c in f.get("categories", [])
                         if c.get("type") == "team" and c.get("description", "").lower() in NAME_TO_ABBR]
                web = next((l["href"] for l in f.get("links", []) if "web" in l.get("rels", [])), None)
                author = next((c.get("displayName") or c.get("descriptions", {}).get("displayName")
                               for c in f.get("contributors", [])), slug)
                items.append(dict(id=f"espn-{f['id']}", source="ESPN", author=author,
                                  time=f.get("dates", {}).get("created"), text=text, url=web,
                                  teams=teams or teams_in_text(text)))
    return items


def espn_headlines():
    """ESPN's general NFL news feed."""
    data = requests.get("https://site.api.espn.com/apis/site/v2/sports/football/nfl/news?limit=50",
                        headers=UA, timeout=TIMEOUT).json()
    items = []
    for a in data.get("articles", []):
        text = a.get("headline", "")
        if a.get("description"):
            text += ". " + a["description"]
        teams = []
        for c in a.get("categories", []):
            d = (c.get("description") or "").lower()
            if c.get("type") == "team" and d in NAME_TO_ABBR:
                teams.append(NAME_TO_ABBR[d])
        items.append(dict(id=f"espnnews-{a.get('id', a.get('headline'))}", source="ESPN", author=a.get("byline") or "ESPN",
                          time=a.get("published"), text=text, url=a.get("links", {}).get("web", {}).get("href"),
                          teams=teams or teams_in_text(text)))
    return items


def x_insiders(state):
    """Recent posts from insider accounts via the official X API (pay-per-use).

    Needs X_BEARER_TOKEN. Uses since_id saved in state so each post is only paid for once.
    """
    token = os.environ.get("X_BEARER_TOKEN")
    if not token:
        _log("X_BEARER_TOKEN not set, skipping X")
        return []
    query = "(" + " OR ".join(f"from:{h}" for h in config.X_HANDLES) + ") -is:retweet -is:reply"
    params = {"query": query, "max_results": min(100, max(10, config.X_MAX_POSTS_PER_RUN)),
              "tweet.fields": "created_at,author_id", "expansions": "author_id", "user.fields": "username"}
    if state.get("x_since_id"):
        params["since_id"] = state["x_since_id"]
    r = requests.get("https://api.x.com/2/tweets/search/recent", params=params,
                     headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT)
    if r.status_code != 200:
        _log(f"X API returned {r.status_code}: {r.text[:300]}")
        return []
    data = r.json()
    users = {u["id"]: u["username"] for u in data.get("includes", {}).get("users", [])}
    items = []
    for t in data.get("data", []):
        handle = users.get(t.get("author_id"), "unknown")
        items.append(dict(id=f"x-{t['id']}", source="X", author="@" + handle, time=t.get("created_at"),
                          text=t["text"], url=f"https://x.com/{handle}/status/{t['id']}", teams=teams_in_text(t["text"])))
    if data.get("meta", {}).get("newest_id"):
        state["x_since_id"] = data["meta"]["newest_id"]
    _log(f"X: {len(items)} new posts")
    return items


def collect(state):
    items = []
    for name, fn in [(f"ESPN {s}", (lambda s=s: espn_contributor(s))) for s in config.ESPN_CONTRIBUTORS] + \
                    [("ESPN headlines", espn_headlines), ("X insiders", lambda: x_insiders(state))]:
        try:
            got = fn()
            _log(f"{name}: {len(got)} items")
            items += got
        except Exception as ex:
            _log(f"{name} failed, skipping: {ex}")
    return items


def merge_history(history, new_items, now=None):
    """Keep a rolling store of news, deduplicated by id, trimmed to the lookback window."""
    now = now or dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(days=config.NEWS_LOOKBACK_DAYS)
    by_id = {h["id"]: h for h in history}
    fresh = []
    for it in new_items:
        if it["id"] not in by_id:
            by_id[it["id"]] = it
            fresh.append(it)
    def ts(x):
        try:
            return dt.datetime.fromisoformat(str(x.get("time")).replace("Z", "+00:00"))
        except Exception:
            return now
    kept = [h for h in by_id.values() if ts(h) >= cutoff]
    kept.sort(key=ts, reverse=True)
    return kept, fresh
