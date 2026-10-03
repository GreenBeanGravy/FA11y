# Leave-match sidebar reference

Checked live in Fortnite Reload on September 21, 2026 at 1920x1080.

1. If the sidebar is closed, press Escape.
2. Wait until the Menu and Settings icons remain at the same positions in consecutive captures. The panel slides horizontally while opening.
3. Select the three-line Menu tab, observed near (1690, 71), unless Return to lobby is already visible.
4. Select the recognized Return to lobby label, observed near (1562, 172).
5. Stop clicking. The live test immediately left the match and reached the lobby without a confirmation dialog.

The Settings icon was near (1595, 71). The search regions cover the observed sidebar positions and its opening slide. Coordinates are matched from the current image; these reference centers are not blind click targets.

In the lobby, the same first row says Close Fortnite. It must never be accepted as Return to lobby.

The PNG templates hold only the menu icon, settings icon, and Return to lobby label. Recognition handles inverted selected colors. Tests use anonymous control crops from the September 21 UI in tests/fixtures/exit_match: Social and selected Menu headers, Return to lobby, and Close Fortnite. The crops are composited at their original positions; they are not full-screen captures.

The action uses fullscreen 16:9 coordinates normalized to 1920x1080. Other resolutions have synthetic scaling coverage only. English button text is required. Lost focus, missing controls, and an unsettled sidebar stop with spoken feedback.

Validation: the return sequence was run through computer use in a live Reload match, and arrival at the lobby was confirmed visually. Automated tests cover FA11y's recognition and input sequencing with mocked input: the observed control crops, sidebar animation, already-open menus, missing controls, inverted colors, scaling, and focus loss. The full FA11y hotkey has not been tried in a second live match.
