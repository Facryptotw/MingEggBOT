"""
處置股監控 Cog
- /disposition 手動觸發
- 每日排程自動推送
使用 Discord Embed 文字格式，清晰易讀
"""

from __future__ import annotations

import traceback
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands, tasks

from config import DISCORD_CHANNEL_ID, SCHEDULE_TIME
from services.twse import TWSEService, WarningStock, ExitingStock, DispositionStock


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
            embeds = await self._build_embeds()
            await interaction.followup.send(embeds=embeds)
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
            embeds = await self._build_embeds()
            await channel.send(embeds=embeds)
            print(f"[SCHEDULE] 報告已推送 {now.strftime('%Y-%m-%d %H:%M')}")
        except Exception as e:
            traceback.print_exc()
            print(f"[SCHEDULE] 推送失敗: {e}")

    @daily_report.before_loop
    async def before_daily_report(self):
        await self.bot.wait_until_ready()

    # ── Embed 生成 ──

    async def _build_embeds(self) -> list[discord.Embed]:
        print("[REPORT] 開始抓取資料...")

        warning = await self.twse.get_all_warning_stocks()
        active = await self.twse.get_active_dispositions()
        exiting = await self.twse.get_exiting_stocks(within_days=5)

        print(f"[REPORT] 瀕臨處置: {len(warning)}, 即將出關: {len(exiting)}, 處置中: {len(active)}")

        embeds = []

        # 不需要額外的標題 Embed，直接用三個區塊

        # Section 1: 處置倒數
        embeds.append(self._build_warning_embed(warning))

        # Section 2: 越關越大尾
        embeds.append(self._build_exiting_embed(exiting))

        # Section 3: 還能噴嗎
        embeds.append(self._build_active_embed(active))

        return embeds

    def _build_warning_embed(self, stocks: list[WarningStock]) -> discord.Embed:
        """處置倒數 - 瀕臨處置的股票"""
        embed = discord.Embed(
            title=f"🚨 處置倒數！{len(stocks)} 檔股票瀕臨處置",
            color=0xEF4444,
        )

        if not stocks:
            embed.description = "目前無瀕臨處置的股票"
            return embed

        lines = []
        for s in stocks[:15]:
            days = s.days_until_disposition
            risk = s.risk_level
            
            if risk == "極高" or days == 0:
                icon = "🔥"
                status = "明日開始處置"
            elif days == 1:
                icon = "⚠️"
                status = "處置倒數 1 天"
            elif days == 2:
                icon = "⚠️"
                status = f"處置倒數 {days} 天"
            else:
                icon = "⚠️"
                status = f"處置倒數 {days} 天"

            lines.append(f"{icon} **{s.code} {s.name}**｜{status}")

        embed.description = "\n".join(lines)
        return embed

    def _build_exiting_embed(self, stocks: list[ExitingStock]) -> discord.Embed:
        """越關越大尾 - 即將出關的股票"""
        embed = discord.Embed(
            title=f"🔓 越關越大尾？{len(stocks)} 檔股票即將出關",
            color=0xF59E0B,
        )

        if not stocks:
            embed.description = "目前無即將出關的股票"
            return embed

        lines = []
        # 過濾掉 CB/權證（代號超過5位數）
        normal_stocks = [s for s in stocks if len(s.code) <= 5]
        
        for s in normal_stocks[:12]:
            exit_date = s.end_date.strftime("%m/%d")
            
            # 如果處置前後都是 0，視為無資料
            has_data = not (s.price_before_pct == 0 and s.price_during_pct == 0)
            
            if has_data:
                before_sign = "+" if s.price_before_pct >= 0 else ""
                during_sign = "+" if s.price_during_pct >= 0 else ""

                tag = s.tag
                if tag == "妖股誕生":
                    tag_icon = "🔥👹"
                    tag_text = "妖股誕生"
                elif tag == "強勢突圍":
                    tag_icon = "🔥"
                    tag_text = "強勢突圍"
                elif tag == "人去樓空":
                    tag_icon = "👻"
                    tag_text = "人去樓空"
                elif tag == "走勢疲軟":
                    tag_icon = "📉"
                    tag_text = "走勢疲軟"
                else:
                    tag_icon = "🤔"
                    tag_text = "多空膠著"

                lines.append(f"**{s.code} {s.name}**｜剩 {s.remaining_days} 天 ({exit_date})")
                lines.append(f"▸ {tag_icon} {tag_text} 處置前{before_sign}{s.price_before_pct}% / 處置中{during_sign}{s.price_during_pct}%")
            else:
                lines.append(f"**{s.code} {s.name}**｜剩 {s.remaining_days} 天 ({exit_date})")
                lines.append(f"▸ 📊 股價資料不足")
            lines.append("")

        embed.description = "\n".join(lines)
        
        embed.set_footer(text="💡 說明：處置前 N 天 vs 處置中 N 天 (同天數對比)")
        return embed

    def _build_active_embed(self, stocks: list[DispositionStock]) -> discord.Embed:
        """還能噴嗎 - 正在處置的股票"""
        # 過濾掉 CB/權證（代號超過5位數）
        normal_stocks = [s for s in stocks if len(s.code) <= 5]
        
        embed = discord.Embed(
            title=f"⚡ 還能噴嗎？{len(normal_stocks)} 檔股票正在處置",
            color=0x8B5CF6,
        )

        if not normal_stocks:
            embed.description = "目前無正在處置的股票"
            return embed

        lines = []
        sorted_stocks = sorted(normal_stocks, key=lambda x: x.remaining_days)
        
        for s in sorted_stocks[:20]:
            start_str = s.start_date.strftime("%m/%d")
            end_str = s.end_date.strftime("%m/%d")
            remaining = s.remaining_days

            if remaining <= 1:
                icon = "🔴"
            elif remaining <= 3:
                icon = "🟡"
            else:
                icon = "🟢"

            lines.append(f"{icon} **{s.code} {s.name}**｜{start_str}～{end_str}（剩 {remaining} 天）")

        embed.description = "\n".join(lines)
        return embed


async def setup(bot: commands.Bot):
    await bot.add_cog(DispositionCog(bot))
