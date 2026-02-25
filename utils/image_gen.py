"""
精美金融風格圖卡生成器
1920x1080 橫向版面 - 三欄式設計
"""

from __future__ import annotations

import os
import platform
from datetime import datetime
from io import BytesIO
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from services.twse import DispositionStock, ExitingStock, WarningStock


# ── 色彩系統 ───────────────────────────────────────────────────

class Colors:
    BG_PRIMARY = "#0D1117"
    BG_CARD = "#161B22"
    BG_SECTION = "#1C2333"
    BG_ROW = "#1A2030"
    BG_ROW_ALT = "#151C28"

    GOLD = "#F0B90B"
    GOLD_DIM = "#B8860B"
    RED = "#EF4444"
    GREEN = "#22C55E"
    BLUE = "#3B82F6"
    PURPLE = "#8B5CF6"
    ORANGE = "#F97316"
    CYAN = "#06B6D4"
    PINK = "#EC4899"

    TEXT_PRIMARY = "#E6EDF3"
    TEXT_SECONDARY = "#9CA3AF"
    TEXT_MUTED = "#6B7280"
    DIVIDER = "#30363D"

    TAG_COLORS = {
        "妖股誕生": "#FF4500",
        "人去樓空": "#8B5CF6",
        "強勢突圍": "#F59E0B",
        "走勢疲軟": "#6B7280",
        "多空膠著": "#3B82F6",
    }


# ── 字體管理 ───────────────────────────────────────────────────

class FontManager:
    _cache: dict[str, ImageFont.FreeTypeFont] = {}

    @classmethod
    def _find_font_path(cls) -> str:
        candidates = []
        system = platform.system()

        if system == "Windows":
            font_dir = r"C:\Windows\Fonts"
            candidates = [
                os.path.join(font_dir, "msjh.ttc"),
                os.path.join(font_dir, "msjhbd.ttc"),
                os.path.join(font_dir, "mingliu.ttc"),
            ]
        elif system == "Darwin":
            candidates = [
                "/System/Library/Fonts/PingFang.ttc",
                "/System/Library/Fonts/STHeiti Medium.ttc",
            ]
        else:
            candidates = [
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            ]

        for path in candidates:
            if os.path.exists(path):
                return path
        return ""

    @classmethod
    def _find_bold_font_path(cls) -> str:
        system = platform.system()
        if system == "Windows":
            bold_path = r"C:\Windows\Fonts\msjhbd.ttc"
            if os.path.exists(bold_path):
                return bold_path
        return cls._find_font_path()

    @classmethod
    def get(cls, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        key = f"{'bold' if bold else 'regular'}_{size}"
        if key not in cls._cache:
            path = cls._find_bold_font_path() if bold else cls._find_font_path()
            if path:
                try:
                    cls._cache[key] = ImageFont.truetype(path, size)
                except Exception:
                    cls._cache[key] = ImageFont.load_default()
            else:
                cls._cache[key] = ImageFont.load_default()
        return cls._cache[key]


# ── 圖卡生成器 ─────────────────────────────────────────────────

class DispositionImageGenerator:

    WIDTH = 1920
    HEIGHT = 1080
    PADDING = 40
    COL_GAP = 30
    HEADER_H = 80
    SECTION_HEADER_H = 50
    ROW_H = 42

    def __init__(self):
        self.fonts = FontManager

    def generate(
        self,
        warning: list[WarningStock],
        exiting: list[ExitingStock],
        active: list[DispositionStock],
    ) -> BytesIO:
        img = Image.new("RGB", (self.WIDTH, self.HEIGHT), Colors.BG_PRIMARY)
        draw = ImageDraw.Draw(img)

        self._draw_header(draw, img)
        
        col_width = (self.WIDTH - self.PADDING * 2 - self.COL_GAP * 2) // 3
        col_x = [
            self.PADDING,
            self.PADDING + col_width + self.COL_GAP,
            self.PADDING + (col_width + self.COL_GAP) * 2,
        ]
        content_y = self.HEADER_H + 20

        self._draw_section_warning(draw, col_x[0], content_y, col_width, warning)
        self._draw_section_exiting(draw, col_x[1], content_y, col_width, exiting)
        self._draw_section_active(draw, col_x[2], content_y, col_width, active)

        self._draw_footer(draw, img)

        buf = BytesIO()
        img.save(buf, format="PNG", quality=95)
        buf.seek(0)
        return buf

    # ── Header ──

    def _draw_header(self, draw: ImageDraw.Draw, img: Image.Image):
        draw.rectangle(
            [(0, 0), (self.WIDTH, self.HEADER_H)],
            fill="#111827",
        )
        
        for x in range(self.WIDTH):
            ratio = x / self.WIDTH
            r = int(0xF0 * (1 - ratio * 0.3))
            g = int(0xB9 * (1 - ratio * 0.3))
            b = int(0x0B * (1 - ratio * 0.3))
            img.putpixel((x, self.HEADER_H - 2), (r, g, b))
            img.putpixel((x, self.HEADER_H - 1), (r, g, b))

        title_font = self.fonts.get(32, bold=True)
        draw.text(
            (self.PADDING, 22),
            "[  ] 台股處置監控機器人",
            fill=Colors.GOLD,
            font=title_font,
        )
        
        draw.rectangle([(self.PADDING + 8, 32), (self.PADDING + 28, 52)], outline=Colors.GOLD, width=2)

        date_font = self.fonts.get(18)
        now = datetime.now()
        weekdays = ["一", "二", "三", "四", "五", "六", "日"]
        date_str = f"{now.strftime('%Y/%m/%d')} 週{weekdays[now.weekday()]} {now.strftime('%H:%M')} 更新"
        date_w = draw.textlength(date_str, font=date_font)
        draw.text(
            (self.WIDTH - self.PADDING - date_w, 30),
            date_str,
            fill=Colors.TEXT_SECONDARY,
            font=date_font,
        )

    # ── Section 1: 處置倒數（注意股累計） ──

    def _draw_section_warning(
        self, draw: ImageDraw.Draw, x: int, y: int, width: int,
        stocks: list[WarningStock],
    ):
        y = self._draw_section_header(
            draw, x, y, width,
            title=f"處置倒數 | {len(stocks)} 檔股票瀕臨處置",
            accent=Colors.RED,
        )

        if not stocks:
            hint_font = self.fonts.get(14)
            draw.text(
                (x + 16, y + 20),
                "目前無瀕臨處置的股票",
                fill=Colors.TEXT_MUTED,
                font=hint_font,
            )
            return

        name_font = self.fonts.get(14, bold=True)
        info_font = self.fonts.get(12)
        detail_font = self.fonts.get(11)

        row_h = 52
        for i, stock in enumerate(stocks[:16]):
            row_y = y + i * row_h
            bg = Colors.BG_ROW_ALT if i % 2 == 0 else Colors.BG_ROW
            draw.rectangle(
                [(x, row_y), (x + width, row_y + row_h - 2)],
                fill=bg,
            )

            days = stock.days_until_disposition
            risk = stock.risk_level
            
            if risk == "極高" or days == 0:
                dot_color = Colors.RED
                status = "即將處置"
            elif risk == "高" or days == 1:
                dot_color = Colors.ORANGE
                status = f"倒數 {days} 天"
            elif risk == "中" or days == 2:
                dot_color = Colors.GOLD
                status = f"倒數 {days} 天"
            else:
                dot_color = Colors.CYAN
                status = f"倒數 {days} 天"

            draw.ellipse(
                [(x + 10, row_y + 10), (x + 20, row_y + 20)],
                fill=dot_color,
            )

            code_name = f"{stock.code} {stock.name}"
            draw.text(
                (x + 28, row_y + 6),
                code_name,
                fill=Colors.TEXT_PRIMARY,
                font=name_font,
            )

            status_w = draw.textlength(status, font=info_font)
            draw.text(
                (x + width - status_w - 12, row_y + 8),
                status,
                fill=dot_color,
                font=info_font,
            )

            detail_text = self._format_warning_detail(stock)
            draw.text(
                (x + 28, row_y + 28),
                detail_text,
                fill=Colors.TEXT_MUTED,
                font=detail_font,
            )

    def _format_warning_detail(self, stock: WarningStock) -> str:
        """格式化累計說明"""
        parts = []
        if stock.consecutive_days > 0:
            parts.append(f"連續{stock.consecutive_days}次")
        if stock.total_in_period > 0 and stock.period_days > 0:
            parts.append(f"{stock.period_days}日內{stock.total_in_period}次")
        if parts:
            return " | ".join(parts)
        return stock.accumulation_info[:35] + "..." if len(stock.accumulation_info) > 35 else stock.accumulation_info

    # ── Section 2: 越關越大尾 ──

    def _draw_section_exiting(
        self, draw: ImageDraw.Draw, x: int, y: int, width: int,
        stocks: list[ExitingStock],
    ):
        y = self._draw_section_header(
            draw, x, y, width,
            title=f"越關越大尾? | {len(stocks)} 檔股票即將出關",
            accent=Colors.CYAN,
        )

        if not stocks:
            hint_font = self.fonts.get(14)
            draw.text(
                (x + 16, y + 20),
                "目前無即將出關的股票",
                fill=Colors.TEXT_MUTED,
                font=hint_font,
            )
            return

        name_font = self.fonts.get(14, bold=True)
        info_font = self.fonts.get(12)
        tag_font = self.fonts.get(11, bold=True)

        row_h = 56
        for i, stock in enumerate(stocks[:14]):
            row_y = y + i * row_h
            bg = Colors.BG_ROW_ALT if i % 2 == 0 else Colors.BG_ROW
            draw.rectangle(
                [(x, row_y), (x + width, row_y + row_h - 2)],
                fill=bg,
            )

            code_name = f"{stock.code} {stock.name}"
            draw.text(
                (x + 12, row_y + 6),
                code_name,
                fill=Colors.TEXT_PRIMARY,
                font=name_font,
            )

            exit_date = stock.end_date.strftime("%m/%d")
            remaining_str = f"| 剩 {stock.remaining_days} 天 ({exit_date})"
            draw.text(
                (x + 130, row_y + 8),
                remaining_str,
                fill=Colors.TEXT_SECONDARY,
                font=info_font,
            )

            tag_text = stock.tag
            tag_color = Colors.TAG_COLORS.get(tag_text, Colors.TEXT_SECONDARY)
            tag_w = draw.textlength(tag_text, font=tag_font) + 12
            tag_x = x + width - tag_w - 10
            
            self._draw_rounded_rect(draw, tag_x, row_y + 4, tag_w, 18, 4, tag_color, alpha=60)
            draw.text((tag_x + 6, row_y + 5), tag_text, fill=tag_color, font=tag_font)

            before_color = Colors.RED if stock.price_before_pct >= 0 else Colors.GREEN
            during_color = Colors.RED if stock.price_during_pct >= 0 else Colors.GREEN
            before_sign = "+" if stock.price_before_pct >= 0 else ""
            during_sign = "+" if stock.price_during_pct >= 0 else ""

            perf_y = row_y + 30
            draw.text((x + 12, perf_y), "處置前", fill=Colors.TEXT_MUTED, font=info_font)
            draw.text((x + 55, perf_y), f"{before_sign}{stock.price_before_pct}%", fill=before_color, font=info_font)
            draw.text((x + 115, perf_y), "/ 處置中", fill=Colors.TEXT_MUTED, font=info_font)
            draw.text((x + 170, perf_y), f"{during_sign}{stock.price_during_pct}%", fill=during_color, font=info_font)

    # ── Section 3: 還能噴嗎 ──

    def _draw_section_active(
        self, draw: ImageDraw.Draw, x: int, y: int, width: int,
        stocks: list[DispositionStock],
    ):
        y = self._draw_section_header(
            draw, x, y, width,
            title=f"還能噴嗎? | {len(stocks)} 檔股票正在處置",
            accent=Colors.PURPLE,
        )

        if not stocks:
            hint_font = self.fonts.get(14)
            draw.text(
                (x + 16, y + 20),
                "目前無正在處置的股票",
                fill=Colors.TEXT_MUTED,
                font=hint_font,
            )
            return

        name_font = self.fonts.get(14, bold=True)
        info_font = self.fonts.get(12)

        for i, stock in enumerate(stocks[:20]):
            row_y = y + i * self.ROW_H
            bg = Colors.BG_ROW_ALT if i % 2 == 0 else Colors.BG_ROW
            draw.rectangle(
                [(x, row_y), (x + width, row_y + self.ROW_H - 2)],
                fill=bg,
            )

            draw.text(
                (x + 12, row_y + 10),
                "[x]",
                fill=Colors.PURPLE,
                font=info_font,
            )

            code_name = f"{stock.code} {stock.name}"
            draw.text(
                (x + 40, row_y + 10),
                code_name,
                fill=Colors.TEXT_PRIMARY,
                font=name_font,
            )

            start_str = stock.start_date.strftime("%m/%d")
            end_str = stock.end_date.strftime("%m/%d")
            date_range = f"{start_str} - {end_str}"
            date_w = draw.textlength(date_range, font=info_font)
            draw.text(
                (x + width - date_w - 12, row_y + 12),
                date_range,
                fill=Colors.TEXT_SECONDARY,
                font=info_font,
            )

    # ── Section Header ──

    def _draw_section_header(
        self, draw: ImageDraw.Draw, x: int, y: int, width: int,
        title: str, accent: str,
    ) -> int:
        draw.rectangle(
            [(x, y), (x + width, y + self.SECTION_HEADER_H)],
            fill=Colors.BG_SECTION,
        )

        draw.rectangle(
            [(x, y), (x + 4, y + self.SECTION_HEADER_H)],
            fill=accent,
        )

        header_font = self.fonts.get(16, bold=True)
        draw.text(
            (x + 14, y + 14),
            title,
            fill=Colors.TEXT_PRIMARY,
            font=header_font,
        )

        return y + self.SECTION_HEADER_H + 4

    # ── Footer ──

    def _draw_footer(self, draw: ImageDraw.Draw, img: Image.Image):
        footer_y = self.HEIGHT - 40
        
        for x in range(self.WIDTH):
            ratio = x / self.WIDTH
            r = int(0xB8 + (0xF0 - 0xB8) * ratio)
            g = int(0x86 + (0xB9 - 0x86) * ratio)
            b = int(0x0B)
            img.putpixel((x, footer_y), (r, g, b))
            img.putpixel((x, footer_y + 1), (r, g, b))

        footer_font = self.fonts.get(13)
        footer_text = "資料來源: TWSE / TPEX  |  MingEggBOT  |  僅供參考，不構成投資建議"
        draw.text(
            (self.PADDING, footer_y + 12),
            footer_text,
            fill=Colors.TEXT_MUTED,
            font=footer_font,
        )

    # ── 工具方法 ──

    def _draw_rounded_rect(
        self, draw: ImageDraw.Draw,
        x: int, y: int, w: int, h: int, r: int,
        color: str, alpha: int = 40,
    ):
        from PIL import ImageColor
        rgb = ImageColor.getrgb(color)
        dimmed = tuple(max(0, c // 4) for c in rgb)
        draw.rounded_rectangle(
            [(x, y), (x + w, y + h)],
            radius=r,
            fill=dimmed,
        )


# ── 快速生成 ───────────────────────────────────────────────────

def generate_disposition_image(
    warning: list[WarningStock],
    exiting: list[ExitingStock],
    active: list[DispositionStock],
) -> BytesIO:
    gen = DispositionImageGenerator()
    return gen.generate(warning, exiting, active)
