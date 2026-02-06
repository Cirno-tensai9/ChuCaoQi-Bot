import os
import asyncio

import discord

from dbConnection.db import DB, createUser, getUser, getDonateAmount
from plugins.kusa_main import getWarehouseInfoStr, vipTitleName
from plugins import kusa_farm


class DummySession:
    """
    Minimal shim object to reuse existing NoneBot-oriented handlers
    from Discord by mimicking the subset of CommandSession used.
    """

    def __init__(self, user_id: str, channel: discord.abc.Messageable, arg_text: str = ""):
        self.ctx = {
            "user_id": user_id,
        }
        self.current_arg_text = arg_text
        self._channel = channel

    async def send(self, content: str):
        # Relay messages back to the originating Discord channel
        await self._channel.send(content)


intents = discord.Intents.default()
intents.message_content = True


discord_client = discord.Client(intents=intents)


@discord_client.event
async def on_ready():
    print(f"Discord bot logged in as {discord_client.user} (id={discord_client.user.id})")


@discord_client.event
async def on_message(message: discord.Message):
    # Ignore messages from bots (including ourselves)
    if message.author.bot:
        return

    content = message.content.strip()
    if not content.startswith("!"):
        return

    # Very small command parser: "!命令 [参数...]"
    without_prefix = content[1:]
    if not without_prefix:
        return

    parts = without_prefix.split(maxsplit=1)
    cmd = parts[0]
    arg_text = parts[1] if len(parts) > 1 else ""

    user_id = str(message.author.id)

    # Ensure user exists in shared database
    await createUser(user_id)

    # !仓库 — reuse existing warehouse logic
    if cmd == "仓库":
        user = await getUser(user_id)
        if not user:
            await message.channel.send("无法在数据库中找到你的账户，请稍后再试。")
            return

        nickname = message.author.display_name or user.qq
        donate_amount = await getDonateAmount(user_id)

        output = "感谢您，生草系统的捐助者!\n" if donate_amount else ""
        if user.vipLevel:
            output += f"Lv{user.vipLevel} "
        title = user.title if user.title else vipTitleName[user.vipLevel]
        output += f"{title} "
        output += f"{nickname}({user_id})\n"
        output += await getWarehouseInfoStr(user)

        await message.channel.send(output)
        return

    # !生草 — call existing plantKusa logic through a shim session
    if cmd == "生草":
        dummy_session = DummySession(user_id=user_id, channel=message.channel, arg_text=arg_text)
        await kusa_farm.plantKusa(dummy_session)  # type: ignore[attr-defined]
        return


async def main():
    # Initialize shared database (same sqlite DB as QQ bot)
    await DB.init()

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("Environment variable DISCORD_TOKEN is required to run the Discord bot.")

    await discord_client.start(token)


if __name__ == "__main__":
    asyncio.run(main())

