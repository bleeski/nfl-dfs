"""Venue roof facts, and the one inference the schedule artifact cannot make.

Why this module exists. nflverse's `games.csv` `roof` column is retrospective:
it records what the roof actually did, so a completed game at a retractable
venue carries `closed` (or `open`) and an unplayed one carries an empty cell.
Both `priors.resolve_weather_state` and `prior_review.decide_weather` read a
blank cell as "the schedule cannot resolve this roof" and demand an
`api.weather.gov` capture. For a retractable-roof venue that is a capture
demanded for a game played under a roof.

Measured against the frozen artifact of run `20260920T195344Z-week2-aft2`: the
2026 rows carried 177 `outdoors`, 52 `dome`, 2 `closed` and **41 blank**, while
the 2025 rows carried no blank at all. Every blank sat at one of five venues.
Two of that afternoon's five games (SEA@ARI, WAS@DAL) were sent to the weather
gate because of it, on a slate that had fourteen minutes left on its lock clock.

The counting window is not optional, and finding out why is the reason this
module counts at runtime instead of hardcoding a verdict. Over the whole
artifact ARI reads 144 `closed`, 21 `open` and 58 `outdoors`, so a venue that
plays every game under a roof today did not always. Scoped to the prior and
current seasons, the same artifact reads unanimous `closed` at all five venues
(8 to 10 completed games each); widened to four seasons, every one of them shows
an `open` row. **These roofs do open sometimes.** The window is therefore the
same prior-plus-current pair the rest of the prior package already treats as
relevant, and the basis string carries it so a reader knows what was counted.

What this module will not do is assert a roof state from the venue name alone.
Four bounds hold it to a prior rather than an observation:

* the resolution is counted out of the same frozen schedule artifact the run has
  already bound and hashed, never out of a constant in this file;
* it is counted over a declared season window and returned under a basis string
  naming both the counts and the window, so a replay can recount it;
* one recorded `open` game in the window stops the venue resolving anything, and
  a venue with too few completed games in it never resolves either;
* a real operator observation always outranks it.

The set below is a stadium fact (which venues have a roof that moves), not a
weather claim. It changes when a stadium is built or rebuilt, not weekly.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping

# Home teams whose venue has a retractable roof, so nflverse records the roof
# state only after the game is played. State Farm Stadium (ARI),
# Mercedes-Benz Stadium (ATL), AT&T Stadium (DAL), NRG Stadium (HOU) and
# Lucas Oil Stadium (IND).
RETRACTABLE_ROOF_HOME_TEAMS = frozenset({"ARI", "ATL", "DAL", "HOU", "IND"})

# How many completed home games a venue needs before its history is allowed to
# resolve anything. Eight is half a home season: enough that one unusual
# afternoon cannot carry the count, and low enough that a venue in its first
# season still qualifies partway through the following one.
MIN_COMPLETED_HOME_GAMES = 8

# The roof value a unanimous retractable history resolves to. `priors` maps this
# to the `ROOF_CLOSED` weather enum exactly as it maps a schedule-recorded
# `closed`, because it is the same claim about the same roof.
RESOLVED_ROOF_VALUE = "closed"

VENUE_ROOF_BASIS = "DERIVED_FROM_VENUE_ROOF_HISTORY"


def home_team_of(game_id: str) -> str:
    """The home team in an `AWAY@HOME` matchup id, or the empty string.

    The slate's own `game_id` is the matchup alone, which is the only place the
    weather stage has the home team without new plumbing. Anything that is not
    exactly one `@` resolves to nothing rather than guessing a side.
    """

    parts = (game_id or "").strip().upper().split("@")
    if len(parts) != 2:
        return ""
    return parts[1].strip()


def roof_history(
    schedule_rows: Iterable[Mapping[str, str]],
    *,
    seasons: Iterable[int | str] | None = None,
) -> dict[str, dict[str, int]]:
    """Count each home team's completed games by the roof state recorded for them.

    Completed means the artifact carries a home score. An unplayed row is
    exactly the row whose roof this function exists to resolve, so counting it
    would let a blank vouch for itself.

    `seasons` is the window. Passing None counts the whole artifact, which is
    the wrong answer for every caller in this repository and is kept only so a
    diagnostic can look at the full record: a venue's roof practice changes over
    a decade, and the module docstring has the counts that show it.
    """

    window = {str(season).strip() for season in seasons} if seasons is not None else None
    counts: dict[str, Counter[str]] = {}
    for row in schedule_rows:
        if not (row.get("home_score") or "").strip():
            continue
        if window is not None and (row.get("season") or "").strip() not in window:
            continue
        team = (row.get("home_team") or "").strip().upper()
        if not team:
            continue
        roof = (row.get("roof") or "").strip().lower()
        if not roof:
            continue
        counts.setdefault(team, Counter())[roof] += 1
    return {team: dict(sorted(tally.items())) for team, tally in sorted(counts.items())}


def season_window(season: int, prior_season: int) -> tuple[int, ...]:
    """The seasons a venue's roof practice is counted over.

    The prior and current seasons, which is the pair the rest of the prior
    package already treats as relevant. Widening it past that reaches back into
    seasons where these venues did open the roof.
    """

    return tuple(sorted({int(prior_season), int(season)}))


def resolve_blank_roof(
    home_team: str,
    history: Mapping[str, Mapping[str, int]] | None,
    *,
    seasons: Iterable[int | str] | None = None,
) -> tuple[str, str] | None:
    """Resolve a blank roof from a retractable venue's own recorded history.

    Returns the roof value and the basis naming the counts behind it, or None
    when this venue is not one the history may speak for. None is the answer for
    a venue with no retractable roof, a venue with too few completed games, and
    a venue that has ever been recorded playing with the roof open: each of
    those is a game whose roof a human still has to observe.
    """

    team = (home_team or "").strip().upper()
    if team not in RETRACTABLE_ROOF_HOME_TEAMS or not history:
        return None
    tally = dict(history.get(team) or {})
    total = sum(tally.values())
    closed = int(tally.get(RESOLVED_ROOF_VALUE, 0))
    if total < MIN_COMPLETED_HOME_GAMES or closed != total:
        return None
    window = (
        ",".join(str(season).strip() for season in seasons)
        if seasons is not None
        else "UNSCOPED"
    )
    return (
        RESOLVED_ROOF_VALUE,
        f"{VENUE_ROOF_BASIS}:retractable"
        f":{RESOLVED_ROOF_VALUE}={closed}/{total}:seasons={window}",
    )
