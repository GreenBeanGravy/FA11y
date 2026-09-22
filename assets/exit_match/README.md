# Leave-match sidebar reference

Rechecked live in Fortnite Reload on September 21, 2026 at 1920 x 1080.

1. If the sidebar is closed, press Escape.
2. Wait until the Menu and Settings icons remain at the same positions in consecutive captures. The panel slides horizontally while opening.
3. Select the three-line Menu tab, observed near (1690, 71), unless Return to lobby is already visible.
4. Select the recognized Return to lobby label, observed near (1562, 172).
5. Stop clicking. The live test immediately left the match and reached the lobby without a confirmation dialog.

The Settings icon was near (1595, 71), outside the old search region once its full template width is included. The search regions now cover the observed sidebar positions and its opening slide. Coordinates are matched from the current image; these reference centers are not blind click targets.

The historical (1834, 76), (1573, 255), (1579, 924) sequence is obsolete. In the lobby, the same first row says Close Fortnite. It must never be accepted as Return to lobby.

The PNG templates contain only the menu icon, settings icon, and Return to lobby label. Recognition supports inverted selected colors. Tests include anonymous control crops from the September 21 UI in tests/fixtures/exit_match: Social and selected Menu headers, Return to lobby, and Close Fortnite. Header and row crops are composited at their original positions for regression tests; they are not full-screen captures.

The action uses fullscreen 16:9 coordinates normalized to 1920 x 1080. Other resolutions have synthetic scaling coverage only. English button text is required. Lost focus, missing controls, and an unsettled sidebar stop with spoken feedback.

Validation: the current return sequence was exercised through computer use in a live Reload match and arrival at the lobby was visually confirmed. Automated tests exercise FA11y's recognition and input sequencing with mocked input, including the observed control crops, sidebar animation, already-open menus, missing controls, inverted colors, scaling, and focus loss. The complete FA11y hotkey has not been exercised in a second live match.
