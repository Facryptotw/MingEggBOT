"""
處置股監控 Cog
- /disposition 手動觸發
- 每日排程自動推送
"""

from __future__ import annotations

import traceback
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands, tasks

from config import DISCORD_CHANNEL_ID, SCHEDULE_TIME
from services.twse import TWSEService
from utils.image_gen import generate_disposition_image


class DispositionCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.twse = TWSEService()

    async def cog_load(self):
        self.daily_report.start()

    async def cog_unload(self):
        self.daily_report.cancel()
        await self.twse.close()

    # ── 手動觸發指令 ──

    @app_commands.command(name="disposition", description="📊 查看台股處置股即時監控報告")
    async def disposition_command(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        try:
            image_buf = await self._build_report()
            file = discord.File(fp=image_buf, filename="disposition_report.png")
            await interaction.followup.send(
                content="## ⚡ 台股處置監控報告\n> 資料來源：TWSE / TPEX｜僅供參考",
                file=file,
            )
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(
                f"❌ 報告生成失敗：{str(e)[:200]}",
                ephemeral=True,
            )

    # ── 每日排程 ──

    @tasks.loop(minutes=1)
    async def daily_report(self):
        now = datetime.now()
        target = SCHEDULE_TIME.split(":")
        if now.hour != int(target[0]) or now.minute != int(target[1]):
            return

        if now.weekday() >= 5:
            return

        channel = self.bot.get_channel(DISCORD_CHANNEL_ID)
        if not channel:
            print(f"[SCHEDULE] 找不到頻道 {DISCORD_CHANNEL_ID}")
            return

        try:
            image_buf = await self._build_report()
            file = discord.File(fp=image_buf, filename="disposition_report.png")
            await channel.send(
                content="## ⚡ 台股處置監控報告（每日自動更新）\n> 資料來源：TWSE / TPEX｜僅供參考",
                file=file,
            )
            print(f"[SCHEDULE] 報告已推送 {now.strftime('%Y-%m-%d %H:%M')}")
        except Exception as e:
            traceback.print_exc()
            print(f"[SCHEDULE] 推送失敗: {e}")

    @daily_report.before_loop
    async def before_daily_report(self):
        await self.bot.wait_until_ready()

    # ── 報告生成核心 ──

    async def _build_report(self):
        print("[REPORT] 開始抓取資料...")

        warning = await self.twse.get_all_warning_stocks()
        active = await self.twse.get_active_dispositions()
        exiting = await self.twse.get_exiting_stocks(within_days=5)

        print(f"[REPORT] 瀕臨處置: {len(warning)}, 即將出關: {len(exiting)}, 處置中: {len(active)}")

        image_buf = generate_disposition_image(
            warning=warning,
            exiting=exiting,
            active=active,
        )

        return image_buf


async def setup(bot: commands.Bot):
    await bot.add_cog(DispositionCog(bot))
