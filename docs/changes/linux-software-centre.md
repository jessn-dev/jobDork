## Fixed — 2026-11-11 — The Linux packages show jobdork's icon and screenshots in a software centre

Opened from the file, the `.deb` showed in GNOME Software with a generic
gear for its icon and "No Screenshots": the packages carried a menu entry
and one 256-pixel icon, but no AppStream metainfo, which is what software
centres (GNOME Software, KDE Discover) read for an app's icon, pictures and
details.

Both the `.deb` and the AppImage now carry
`/usr/share/metainfo/io.github.jessn_dev.jobdork.metainfo.xml`: name,
summary, description, licence, links, the release, the icon (installed, and
as a web address), and four screenshots with captions (the Dashboard, Job
posts, a job post, the Resume page), taken from the guide's pictures at the
release's own tag so they match the version installed. The icon is
installed at 64, 128, 256 and 512 pixels and as an SVG (`packaging/build.py`,
`metainfo`). desktop.yml's install check looks for the metainfo and the
large icon on Ubuntu 22.04, 24.04 and Debian 12; tests/test_build.py checks
the metainfo's shape and that each screenshot is a guide picture.

Not yet checked in GNOME Software itself: the screenshots' addresses exist
once the release is tagged.
