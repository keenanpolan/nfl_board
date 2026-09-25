"""Settings you may want to edit."""

# X (Twitter) accounts to follow. Verify each handle on x.com before relying on it.
X_HANDLES = [
    "AdamSchefter",   # ESPN
    "RapSheet",       # Ian Rapoport, NFL Network
    "TomPelissero",   # NFL Network
    "MikeGarafolo",   # NFL Network
    "JFowlerESPN",    # Jeremy Fowler, ESPN
]
X_MAX_POSTS_PER_RUN = 60      # hard cap per run to control cost ($0.005 per post read)

# ESPN contributor feeds (free, unofficial)
ESPN_CONTRIBUTORS = ["adam-schefter"]

# Claude model used to turn headlines into structured injury/QB data
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

NEWS_LOOKBACK_DAYS = 7        # how far back news stays attached to games
AUTO_QB_OVERRIDE = True       # let confirmed "X will start" news replace the listed starter

TEAMS = {
    "ARI": ["Arizona Cardinals", "Cardinals"], "ATL": ["Atlanta Falcons", "Falcons"], "BAL": ["Baltimore Ravens", "Ravens"],
    "BUF": ["Buffalo Bills", "Bills"], "CAR": ["Carolina Panthers", "Panthers"], "CHI": ["Chicago Bears", "Bears"],
    "CIN": ["Cincinnati Bengals", "Bengals"], "CLE": ["Cleveland Browns", "Browns"], "DAL": ["Dallas Cowboys", "Cowboys"],
    "DEN": ["Denver Broncos", "Broncos"], "DET": ["Detroit Lions", "Lions"], "GB": ["Green Bay Packers", "Packers"],
    "HOU": ["Houston Texans", "Texans"], "IND": ["Indianapolis Colts", "Colts"], "JAX": ["Jacksonville Jaguars", "Jaguars"],
    "KC": ["Kansas City Chiefs", "Chiefs"], "LA": ["Los Angeles Rams", "Rams"], "LAC": ["Los Angeles Chargers", "Chargers"],
    "LV": ["Las Vegas Raiders", "Raiders"], "MIA": ["Miami Dolphins", "Dolphins"], "MIN": ["Minnesota Vikings", "Vikings"],
    "NE": ["New England Patriots", "Patriots"], "NO": ["New Orleans Saints", "Saints"], "NYG": ["New York Giants", "Giants"],
    "NYJ": ["New York Jets", "Jets"], "PHI": ["Philadelphia Eagles", "Eagles"], "PIT": ["Pittsburgh Steelers", "Steelers"],
    "SEA": ["Seattle Seahawks", "Seahawks"], "SF": ["San Francisco 49ers", "49ers"], "TB": ["Tampa Bay Buccaneers", "Buccaneers"],
    "TEN": ["Tennessee Titans", "Titans"], "WAS": ["Washington Commanders", "Commanders"],
}
