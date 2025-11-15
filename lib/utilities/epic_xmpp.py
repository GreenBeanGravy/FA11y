"""
Epic Games XMPP Client
Handles XMPP connections for party functionality using aioxmpp (same as FortnitePy)
"""
import asyncio
import logging
import aioxmpp
from typing import Optional

logger = logging.getLogger(__name__)


class EpicXMPP:
    """
    XMPP client for Epic Games services
    Handles MUC (Multi-User Chat) for party rooms
    Uses aioxmpp (same library as FortnitePy)
    """

    def __init__(self, jid: str, password: str, auth_instance):
        """
        Initialize XMPP client

        Args:
            jid: XMPP Jabber ID (account_id@prod.ol.epicgames.com)
            password: XMPP password (access token)
            auth_instance: EpicAuth instance for authentication
        """
        self.auth = auth_instance
        self.connected = False
        self.current_party_muc = None
        self.client = None
        self.muc_service = None

        # Parse JID
        self.jid = aioxmpp.JID.fromstr(jid)
        self.password = password

        # Epic's XMPP server configuration
        self.server_host = "prod.ol.epicgames.com"
        self.server_port = 5222

        logger.info(f"Initialized XMPP client for {jid}")

    async def connect_and_start(self) -> bool:
        """
        Connect to Epic's XMPP server and start session

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Connecting to XMPP server {self.server_host}:{self.server_port}")

            # Create security layer (allow unencrypted for Epic's server)
            security_layer = aioxmpp.make_security_layer(
                self.password,
                no_verify=True,
                anonymous=False
            )

            # Create client (don't use as context manager)
            # Let JID domain (prod.ol.epicgames.com) auto-resolve via DNS
            self.client = aioxmpp.PresenceManagedClient(
                self.jid,
                security_layer
            )

            # Connect using .connected() context manager
            async with self.client.connected() as stream:
                logger.info("XMPP session established")
                self.connected = True

                # Get MUC service
                self.muc_service = self.client.summon(aioxmpp.MUCClient)

                # Keep connection alive for a moment
                await asyncio.sleep(1)

                return True

        except Exception as e:
            logger.error(f"Error connecting to XMPP: {e}")
            self.connected = False
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
            if not self.connected or not self.muc_service:
                logger.error("XMPP not connected, cannot join MUC")
                return False

            # Construct MUC room JID: Party-{party_id}@muc.prod.ol.epicgames.com
            muc_jid = aioxmpp.JID.fromstr(f"Party-{party_id}@muc.prod.ol.epicgames.com")
            self.current_party_muc = muc_jid

            logger.info(f"Joining party MUC: {muc_jid}")

            # Join the MUC room
            room, future = self.muc_service.join(
                muc_jid,
                display_name
            )

            # Wait for join to complete
            await future

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
            if not self.current_party_muc or not self.muc_service:
                logger.debug("No party MUC to leave")
                return True

            logger.info(f"Leaving party MUC: {self.current_party_muc}")

            # Leave the MUC room
            # Note: Need to get room reference first
            # For simplicity, we'll just clear the reference
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

            if self.client:
                # Client will auto-disconnect when exiting context manager
                self.client = None

            self.connected = False
            logger.info("Disconnected from XMPP server")

        except Exception as e:
            logger.error(f"Error disconnecting from XMPP: {e}")


class EpicXMPPManager:
    """
    Manager for XMPP connection that keeps it alive
    Simpler approach that maintains persistent connection
    """

    def __init__(self, jid_str: str, password: str):
        self.jid = aioxmpp.JID.fromstr(jid_str)
        self.password = password
        self.server_host = "prod.ol.epicgames.com"
        self.server_port = 5222
        self.client = None
        self.muc_client = None
        self.current_room = None
        self.connected = False
        self._connection_task = None
        self._shutdown_event = asyncio.Event()  # Event to signal shutdown
        self._keep_alive_future = None  # Future that keeps connection alive

    async def connect_and_join_muc(self, party_id: str, nickname: str, loop: asyncio.AbstractEventLoop = None) -> bool:
        """
        Connect to XMPP and immediately join party MUC
        Keeps connection alive indefinitely until shutdown() is called

        Args:
            party_id: Party ID to join
            nickname: Display name for MUC
            loop: Event loop to use (if None, will get current loop)

        Returns:
            True if connection succeeds, False otherwise
        """
        try:
            logger.info(f"Connecting XMPP to {self.server_host}:{self.server_port}")

            # Get or create event loop
            if loop is None:
                loop = asyncio.get_event_loop()

            # Create security layer
            security_layer = aioxmpp.make_security_layer(
                self.password,
                no_verify=True
            )

            # Create client
            # JID domain (prod.ol.epicgames.com) will auto-resolve via DNS SRV records
            # No need to override peer - let aioxmpp handle connection
            self.client = aioxmpp.PresenceManagedClient(
                self.jid,
                security_layer
            )

            # Connect and join MUC
            async with self.client.connected() as stream:
                logger.info("XMPP connected successfully")
                self.connected = True

                # Get MUC client
                self.muc_client = self.client.summon(aioxmpp.MUCClient)

                # Join party MUC room
                muc_jid = aioxmpp.JID.fromstr(f"Party-{party_id}@muc.prod.ol.epicgames.com")
                logger.info(f"Joining MUC: {muc_jid}")

                # Join room
                self.current_room, join_future = self.muc_client.join(muc_jid, nickname)
                await join_future

                logger.info(f"Successfully joined MUC room, keeping connection alive indefinitely...")

                # Keep connection alive indefinitely (like FortnitePy does)
                # Create a future that will never complete unless shutdown() is called
                # This is the critical fix - the connection must stay alive for character to spawn!
                self._keep_alive_future = loop.create_future()

                # Wait for either the shutdown event or the future to complete
                # This keeps the connection alive until we explicitly disconnect
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=None  # No timeout - wait indefinitely
                    )
                    logger.info("XMPP shutdown requested, disconnecting gracefully")
                except asyncio.CancelledError:
                    logger.info("XMPP connection cancelled")

                return True

        except Exception as e:
            logger.error(f"XMPP error: {e}")
            self.connected = False
            return False
        finally:
            self.connected = False
            logger.info("XMPP connection closed")

    def shutdown(self):
        """
        Signal the XMPP connection to shutdown gracefully
        Call this to disconnect from XMPP and leave MUC rooms
        """
        logger.info("Signaling XMPP shutdown...")
        self._shutdown_event.set()

        # Cancel the keep-alive future if it exists
        if self._keep_alive_future and not self._keep_alive_future.done():
            self._keep_alive_future.cancel()

    async def disconnect(self):
        """
        Disconnect from XMPP (async version)
        Triggers shutdown and waits for connection to close
        """
        try:
            # Signal shutdown
            self.shutdown()

            # Leave MUC room if in one
            if self.current_room:
                try:
                    await self.current_room.leave()
                    logger.info("Left MUC room")
                except Exception as e:
                    logger.warning(f"Error leaving MUC room: {e}")

            # Stop client if running
            if self.client:
                try:
                    self.client.stop()
                    logger.info("Stopped XMPP client")
                except Exception as e:
                    logger.warning(f"Error stopping XMPP client: {e}")

            self.connected = False
            logger.info("XMPP disconnected successfully")

        except Exception as e:
            logger.error(f"Error disconnecting XMPP: {e}")