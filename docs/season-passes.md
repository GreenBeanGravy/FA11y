# Locker passes

Open **Locker → Battle Passes**. The dialog has Battle Royale, OG, Festival / Music,
and LEGO tabs. Ctrl+Tab switches tabs. Arrow keys and the mouse browse rewards;
Page Up and Page Down switch to the previous/next game page, without wrapping.
The Page choice also allows direct page selection. Each pass remembers its page
while switching tabs. Tab to the details field to read the description, set,
cost, premium requirement, and reward prerequisites.

* **Claim reward** selects one unclaimed reward.
* **Claim full page** selects its unclaimed claimable-offer entries.
* **Claim full set** selects the current BR category's unclaimed offer entries.
  The other three current passes have pages rather than BR-style unlockable sets.
* **Unlock set** exchanges earned set-unlock tokens for the BR set's actual
  prerequisite offer. Claiming rewards is a separate action.
* **Unlock premium pass** uses that pass's exact current storefront offer and
  V-Bucks price. It is disabled when already owned. Real-money checkout, gift
  offers, and level bundles are not selected by this button.

An action displays its selected rewards and total cost before submission.
Full-page/full-set operations leave quest entries to their in-game quest system;
they do not complete quests. Full-page/full-set claims require enough points for
the selection and an unlocked set. Claim individual rewards when points are
insufficient for a whole page. Epic remains authoritative for level, ownership,
time, and reward-count prerequisites. Descriptions absent from the game data are
reported as unavailable rather than invented.

## Sources and current definitions

Definitions were extracted from the installed Release-42.20 game files with
cModdle on September 24, 2026. They contain 26 BR pages, 6 OG pages, 4 Music pages,
and 4 LEGO pages. There are 255 reward offers, 17 quest entries, and 12 separate
BR set-unlock offers. Game-authored category/page order and offer GUIDs are kept.
BR pages include bonus rewards. Variant rewards use their own item names and
their base cosmetic's description where available. Music titles and artists are
resolved through Epic's [Festival track metadata](https://fortnitecontent-website-prod07.ol.epicgames.com/content/api/pages/fortnite-game/spark-tracks).

Bonus pages are explicitly labeled **Bonus** in the page selector and details.
Select a quest-reward entry and choose **View reward quests** to open the existing
quest browser scoped to its exact quest and linked reward bundle. It shows both
active and completed quests initially, objective counters, and claimed status.
Pass-only hidden quests are admitted only in that explicitly linked context;
missing account records are not inferred to be completed. **View available
quests** opens the normal browser across all modes. Both views use the existing
account reader. This release does not include or require a packet decoder.

The general Left Alt+Q browser now respects the game's explicit bundle
`SuppressedQuestDefs`, matched to each quest's actual account bundle. The current
Birthday bundle suppresses “Emote in different matches” and “Land from the Bus
in different matches”; their account Active flag alone does not make them live
objectives. Completed records remain available in the Completed filter. Current
suppression data also covers known weekly, OG, Reload, and other bundles. It is
generated with `tools/build_quest_suppression.py` from cooked bundle exports, not
inferred from names or zero progress.

Account state comes from complete `QueryProfile` responses for `athena` and
`common_core`, and the live storefront. Claimed state uses the matching
`AthenaSeason` item's `purchased_offers`, not possession of a cosmetic that might
have several styles. An exact live season item and live purchase offer must match
the installed definitions before actions are enabled.

The documented operations are:

* [ExchangeGameCurrencyForSeasonPassOffer](https://github.com/LeleDerGrasshalmi/FortniteEndpointsDocumentation/blob/main/EpicGames/FN-Service/Game/Profile/Operations/ExchangeGameCurrencyForSeasonPassOffer.md):
  `athena`, an explicit `seasonPassTemplateId`, and an `offerItemIdList`. The same
  operation submits an individual reward, selected page/set rewards, or the
  category's game-defined token offer. Completion rewards follow prerequisites.
* [PurchaseCatalogEntry](https://github.com/LeleDerGrasshalmi/FortniteEndpointsDocumentation/blob/main/EpicGames/FN-Service/Game/Profile/Operations/PurchaseCatalogEntry.md):
  `common_core`, exact live offer, quantity 1, V-Bucks currency and expected price.
* [Epic's pass progression explanation](https://www.epicgames.com/help/c-34254770/c-33726977/a19736825).

The endpoint documentation is community research; the identifiers and account
schemas were cross-checked against current game assets and live read-only API
responses. No dedicated generic "claim cosmetic set" operation was found. The
set button batches the game-defined BR category's offers.

## Validation and maintenance

`tests/test_epic_passes.py` covers preflight checks, exact pass/offer binding,
ownership and currency checks, prerequisite ordering, price changes, expiry,
account switching, authentication, and post-mutation reconciliation.
`tests/test_passes_gui.py` uses real wx controls to check keyboard navigation,
tab-local pages, boundary behavior, and action availability without showing a
window or performing account changes.

Live profile/storefront reads and action previews succeeded for all four passes.
Actual claim, set unlock, and premium purchase execution have not been exercised
on the live account. No development test claims a reward or spends currency.

Mutations are never automatically retried. A follow-up query checks each selected
offer; errors, partial results, and uncertain results are reported explicitly.
If reconciliation cannot complete, the dialog requires a refresh. Concurrent
pass operations within FA11y are serialized and revalidated before submission.

To regenerate after a season change, export each current `SeasonPass` folder as
properties and the referenced reward/base-item definitions with cModdle, then run:

```text
python tools/build_pass_catalog.py EXPORTS CMODDLE_JSON_OUTPUT data/season_passes_4220.json --tracks EPIC_TRACKS_JSON
```

Review newly introduced requirement types, update the supported pass identities,
and rerun account read validation before enabling their operations. The builder
refuses unknown category requirement types. Keep account captures out of public
catalogs and documentation.

## Account quest updates

Open the quest browser with Left Alt+Q. Background account checks run every 15
seconds when QuestAnnouncements is enabled; initial state is silent. Failures
back off up to 300 seconds. The open browser also refreshes every 60 seconds and
provides a Refresh button. Epic controls when progress is saved; no guaranteed
account persistence interval has been established. Polling cannot force a save.
The file packet_quests_4210.json is static metadata, not a packet decoder.
