"""Ratings engine: Elo, Elo + QB, and Blend + EPA, plus trust, key numbers and injury flags.
Same logic as the v3 notebook, packaged as functions."""
import numpy as np, pandas as pd, nflreadpy as nfl
from scipy.stats import norm

K, HFA, REVERT, REST_BONUS = 20, 48, 1/3, 25
QB_MULT, QB_ALPHA, TEAM_ALPHA, NEW_QB = 3.3, 0.10, 0.10, 35
EPA_ALPHA, EPA_REVERT, TRAIN_END = 0.10, 0.5, 2019
MODELS = ['elo', 'eloqb', 'blend']


def load():
    sched = nfl.load_schedules().to_pandas()
    sched = sched[sched.season >= 2005].sort_values(['season', 'week', 'gameday', 'gametime']).reset_index(drop=True)
    cur = int(sched.season.max())
    seasons = list(range(2005, cur + 1))
    ps = nfl.load_player_stats(seasons).to_pandas()
    f = lambda c: ps[c].fillna(0)
    ps['qb_val'] = (-2.2*f('attempts') + 3.7*f('completions') + f('passing_yards')/5 + 11.3*f('passing_tds')
                    - 14.1*f('passing_interceptions') - 8*f('sacks_suffered') - 1.1*f('carries')
                    + 0.6*f('rushing_yards') + 15.9*f('rushing_tds'))
    qbv = ps.set_index(['game_id', 'player_id']).qb_val
    qbv = qbv[~qbv.index.duplicated()].to_dict()
    qbs = ps[ps.position == 'QB'][['player_id', 'player_display_name', 'team', 'season']].drop_duplicates()
    ts = nfl.load_team_stats(seasons).to_pandas()
    g = lambda c: ts[c].fillna(0)
    ts['plays'] = g('attempts') + g('carries') + g('sacks_suffered')
    ts['epa'] = g('passing_epa') + g('rushing_epa')
    ts = ts[ts.plays > 0]
    epa_pp = {(r.game_id, r.team): r.epa / r.plays for r in ts.itertuples()}
    return sched, cur, qbv, qbs, epa_pp


def run(games, qbv, epa_pp):
    R, Q, TQ, OFF, DEF, season = {}, {}, {}, {}, {}, None
    rows = []
    for g in games.itertuples():
        if g.season != season:
            R = {t: 1500 + (r - 1500) * (1 - REVERT) for t, r in R.items()}
            OFF = {t: v * (1 - EPA_REVERT) for t, v in OFF.items()}
            DEF = {t: v * (1 - EPA_REVERT) for t, v in DEF.items()}
            season = g.season
        h, a = R.get(g.home_team, 1500), R.get(g.away_team, 1500)
        adj = 0 if g.location == 'Neutral' else HFA
        if pd.notna(g.home_rest) and pd.notna(g.away_rest):
            if g.home_rest >= 10 and g.away_rest < 10: adj += REST_BONUS
            if g.away_rest >= 10 and g.home_rest < 10: adj -= REST_BONUS
        qa = {}
        for side, team, qb in (('h', g.home_team, g.home_qb_id), ('a', g.away_team, g.away_qb_id)):
            qr = Q.get(qb, NEW_QB) if pd.notna(qb) else None
            tq = TQ.get(team)
            qa[side] = QB_MULT * (qr - tq) if (qr is not None and tq is not None) else 0.0
        base = h + adj - a
        diff = base + qa['h'] - qa['a']
        net = lambda t: OFF.get(t, 0) - DEF.get(t, 0)
        rows.append((base / 25, diff / 25, qa['h'] / 25, qa['a'] / 25, net(g.home_team) - net(g.away_team)))
        if pd.notna(g.result):
            exp = 1 / (1 + 10 ** (-diff / 400))
            act = 1.0 if g.result > 0 else 0.0 if g.result < 0 else 0.5
            wd = diff if g.result > 0 else -diff
            shift = K * np.log(abs(g.result) + 1) * 2.2 / (wd * 0.001 + 2.2) * (act - exp)
            R[g.home_team], R[g.away_team] = h + shift, a - shift
            for team, qb in ((g.home_team, g.home_qb_id), (g.away_team, g.away_qb_id)):
                v = qbv.get((g.game_id, qb))
                if v is None: continue
                Q[qb] = Q.get(qb, NEW_QB) * (1 - QB_ALPHA) + v * QB_ALPHA
                TQ[team] = TQ.get(team, v) * (1 - TEAM_ALPHA) + v * TEAM_ALPHA
            for team, opp in ((g.home_team, g.away_team), (g.away_team, g.home_team)):
                off, dfn = epa_pp.get((g.game_id, team)), epa_pp.get((g.game_id, opp))
                if off is None or dfn is None: continue
                OFF[team] = OFF.get(team, 0) * (1 - EPA_ALPHA) + off * EPA_ALPHA
                DEF[team] = DEF.get(team, 0) * (1 - EPA_ALPHA) + dfn * EPA_ALPHA
    out = pd.DataFrame(rows, index=games.index, columns=['elo', 'eloqb', 'hqa', 'aqa', 'epa_diff'])
    return out, dict(R=R, Q=Q, TQ=TQ, OFF=OFF, DEF=DEF)


def fit_and_score(sched, qbv, epa_pp):
    out, state = run(sched, qbv, epa_pp)
    d = sched.join(out)
    train = d[d.result.notna() & d.season.between(2010, TRAIN_END)]
    X = lambda D: np.column_stack([np.ones(len(D)), D.eloqb, D.epa_diff])
    coef = np.linalg.lstsq(X(train), train.result, rcond=None)[0]
    d['blend'] = X(d) @ coef
    h = d[d.result.notna() & (d.season >= 2010) & d.spread_line.notna()]
    recent = h[h.season >= 2020]
    trust = {m: round(float(((h[m] - h.spread_line) @ (h.result - h.spread_line)) /
                            ((h[m] - h.spread_line) @ (h[m] - h.spread_line))), 2) for m in MODELS}
    mae_test = {m: round(float((recent.result - recent[m]).abs().mean()), 2) for m in MODELS + ['spread_line']}
    return d, h, state, coef, trust, mae_test


def ats(D, m, th):
    e, c = D[m] - D.spread_line, D.result - D.spread_line
    k = (e.abs() >= th) & (c != 0)
    won = np.sign(e[k]) == np.sign(c[k])
    return won, D.season[k]


def key_weights(d):
    hist = d[d.result.notna() & d.spread_line.notna() & (d.season >= 2010)]
    ks = np.arange(-60, 61)
    expected = sum(norm.cdf(ks + .5, m, 13.5) - norm.cdf(ks - .5, m, 13.5) for m in hist.spread_line.values)
    observed = pd.Series(hist.result.astype(int)).value_counts().reindex(ks, fill_value=0).values
    w = []
    for a in range(61):
        mask = np.isin(ks, [a, -a]); e = expected[mask].sum()
        w.append(round(float(observed[mask].sum() / e), 3) if (e > 0 and a <= 40) else 1.0)
    return w


def injury_flags(cur, week):
    inj_out = {}
    try:
        inj = nfl.load_injuries([cur]).to_pandas()
        inj = inj[(inj.week == week) & inj.report_status.isin(['Out', 'Doubtful'])]
        sc = nfl.load_snap_counts([cur]).to_pandas()
        sc = sc[sc.week < week]
        sc['share'] = sc[['offense_pct', 'defense_pct']].max(axis=1)
        clean = lambda n: n.lower().replace('.', '').replace(' jr', '').replace(' iii', '').replace(' ii', '').strip()
        share = {(t, clean(p)): v for (t, p), v in sc.groupby(['team', 'player']).share.mean().items()}
        inj['share'] = [share.get((t, clean(n))) for t, n in zip(inj.team, inj.full_name)]
        for r in inj[inj.share >= 0.5].sort_values('share', ascending=False).itertuples():
            inj_out.setdefault(r.team, []).append(dict(name=r.full_name, pos=r.position, status=r.report_status,
                                                      snaps=round(float(r.share) * 100)))
    except Exception as ex:
        print("[model] injury data unavailable:", ex)
    return inj_out
