import logging
import sqlite3
import asqlite
import twitchio
import os

from dotenv import load_dotenv
from twitchio.ext import commands
from twitchio import eventsub, web
from common import event_bus


load_dotenv()

CLIENT_ID: str = os.environ["TWITCH_CLIENT_ID"]
CLIENT_SECRET: str = os.environ["TWITCH_CLIENT_SECRET"]
BOT_ID = os.environ["TWITCH_BOT_ID"]
OWNER_ID = os.environ["TWITCH_OWNER_ID"]
BOT_USERNAME = os.environ["TWITCH_BOT_USERNAME"]
OWNER_USERNAME = os.environ["TWITCH_OWNER_USERNAME"]
LOGGER: logging.Logger = logging.getLogger("Bot")

adapter = web.StarletteAdapter(domain=os.environ["DOMAIN"])


class Bot(commands.Bot):
    def __init__(self, *, token_database: asqlite.Pool) -> None:
        super().__init__(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            bot_id=BOT_ID,
            owner_id=OWNER_ID,
            adapter=adapter,
            prefix="d!",
        )
        self.token_database = token_database

    async def setup_hook(self) -> None:
        # Add components
        await self.add_component(BitListener(self))

        # For testing locally, connected to Twitch CLI tool
        # twitchio.http.Route.BASE = "http://localhost:8080/"
        # websockets.WSS = "ws://localhost:8080/ws"

        # Add WebSocket event subscriptions
        subscription_chat = eventsub.ChatMessageSubscription(
            broadcaster_user_id=OWNER_ID, user_id=BOT_ID
        )
        await self.subscribe_websocket(payload=subscription_chat)

        subscription_cheer = eventsub.ChannelCheerSubscription(
            broadcaster_user_id=OWNER_ID
        )
        await self.subscribe_websocket(payload=subscription_cheer)

        # todo: Send Discord webhook when live
        subscription_online = eventsub.StreamOnlineSubscription(
            broadcaster_user_id=OWNER_ID
        )
        await self.subscribe_websocket(payload=subscription_online)

    async def add_token(
        self, token: str, refresh: str
    ) -> twitchio.authentication.ValidateTokenPayload:
        response: twitchio.authentication.ValidateTokenPayload = (
            await super().add_token(token, refresh)
        )

        # Store tokens in basic SQLite database
        # TODO: This is dumb and I want to replace this with something simpler
        query = """
            INSERT INTO tokens (user_id, token, refresh)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id)
            DO UPDATE SET
            token = excluded.token,
            refresh = excluded.refresh;
        """

        async with self.token_database.acquire() as connection:
            await connection.execute(query, (response.user_id, token, refresh))

        LOGGER.info("Added token to the database for user: %s", response.user_id)
        return response

    async def load_tokens(self, path: str | None = None) -> None:
        # Called internally from .login(), which is in .start()

        async with self.token_database.acquire() as connection:
            rows: list[sqlite3.Row] = await connection.fetchall(
                """SELECT * from tokens"""
            )

        for row in rows:
            await self.add_token(row["token"], row["refresh"])

    async def setup_database(self) -> None:
        # Create token table if it doesn't exist
        query = """CREATE TABLE IF NOT EXISTS tokens(user_id TEXT PRIMARY KEY, token TEXT NOT NULL, refresh TEXT NOT NULL)"""
        async with self.token_database.acquire() as connection:
            await connection.execute(query)

    async def event_ready(self) -> None:
        LOGGER.info("Successfully logged in as: %s", self.bot_id)


class BitListener(commands.Component):
    def __init__(self, bot: Bot):
        self.bot = bot

    @commands.Component.listener()
    async def event_message(self, payload: twitchio.ChatMessage) -> None:
        print(f"[{payload.broadcaster.name}] - {payload.chatter.name}: {payload.text}")
        await event_bus.put(("channel.message", payload))

    """@commands.Component.listener()
    async def event_channel_update(self, payload: twitchio.ChannelUpdate) -> None:
        print("channel updated")"""

    @commands.Component.listener()
    async def event_cheer(self, payload: twitchio.ChannelCheer) -> None:
        await event_bus.put(("channel.cheer", payload))

    @commands.Component.listener()
    async def event_stream_online(self, payload: twitchio.StreamOnline) -> None:
        print("received stream online")
        await payload.broadcaster.send_message(
            sender=self.bot.bot_id, message="dave prime activated and at your service"
        )


async def fetch_guys() -> None:
    # Fetch corresponding Twitch IDs for usernames
    async with twitchio.Client(
        client_id=CLIENT_ID, client_secret=CLIENT_SECRET
    ) as client:
        await client.login()
        user = await client.fetch_users(logins=[OWNER_USERNAME, BOT_USERNAME])
        for u in user:
            print(f"User: {u.name} - ID: {u.id}")


async def initialise() -> None:
    twitchio.utils.setup_logging(level=logging.INFO)

    async with asqlite.create_pool("tokens.db") as tdb, Bot(token_database=tdb) as bot:
        await bot.setup_database()
        await bot.start(with_adapter=False)


if __name__ == "__main__":
    # asyncio.run(fetch_guys())
    pass
