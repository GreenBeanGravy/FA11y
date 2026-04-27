"""Tail FortniteGame.log and announce in-game events via the screen reader."""

import os
import re
import threading
import time
import logging
from typing import Optional

from accessible_output2.outputs.auto import Auto

from lib.utilities.utilities import read_config, get_config_boolean, on_config_change

logger = logging.getLogger(__name__)


# Default location for Fortnite's log directory on Windows. Other platforms
# can't run Fortnite, so this is the only path we need to try.
_DEFAULT_LOG_DIR = os.path.join(
    os.environ.get('LOCALAPPDATA', ''),
    'FortniteGame', 'Saved', 'Logs'
)
_LOG_FILENAME = 'FortniteGame.log'


# --- Event patterns -----------------------------------------------------
#
# Each pattern targets exactly one log signature we verified against a real
# match log. Patterns are anchored loosely (no leading timestamp matching)
# so future log format tweaks don't silently break detection.

# Reload "instant reboot" widget (the on-screen prompt that says you can
# hold reload to instantly respawn while DBNO).
_RE_DBNO_KNOCKED = re.compile(
    r'BlastBerryInstantRebootWidget.*widget is now active.*Invincibility tag has been removed and player is DBNO'
)
_RE_RESPAWN_HELD = re.compile(
    r'BlastBerryInstantRebootWidget.*HandleInputPressed Action name is: Reload'
)
_RE_RESPAWN_RECOVERED = re.compile(
    r'BlastBerryInstantRebootWidget.*widget is now inactive.*Player is not DBNO anymore'
)
_RE_RESPAWN_DISABLED = re.compile(
    r'BlastBerryInstantRebootWidget.*widget is now inactive.*respawn has been disabled'
)

# EOS rich-presence text. The game updates this every time the player
# count changes, with the form "<Mode> - <N> Left".
_RE_PRESENCE = re.compile(
    r'LogEOSPresence: Updating Presence.*RichText=\[(?P<text>[^\]]*)\]'
)
_RE_PRESENCE_PLAYERS = re.compile(r'(?P<mode>.+?)\s*-\s*(?P<count>\d+)\s*Left', re.IGNORECASE)

# Battle royale game-phase logic. Two flavours: HandleGamePhaseChanged
# (top-level phase: Setup/Warmup/Aircraft/SafeZones) and UpdateGamePhaseStep
# (sub-step: BusLocked/BusFlying/StormForming/StormHolding/StormShrinking).
_RE_PHASE_CHANGED = re.compile(
    r'LogBattleRoyaleGamePhaseLogic: HandleGamePhaseChanged.*NewPhase = EAthenaGamePhase::(?P<phase>\w+)'
)
_RE_PHASE_STEP = re.compile(
    r'LogBattleRoyaleGamePhaseLogic: UpdateGamePhaseStep\..*PhaseStep = EAthenaGamePhaseStep::(?P<step>\w+)'
)

# You died (cursor opens the death/spectate menu).
_RE_DEATH = re.compile(r'LogFortHUDContext.*Entering cursor mode \(Show Death Spectator Menu\)')

# View-target changes. After death the player cycles through spectator
# subjects with the next-player button, which emits "from Pawn:<a> to
# Pawn:<b>" for each switch. The first change after death is from a
# FortSpectator pawn (the helper camera the game inserts), subsequent
# ones are player-to-player. We accept both and use a state flag to
# only announce while we're actually in spectator mode.
_RE_VIEW_TARGET = re.compile(
    r'LogFortViewTarget.*trying to set view target from\s+(?P<src>\S+)\s+to\s+Pawn:(?P<name>\S+(?:\[\d+\])?)'
)

# Match-end placement determined.
_RE_PLACEMENT = re.compile(r'LocalPlacementChanged We now have placement for the local player')

# Reload/box-fights final countdown player count warnings.
_RE_FINAL_COUNTDOWN = re.compile(
    r'FortAthenaMutator_FinalCountdown.*WarnCountdownStartingSoon.*PlayersRemaining:\s*(?P<count>\d+)'
)

# --- Party events ---
#
# These events are fired by Fortnite when party state changes. Parsing them
# from the log gives us sub-second latency and removes the need to poll the
# social API for invites or membership changes. They deliberately do NOT have
# their own config toggles — the API-polled versions they replace were also
# always-on.
#
# OnPartyInviteReceived: someone invited you to their party.
_RE_PARTY_INVITE_RECEIVED = re.compile(
    r'LogOnlineParty:\s*MCP:\s*OnPartyInviteReceived:.*?Sender=\[(?P<sender>[^\]]+)\]'
)
# OnPingReceived: someone pinged you asking to join your party.
_RE_PARTY_PING_RECEIVED = re.compile(
    r'LogOnlineParty:\s*MCP:\s*OnPingReceived:.*?Sender=\[(?P<sender>[^\]]+)\]'
)
# JoinParty (local request kicked off) — carries the other party's display
# name inline, which is a rare luxury in these logs.
_RE_PARTY_JOIN_ATTEMPT = re.compile(
    r'LogOnlineParty:\s*MCP:\s*JoinParty:.*?SourceDisplayName\((?P<name>[^)]+)\)'
)
# LogParty: Verbose: Adding [<name>] Id [MCP:<id>] ... — fires when a member
# (you or someone else) is inserted into the party's in-game team. The line
# contains the display name verbatim, so no partial-ID resolver is needed.
# Only emitted at Verbose log level, which is Fortnite's default for this
# category on all profiles we've checked.
_RE_PARTY_MEMBER_ADDED = re.compile(
    r'LogParty:\s*Verbose:\s*Adding\s*\[(?P<name>[^\]]+)\]\s*Id\s*\[MCP:(?P<id>[^\]]+)\]\s*as a new member'
)
# HandleZonePlayerStateRemoved: member left. No name in the line, so we rely
# on the _party_member_names cache populated by prior Added events.
_RE_PARTY_MEMBER_REMOVED = re.compile(
    r'LogParty:.*?HandleZonePlayerStateRemoved:\s*\[MCP:(?P<id>[^\]]+)\]'
)


# Phase-step strings worth announcing. Filtered to high-signal events;
# 'None' steps and intermediate transitions are noise.
_INTERESTING_STEPS = {
    'BusLocked': 'Battle bus locked',
    'BusFlying': 'Battle bus flying',
    'StormForming': 'Storm forming',
    'StormHolding': 'Storm holding',
    'StormShrinking': 'Storm shrinking',
    'GetReady': 'Get ready',
}


from lib.monitors.base import BaseMonitor


class MatchEventMonitor(BaseMonitor):
    """Tails the Fortnite log file in a background thread and speaks events."""

    _THREAD_NAME = "MatchEventMonitor"

    def __init__(self):
        super().__init__()
        self.speaker = Auto()

        # File-tracking state.
        self._log_path = os.path.join(_DEFAULT_LOG_DIR, _LOG_FILENAME)
        self._fp = None
        self._inode = None

        # Per-event de-duplication state. The log can repeat some lines
        # (e.g. multiple "trying to set view target" while loading) so we
        # remember the last value and only speak on real changes.
        self._last_player_count = None
        self._last_mode = None
        self._last_phase = None
        self._last_step = None
        self._last_spectate_target = None
        self._last_final_countdown = None

        # Spectator mode flag. Set on death, cleared on respawn or match
        # end. We need this because view-target changes happen during
        # normal play too (entering vehicles, getting downed, etc.) — only
        # changes that happen while we're spectating should be announced.
        self._spectating = False

        # Party-event state. _party_member_names maps MCP id -> display
        # name so we can announce "X left the party" when we only get an
        # id in the removal line. Populated by LogParty: Verbose: Adding
        # events. Cleared when the local user leaves the party.
        self._party_member_names: dict = {}

        # Resolver callback for "Sender=[<short>...<short>]" partial ids
        # in OnPartyInviteReceived / OnPingReceived. Set by FA11y at
        # startup once SocialManager is available. Signature:
        #   callable(partial_id: str) -> Optional[str]
        # Left as None means "announce with the partial id as-is".
        self.name_resolver = None

        # Local account id, set by FA11y at startup. Used to suppress
        # "joined the party" announcements for yourself when the Adding
        # event fires for the local user.
        self.local_account_id: Optional[str] = None

        # Config flags.
        self.config = read_config()
        self._reload_config_flags()
        on_config_change(self._on_config_change)

    # -- config -----------------------------------------------------------

    def _reload_config_flags(self):
        c = self.config
        self.enabled = get_config_boolean(c, 'MonitorMatchEvents', True)
        self.announce_dbno = get_config_boolean(c, 'AnnounceReloadKnocked', True)
        self.announce_respawn = get_config_boolean(c, 'AnnounceReloadRespawn', True)
        self.announce_players_left = get_config_boolean(c, 'AnnouncePlayersLeft', True)
        self.announce_phase = get_config_boolean(c, 'AnnounceMatchPhase', True)
        self.announce_death = get_config_boolean(c, 'AnnounceDeath', True)
        self.announce_spectate = get_config_boolean(c, 'AnnounceSpectating', True)
        self.announce_placement = get_config_boolean(c, 'AnnouncePlacement', True)
        self.announce_final_countdown = get_config_boolean(c, 'AnnounceFinalCountdown', True)

    def _on_config_change(self, config):
        self.config = config
        self._reload_config_flags()

    # -- file handling ----------------------------------------------------

    def _open_log(self) -> bool:
        """Open the log file and seek to the end. Returns True on success."""
        try:
            if not os.path.exists(self._log_path):
                return False
            # Use binary mode + manual decode so a partial UTF-8 sequence at
            # the tail (writer mid-write) doesn't raise.
            self._fp = open(self._log_path, 'rb')
            self._fp.seek(0, os.SEEK_END)
            self._inode = os.stat(self._log_path).st_ino
            end_pos = self._fp.tell()
            logger.info(
                f"MatchEventMonitor: tailing {self._log_path} "
                f"(starting at byte {end_pos}, inode {self._inode})"
            )
            return True
        except Exception as e:
            logger.info(f"MatchEventMonitor: could not open log: {e}")
            self._fp = None
            return False

    def _check_rotation(self):
        """If the file was rotated (Fortnite restarted), re-open it."""
        try:
            stat = os.stat(self._log_path)
        except OSError:
            # File temporarily missing during rotation; try again next tick.
            return
        if stat.st_ino != self._inode:
            logger.info(
                f"MatchEventMonitor: log rotation detected "
                f"(old inode {self._inode} -> new inode {stat.st_ino}), re-opening"
            )
            try:
                if self._fp:
                    self._fp.close()
            except Exception:
                pass
            # New log is a fresh game session - reset per-match dedupe state
            # so we don't suppress legitimate first-event announcements.
            self._last_player_count = None
            self._last_mode = None
            self._last_phase = None
            self._last_step = None
            self._last_spectate_target = None
            self._last_final_countdown = None
            self._spectating = False
            # Party cache is per-Fortnite-session: new game means Fortnite
            # will re-emit Adding events for any existing party members.
            self._party_member_names.clear()
            self._open_log()

    def _read_new_lines(self):
        """Yield any new full lines appended since the last read."""
        if self._fp is None:
            return
        try:
            chunk = self._fp.read()
        except Exception as e:
            logger.debug(f"MatchEventMonitor: read error: {e}")
            return
        if not chunk:
            return
        # Buffer-and-split so we never emit a partial line.
        buf = getattr(self, '_pending', b'') + chunk
        lines = buf.split(b'\n')
        self._pending = lines[-1]  # keep partial last line for next iteration
        for raw in lines[:-1]:
            try:
                yield raw.decode('utf-8', errors='replace')
            except Exception:
                continue

    # -- event handling ---------------------------------------------------

    def _speak(self, text: str):
        # Log every announcement at INFO so we can correlate "user heard
        # nothing" with "monitor thought it announced" in the FA11y log.
        logger.info(f"MatchEventMonitor: announcing {text!r}")
        try:
            self.speaker.speak(text)
        except Exception as e:
            # Screen reader may transiently fail (COM errors with SAPI);
            # don't let it kill the monitor thread.
            logger.info(f"MatchEventMonitor: speak failed: {e}")

    def _process_line(self, line: str):
        # --- Reload DBNO / respawn (user-requested core feature) ---
        if _RE_DBNO_KNOCKED.search(line):
            if self.announce_dbno:
                self._speak("Knocked. Hold reload to respawn.")
            return
        if _RE_RESPAWN_HELD.search(line):
            if self.announce_respawn:
                self._speak("Respawning")
            return
        if _RE_RESPAWN_RECOVERED.search(line):
            # Got back up - we're alive again, exit spectator mode if set.
            self._spectating = False
            self._last_spectate_target = None
            if self.announce_respawn:
                self._speak("Respawned")
            return
        if _RE_RESPAWN_DISABLED.search(line):
            if self.announce_respawn:
                self._speak("Respawn unavailable")
            return

        # --- Players left (rich presence) ---
        m = _RE_PRESENCE.search(line)
        if m:
            text = m.group('text').strip()
            pm = _RE_PRESENCE_PLAYERS.search(text)
            if pm:
                count = int(pm.group('count'))
                mode = pm.group('mode').strip()
                if self.announce_players_left and count != self._last_player_count:
                    # First appearance per-mode is the match-start lobby
                    # population; quieter wording for that case.
                    if self._last_player_count is None or self._last_mode != mode:
                        self._speak(f"{count} players in match")
                    else:
                        self._speak(f"{count} left")
                    self._last_player_count = count
                    self._last_mode = mode
            else:
                # Empty/lobby presence - reset so next match starts fresh.
                if self._last_player_count is not None:
                    self._last_player_count = None
                    self._last_mode = None
            return

        # --- Match phase ---
        m = _RE_PHASE_CHANGED.search(line)
        if m:
            phase = m.group('phase')
            if phase != self._last_phase:
                self._last_phase = phase
                # A new Warmup means a new match has started - exit any
                # leftover spectator state from the previous round.
                if phase in ('Setup', 'Warmup'):
                    self._spectating = False
                    self._last_spectate_target = None
                if self.announce_phase:
                    spoken = {
                        'Warmup': 'Warmup',
                        'Aircraft': 'On the battle bus',
                        'SafeZones': 'Match started',
                    }.get(phase)
                    if spoken:
                        self._speak(spoken)
            return

        m = _RE_PHASE_STEP.search(line)
        if m and self.announce_phase:
            step = m.group('step')
            if step != self._last_step and step in _INTERESTING_STEPS:
                self._last_step = step
                self._speak(_INTERESTING_STEPS[step])
            return

        # --- Death ---
        if _RE_DEATH.search(line):
            # Track spectator mode regardless of whether announce_death is
            # on, so spectate-target announcements still work when death
            # itself is muted.
            self._spectating = True
            self._last_spectate_target = None
            if self.announce_death:
                self._speak("You died")
            return

        # --- Spectating (only while in spectator mode after death) ---
        m = _RE_VIEW_TARGET.search(line)
        if m and self._spectating and self.announce_spectate:
            src = m.group('src')
            target = m.group('name')
            # Skip self-confirmations the game emits after every real
            # switch (e.g. "from Pawn:Foo to Pawn:Foo").
            if src == f'Pawn:{target}':
                return
            if target != self._last_spectate_target:
                self._last_spectate_target = target
                # "Anonymous[282]" -> "Anonymous player" for screen reader.
                if target.startswith('Anonymous'):
                    spoken_name = 'Anonymous player'
                else:
                    spoken_name = target
                self._speak(f"Spectating {spoken_name}")
            return

        # --- Final placement ---
        if _RE_PLACEMENT.search(line):
            # Match ended - exit spectator mode.
            self._spectating = False
            self._last_spectate_target = None
            if self.announce_placement:
                self._speak("Match ended")
            return

        # --- Final countdown player count ---
        m = _RE_FINAL_COUNTDOWN.search(line)
        if m and self.announce_final_countdown:
            count = int(m.group('count'))
            if count != self._last_final_countdown:
                self._last_final_countdown = count
                self._speak(f"Final countdown: {count} players left")
            return

        # --- Party invite received (someone invited you to their party) ---
        m = _RE_PARTY_INVITE_RECEIVED.search(line)
        if m:
            sender = m.group('sender')
            name = self._resolve_party_identity(sender)
            self._speak(f"Party invite from {name}")
            return

        # --- Ping received (someone requesting to join your party) ---
        m = _RE_PARTY_PING_RECEIVED.search(line)
        if m:
            sender = m.group('sender')
            name = self._resolve_party_identity(sender)
            self._speak(f"{name} is requesting to join your party")
            return

        # --- You joined someone's party ---
        m = _RE_PARTY_JOIN_ATTEMPT.search(line)
        if m:
            name = m.group('name').strip()
            if name:
                self._speak(f"Joined {name}'s party")
            return

        # --- Party member added (this includes yourself on party create) ---
        m = _RE_PARTY_MEMBER_ADDED.search(line)
        if m:
            name = m.group('name').strip()
            account_id = m.group('id').strip()
            # Cache the id -> name mapping so we can report who left later.
            if account_id and name:
                self._party_member_names[account_id] = name
            # Skip the self-add that fires on party creation / join. We
            # already announced "Joined X's party" in the JoinParty case
            # for joins, and a create doesn't need an announcement.
            if self.local_account_id and account_id == self.local_account_id:
                return
            if name:
                self._speak(f"{name} joined the party")
            return

        # --- Party member removed ---
        m = _RE_PARTY_MEMBER_REMOVED.search(line)
        if m:
            account_id = m.group('id').strip()
            # If it's us being removed, we left the party — drop the cache
            # and stay quiet (FA11y's existing self-state logic will
            # handle that path).
            if self.local_account_id and account_id == self.local_account_id:
                self._party_member_names.clear()
                return
            # Prefer the cached name from when they joined; fall back to
            # a partial id so there's still a useful announcement.
            name = self._party_member_names.pop(account_id, None)
            if not name:
                name = self._resolve_party_identity(account_id)
            self._speak(f"{name} left the party")
            return

    def _resolve_party_identity(self, partial_or_full_id: str) -> str:
        """Turn a party-log id (either a partial 'xxxxx...xxxxx' or a full
        MCP id) into a display name. Falls back to returning the raw id if
        no resolver is configured or no match is found — better a clumsy
        announcement than silent."""
        resolver = self.name_resolver
        if resolver:
            try:
                name = resolver(partial_or_full_id)
            except Exception as e:
                logger.info(f"MatchEventMonitor: name_resolver raised: {e}")
                name = None
            if name:
                return name
        return partial_or_full_id

    # -- main loop --------------------------------------------------------

    def _monitor_loop(self):
        logger.info(f"MatchEventMonitor: loop entered, waiting for log at {self._log_path}")
        # Wait for log file to appear (Fortnite may not be running yet).
        attempts = 0
        while self.running and not self._open_log():
            attempts += 1
            if attempts == 1 or attempts % 12 == 0:
                # First miss + every minute; avoid spamming the log.
                logger.info(
                    f"MatchEventMonitor: log not present yet, retrying "
                    f"(attempt {attempts}, path={self._log_path})"
                )
            if self.stop_event.wait(timeout=5.0):
                return
        logger.info("MatchEventMonitor: entering main read loop")

        last_rotation_check = time.monotonic()
        while self.running:
            if self.stop_event.wait(timeout=0.25):
                break
            if not self.enabled:
                continue
            if self.wizard_paused():
                continue
            try:
                # Cheap rotation check every ~2 seconds (stat is fast but
                # not free, and rotations only happen on game restart).
                now = time.monotonic()
                if now - last_rotation_check > 2.0:
                    self._check_rotation()
                    last_rotation_check = now
                if self._fp is None:
                    if not self._open_log():
                        continue
                for line in self._read_new_lines():
                    self._process_line(line)
            except Exception as e:
                logger.debug(f"MatchEventMonitor: loop error: {e}")
                # Brief backoff so a persistent error doesn't pin a CPU.
                if self.stop_event.wait(timeout=1.0):
                    break

        # Cleanup on exit.
        try:
            if self._fp:
                self._fp.close()
        except Exception:
            pass
        self._fp = None

    def start_monitoring(self):
        """Log startup state then call BaseMonitor to do the actual threading."""
        if self.running:
            logger.info("MatchEventMonitor: start_monitoring called but already running")
            return
        logger.info(
            f"MatchEventMonitor: starting thread "
            f"(enabled={self.enabled}, "
            f"announce_phase={self.announce_phase}, "
            f"announce_players_left={self.announce_players_left}, "
            f"announce_dbno={self.announce_dbno})"
        )
        super().start_monitoring()

    # stop_monitoring inherited from BaseMonitor


# Single shared instance, matching the pattern of other monitors.
match_event_monitor = MatchEventMonitor()
