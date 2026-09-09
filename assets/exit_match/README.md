# Leave-match sidebar reference

Mapped in a live Fortnite Battle Royale match on September 8, 2026 at 1920 x 1080.

1. If the sidebar is closed, press Escape and wait for its top-row icons.
2. Select the three-line Menu tab, centered near (1678, 71).
3. Select Return to lobby, centered near (1562, 172).
4. Stop clicking. This flow immediately left the match and returned to the lobby; no confirmation dialog appeared.

The former (1834, 76), (1573, 255), (1579, 924) sequence is obsolete.

The PNGs contain only the menu icon, settings icon, and Return to lobby label. They are used to recognize controls before clicking, including inverted hover/selected colors. Search areas are restricted to the observed sidebar positions. Other labels, including Exit Fortnite in the lobby, must not be accepted as Return to lobby.

The action uses fullscreen 16:9 screen coordinates, normalized to the 1920 x 1080 reference. Live validation was at 1920 x 1080; other resolutions have only synthetic coordinate-scaling coverage. English button text is required. Lost focus, missing controls, and unrecognized layouts stop with spoken feedback.

Validation: the observed Social and Menu screenshots match both sidebar icons; only Menu matches Return to lobby. The observed lobby screenshot matches none. Tests cover a closed/open sidebar, an already-selected Menu tab, missing controls, inverted colors, coordinate scaling, and lost focus. UI mapping was exercised live; the complete FA11y hotkey was tested with mocked input rather than a second live match.
