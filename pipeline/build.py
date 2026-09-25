"""Main entry point: python -m pipeline.build

1. Collect news (ESPN always, X if a token is set) and extract structured facts
2. Run the three models
3. Apply confirmed QB changes from the news
4. Write docs/index.html (the board), docs/data.json, and updated state files
"""
import json, os, re, datetime as dt, pathlib
import pandas as pd
from . import config, news, extract, model

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATE, HISTORY = ROOT / "state" / "state.json", ROOT / "state" / "news.json"
DOCS = ROOT / "docs"


def jload(p, default):
    try:
        return json.loads(p.read_text())
    except Exception:
        return default


def norm_name(n):
    return re.sub(r"[^a-z ]", "", (n or "").lower().replace(" jr", "").replace(" iii", "").replace(" ii", "")).strip()


def main():
    now = dt.datetime.now(dt.timezone.utc)
    state = jload(STATE, {})
    history = jload(HISTORY, [])

    # 1. News
    raw = news.collect(state)
    history, fresh = news.merge_history(history, raw, now)
    facts = extract.extract(fresh)
    for h in history:
        if h["id"] in facts:
            h["facts"] = facts[h["id"]]
    print(f"[build] {len(fresh)} new items, {len(history)} in the {config.NEWS_LOOKBACK_DAYS}-day window")

    # 2. Models
    sched, cur, qbv, qbs, epa_pp = model.load()
    d, h, mstate, coef, trust, mae_test = model.fit_and_score(sched, qbv, epa_pp)
    upcoming = d[(d.season == cur) & d.result.isna() & d.spread_line.notna()]
    week = int(upcoming.week.min())
    upcoming = upcoming[upcoming.week == week].copy()
    inj = model.injury_flags(cur, week)

    # 3. QB changes from news (newest confirmed "will start" per team wins)
    name_to_id = {}
    for r in qbs.sort_values('season').itertuples():
        name_to_id[norm_name(r.player_display_name)] = r.player_id
    starter_news = {}
    for item in sorted(history, key=lambda x: x.get("time") or ""):
        f = item.get("facts") or {}
        if f.get("confirmed") and f.get("starting_qb") and f.get("team") in config.TEAMS:
            starter_news[f["team"]] = (f["starting_qb"], item)

    games = []
    for g in upcoming.itertuples():
        row = dict(date=str(g.gameday), time=str(g.gametime), away=g.away_team, home=g.home_team,
                   aqb=g.away_qb_name, hqb=g.home_qb_name, market=float(g.spread_line),
                   elo=round(g.elo, 1), eloqb=float(g.eloqb), blend=float(g.blend),
                   aqa=round(g.aqa, 1), hqa=round(g.hqa, 1),
                   hodds=int(g.home_spread_odds) if pd.notna(g.home_spread_odds) else -110,
                   aodds=int(g.away_spread_odds) if pd.notna(g.away_spread_odds) else -110,
                   hinj=inj.get(g.home_team, []), ainj=inj.get(g.away_team, []), alerts=[], news=[])
        for side, team, listed in (('h', g.home_team, g.home_qb_name), ('a', g.away_team, g.away_qb_name)):
            if team in starter_news and config.AUTO_QB_OVERRIDE:
                name, item = starter_news[team]
                if norm_name(name) != norm_name(listed):
                    pid = name_to_id.get(norm_name(name))
                    tq = mstate['TQ'].get(team)
                    if tq is not None:
                        new_adj = model.QB_MULT * (mstate['Q'].get(pid, model.NEW_QB) - tq) / 25
                        old_adj = row[side + 'qa']
                        delta = (new_adj - old_adj) * (1 if side == 'h' else -1)
                        row['eloqb'] += delta
                        row['blend'] += coef[1] * delta
                        row[side + 'qa'] = round(new_adj, 1)
                        row[side + 'qb'] = name
                        note = " No history for this QB, rated as a new starter." if pid is None else ""
                        row['alerts'].append(f"Starter updated from news: {name} replaces {listed} ({item['author']}).{note}")
            # listed QB ruled out with no named replacement
            for item in history:
                f = item.get("facts") or {}
                if (f.get("team") == team and f.get("status") in ("out", "injured reserve") and f.get("confirmed")
                        and norm_name(f.get("player")) == norm_name(row[side + 'qb'])):
                    row['alerts'].append(f"{row[side + 'qb']} reported {f['status']} ({item['author']}). Lines may be stale.")
        row['eloqb'], row['blend'] = round(row['eloqb'], 1), round(row['blend'], 1)
        for item in history:
            if set(item.get("teams") or []) & {g.home_team, g.away_team} or \
               (item.get("facts") or {}).get("team") in (g.home_team, g.away_team):
                f = item.get("facts") or {}
                row['news'].append(dict(author=item["author"], time=item.get("time"), url=item.get("url"),
                                        text=f.get("summary") or item["text"][:180], status=f.get("status"),
                                        confirmed=bool(f.get("confirmed"))))
        row['news'] = row['news'][:4]
        games.append(row)

    # 4. Output
    def back(m):
        return [dict(th=th, w=int(w.sum()), l=int((~w).sum())) for th in range(8) for w in [model.ats(h, m, th)[0]]]
    def seasons(m, th):
        won, s = model.ats(h, m, th)
        gg = won.groupby(s).agg(['count', 'sum'])
        return [dict(season=int(i), bets=int(r['count']), w=int(r['sum'])) for i, r in gg.iterrows()]
    active = set(d[d.season == cur].home_team)
    power = sorted([dict(team=t, elo=round((mstate['R'][t] - 1500) / 25, 1),
                         epa=round(mstate['OFF'].get(t, 0) - mstate['DEF'].get(t, 0), 3)) for t in active],
                   key=lambda x: -x['elo'])
    feed = [dict(author=i["author"], source=i["source"], time=i.get("time"), url=i.get("url"), teams=i.get("teams") or [],
                 text=i["text"][:280], status=(i.get("facts") or {}).get("status"),
                 confirmed=bool((i.get("facts") or {}).get("confirmed"))) for i in history[:40]]
    data = dict(season=cur, week=week, asof=now.strftime("%Y-%m-%d"), updated=now.isoformat(timespec="minutes"),
                games=games, power=power, back={m: back(m) for m in model.MODELS},
                seasons={m: {th: seasons(m, th) for th in range(8)} for m in model.MODELS},
                maeTest=mae_test, trust=trust, keyw=model.key_weights(d), blendCoef=[round(float(x), 3) for x in coef],
                feed=feed, xEnabled=bool(os.environ.get("X_BEARER_TOKEN")),
                claudeEnabled=bool(os.environ.get("ANTHROPIC_API_KEY")))
    DOCS.mkdir(exist_ok=True)
    (DOCS / "data.json").write_text(json.dumps(data))
    tmpl = (ROOT / "pipeline" / "template.html").read_text()
    (DOCS / "index.html").write_text(tmpl.replace("__DATA__", json.dumps(data)))
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state, indent=1))
    HISTORY.write_text(json.dumps(history, indent=1))
    print(f"[build] wrote docs/index.html for {cur} week {week}")


if __name__ == "__main__":
    main()
