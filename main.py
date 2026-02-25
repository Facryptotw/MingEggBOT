"""
MingEggBOT — 台股處置監控機器人
每日自動推送處置倒數、出關追蹤、處置中一覽
"""

import asyncio
import discord
from discord.ext import commands

from config import DISCORD_TOKEN


class MingEggBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(
            command_prefix="!",
            intents=intents,
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="台股處置股監控中",
            ),
        )

    async def setup_hook(self):
        await self.load_extension("cogs.disposition")
        synced = await self.tree.sync()
        print(f"[BOT] 已同步 {len(synced)} 個斜線指令")

    async def on_ready(self):
        print(f"[BOT] 已上線: {self.user} (ID: {self.user.id})")
        print(f"[BOT] 伺服器數: {len(self.guilds)}")
        print("[BOT] ─────────────────────────")


def main():
    if not DISCORD_TOKEN:
        print("❌ 請在 .env 檔案中設定 DISCORD_TOKEN")
        print("   參考 .env.example 建立 .env 檔案")
        return

    bot = MingEggBot()
    bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()
