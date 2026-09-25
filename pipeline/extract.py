"""Turn raw news text into structured facts the model can use.

With ANTHROPIC_API_KEY set, Claude reads each new item. Without it, a simple keyword
fallback tags status words so the board still flags likely injury news.
"""
import os, re, json
from . import config

STATUSES = ["out", "doubtful", "questionable", "will play", "will start", "benched", "injured reserve",
            "traded", "signed", "released", "suspended", "other"]

PROMPT = """You extract NFL availability facts from news items for a betting model.
Team codes: {teams}

For EACH item return one JSON object with:
- "id": the item id
- "team": team code the news is about (or null)
- "player": player name (or null)
- "position": position abbreviation if stated or obvious (QB, RB, WR, TE, OL, DL, LB, CB, S, K), else null
- "status": one of {statuses}
- "starting_qb": if the item says who WILL START at quarterback for a team's next game, that QB's full name, else null
- "confirmed": true only if the item states it as fact (e.g. "ruled out", "will start", "placed on IR"), false for maybes or speculation
- "summary": 12 words or fewer

Return ONLY a JSON array, no other text.

Items:
{items}"""


def with_claude(items):
    import anthropic
    client = anthropic.Anthropic()
    out = {}
    for i in range(0, len(items), 25):
        batch = items[i:i + 25]
        payload = "\n".join(json.dumps({"id": it["id"], "author": it["author"], "text": it["text"][:600]}) for it in batch)
        msg = client.messages.create(
            model=config.CLAUDE_MODEL, max_tokens=4000,
            messages=[{"role": "user", "content": PROMPT.format(
                teams=", ".join(config.TEAMS), statuses=", ".join(STATUSES), items=payload)}])
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        text = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.M).strip()
        for rec in json.loads(text):
            if rec.get("id"):
                out[rec["id"]] = rec
    return out


KEYWORDS = [("ruled out", "out", True), ("will not play", "out", True), ("won't play", "out", True),
            ("placed on injured reserve", "injured reserve", True), ("on ir", "injured reserve", True),
            ("will start", "will start", True), ("doubtful", "doubtful", False), ("questionable", "questionable", False),
            ("traded", "traded", True), ("trade:", "traded", True), ("released", "released", True), ("suspended", "suspended", True)]


def with_keywords(items):
    out = {}
    for it in items:
        t = it["text"].lower()
        status, conf = "other", False
        for k, s, c in KEYWORDS:
            if k in t:
                status, conf = s, c
                break
        out[it["id"]] = dict(id=it["id"], team=(it["teams"] or [None])[0], player=None, position=None,
                             status=status, starting_qb=None, confirmed=conf, summary=None)
    return out


def extract(items):
    if not items:
        return {}
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            res = with_claude(items)
            print(f"[extract] Claude parsed {len(res)} items")
            return res
        except Exception as ex:
            print(f"[extract] Claude failed ({ex}), using keyword fallback")
    return with_keywords(items)
