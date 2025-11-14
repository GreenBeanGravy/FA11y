"""
Epic Games XMPP Client
Handles XMPP connections for party functionality
"""
import asyncio
import logging
from typing import Optional
from slixmpp import ClientXMPP
from slixmpp.exceptions import IqError, IqTimeout

logger = logging.getLogger(__name__)


class EpicXMPP(ClientXMPP):
    """
    XMPP client for Epic Games services
    Handles MUC (Multi-User Chat) for party rooms
    """

    def __init__(self, jid: str, password: str, auth_instance):
        """
        Initialize XMPP client

        Args:
            jid: XMPP Jabber ID (account_id@prod.ol.epicgames.com)
            password: XMPP password (access token)
            auth_instance: EpicAuth instance for authentication
        """
        super().__init__(jid, password)

        self.auth = auth_instance
        self.connected = False
        self.current_party_muc = None

        # Epic's XMPP server configuration
        self.server_host = "prod.ol.epicgames.com"
        self.server_port = 5222

        # Register plugins
        self.register_plugin('xep_0045')  # MUC (Multi-User Chat)
        self.register_plugin('xep_0199')  # XMPP Ping

        # Register event handlers
        self.add_event_handler("session_start", self._handle_session_start)
        self.add_event_handler("session_end", self._handle_session_end)
        self.add_event_handler("groupchat_message", self._handle_muc_message)
        self.add_event_handler("muc::%s::got_online" % self.current_party_muc, self._handle_muc_presence)

        logger.info(f"Initialized XMPP client for {jid}")

    async def _handle_session_start(self, event):
        """Handle XMPP session start"""
        logger.info("XMPP session started")
        self.connected = True

        # Send presence
        self.send_presence()

        # Get roster
        try:
            await self.get_roster()
        except IqError as e:
            logger.error(f"Error getting roster: {e}")
        except IqTimeout:
            logger.error("Roster request timed out")

    async def _handle_session_end(self, event):
        """Handle XMPP session end"""
        logger.info("XMPP session ended")
        self.connected = False

    async def _handle_muc_message(self, msg):
        """Handle MUC (party chat) messages"""
        if msg['mucnick'] != self.boundjid.user:
            logger.debug(f"Party message from {msg['mucnick']}: {msg['body']}")

    async def _handle_muc_presence(self, presence):
        """Handle MUC presence updates"""
        logger.debug(f"Party presence update: {presence}")

    async def connect_and_start(self) -> bool:
        """
        Connect to Epic's XMPP server and start session

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Connecting to XMPP server {self.server_host}:{self.server_port}")

            # Connect to Epic's XMPP server
            if self.connect((self.server_host, self.server_port)):
                # Process XMPP stanzas
                self.process(forever=False)

                # Wait for connection
                await asyncio.sleep(2)

                if self.connected:
                    logger.info("Successfully connected to XMPP server")
                    return True
                else:
                    logger.error("Failed to establish XMPP session")
                    return False
            else:
                logger.error("Failed to connect to XMPP server")
                return False

        except Exception as e:
            logger.error(f"Error connecting to XMPP: {e}")
            return False

    async def join_party_muc(self, party_id: str, display_name: str = "Player") -> bool:
        """
        Join party MUC (Multi-User Chat) room

        Args:
            party_id: The party ID to join
            display_name: Display name to use in the MUC

        Returns:
            True if successful, False otherwise
        """
        try:
            # Construct MUC room JID: Party-{party_id}@muc.prod.ol.epicgames.com
            muc_jid = f"Party-{party_id}@muc.prod.ol.epicgames.com"
            self.current_party_muc = muc_jid

            logger.info(f"Joining party MUC: {muc_jid}")

            # Join the MUC room
            self.plugin['xep_0045'].join_muc(
                muc_jid,
                display_name,
                wait=True
            )

            logger.info(f"Successfully joined party MUC: {muc_jid}")
            return True

        except Exception as e:
            logger.error(f"Error joining party MUC: {e}")
            return False

    async def leave_party_muc(self) -> bool:
        """
        Leave current party MUC room

        Returns:
            True if successful, False otherwise
        """
        try:
            if not self.current_party_muc:
                logger.debug("No party MUC to leave")
                return True

            logger.info(f"Leaving party MUC: {self.current_party_muc}")

            # Leave the MUC room
            self.plugin['xep_0045'].leave_muc(
                self.current_party_muc,
                self.boundjid.user
            )

            self.current_party_muc = None
            logger.info("Successfully left party MUC")
            return True

        except Exception as e:
            logger.error(f"Error leaving party MUC: {e}")
            return False

    async def disconnect_xmpp(self):
        """Disconnect from XMPP server"""
        try:
            if self.current_party_muc:
                await self.leave_party_muc()

            self.disconnect(wait=True)
            logger.info("Disconnected from XMPP server")
        except Exception as e:
            logger.error(f"Error disconnecting from XMPP: {e}")
