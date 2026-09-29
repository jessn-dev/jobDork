"""
jobdork.db.grouping
===================
Copies of one job, posted in several places, kept together.

Aggregators republish one vacancy under several URLs, and an employer's own
board carries the same job an aggregator does. Each URL is its own row —
deleting all but one would throw away the working link when another copy's
link dies — so copies are *grouped* instead:

  **Same job** means same employer, same title and same place. Place is the
  resolved city and state, or "remote", or the location text as written when
  it could not be resolved. Without the place, a company hiring "Software
  Engineer" in Chicago and in Austin would collapse into one post and one of
  them would vanish.

  **One post on screen.** The list shows one copy per group: one that is not
  known to be closed, then the fullest advert, then the best score.

  **One decision.** A status or note set on any copy is set on the group, so
  a copy that later becomes the one shown does not reappear as new.

  **Closed only when every copy is.** One live copy keeps the job open.

The key is SQL so the database can group without a stored column that every
write would have to keep current.
"""

from __future__ import annotations

from collections.abc import Iterable


def key_sql(alias: str = "") -> str:
    """The group key as an SQL expression over a `roles` row."""
    a = f"{alias}." if alias else ""
    return (
        f"lower(trim(COALESCE({a}company, ''))) || '|' || "
        f"lower(trim(COALESCE({a}title, ''))) || '|' || "
        f"CASE WHEN {a}work_mode = 'remote' THEN 'remote' "
        f"WHEN COALESCE({a}city, '') <> '' "
        f"THEN lower({a}city) || ',' || lower(COALESCE({a}state, '')) "
        f"ELSE lower(trim(COALESCE({a}location_raw, ''))) END"
    )


def representative_order() -> str:
    """Which copy of a group is shown: not closed, fullest advert, best score.

    Advert length is bucketed by the thousand: 4,700 and 4,900 characters are
    the same advert, and the score should decide between them. Fuller before
    score, because a 500-character teaser cannot lose points on content it
    does not contain and so tends to out-score the real advert.
    """
    return ("CASE WHEN listing_state = 'closed' THEN 1 ELSE 0 END, "
            "LENGTH(COALESCE(description, '')) / 1000 DESC, "
            "score DESC, first_seen ASC, uid ASC")


def uids(conn, uid: str) -> list[str]:
    """Every copy in `uid`'s group, `uid` first. Just `uid` if it has none."""
    rows = conn.execute(
        # Safe: key_sql() is a fixed SQL fragment; uid is a ? parameter.
        f"SELECT uid FROM roles WHERE {key_sql()} = "  # nosec B608
        f"(SELECT {key_sql()} FROM roles WHERE uid = ?) ORDER BY uid = ? DESC",
        (uid, uid)).fetchall()
    return [r[0] for r in rows] or [uid]


def all_closed(conn, members: Iterable[str]) -> bool:
    """True when every copy has been found closed."""
    members = list(members)
    marks = ",".join("?" for _ in members)
    open_left = conn.execute(
        # Safe: only ? placeholders are interpolated.
        f"SELECT COUNT(*) FROM roles WHERE uid IN ({marks}) "  # nosec B608
        "AND COALESCE(listing_state, '') <> 'closed'", members).fetchone()[0]
    return open_left == 0
