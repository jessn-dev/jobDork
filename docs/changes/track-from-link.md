## Added — 2026-11-05 — Track an application you sent, from its link

My applications listed only job posts jobdork had found and you marked
applied. A job you applied to somewhere else, or before you used jobdork,
could be brought in only by adding it on the Sources page and then marking
it applied, dated the day you did that rather than the day you applied.

**Track an application you sent**, at the top of My applications, takes the
job post's link and the day you applied (today unless you change it; a day
still to come is refused). The post is read into Job posts as **Add a Job
Post** does, marked *applied*, dated that day in its stages, and listed. When
the page cannot be read, the form asks for the job title and employer
(and the place, and the advert if you have it): with the advert the post is
scored like any other; without it, it is tracked with nothing to score
against. A job already at *interviewing* or *offer* is left there, and a post
jobdork already had is not added twice.

`api.track_application` and `POST /api/application/track` do it;
`Store.set_status` takes the day a change was made (`when`) for its history.
The guide's My applications page explains it. Tests cover tracking from a
pasted advert (applied on its day, listed), from a title and employer alone
(each asked for), the day (real, `YYYY-MM-DD`, not in the future, nothing
stored when refused), a job further along left as it is, and a link read or
not readable (asking for more).
