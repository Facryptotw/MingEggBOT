"""
TWSE / TPEX 處置股資料服務
抓取：處置股清單、注意股票、個股收盤價
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import aiohttp

from config import HEADERS, TWSE_BASE_URL, TPEX_BASE_URL


# ── Data Models ────────────────────────────────────────────────

@dataclass
class DispositionStock:
    """正在處置 / 即將處置的股票"""
    code: str
    name: str
    start_date: datetime
    end_date: datetime
    market: str = "twse"  # twse / tpex

    @property
    def total_days(self) -> int:
        return (self.end_date - self.start_date).days

    @property
    def remaining_days(self) -> int:
        delta = (self.end_date - datetime.now()).days
        return max(delta, 0)

    @property
    def is_active(self) -> bool:
        now = datetime.now()
        return self.start_date <= now <= self.end_date

    @property
    def days_until_start(self) -> int:
        delta = (self.start_date - datetime.now()).days
        return max(delta, 0)

    @property
    def is_upcoming(self) -> bool:
        return datetime.now() < self.start_date


@dataclass
class WarningStock:
    """注意股累計狀況 - 接近處置門檻"""
    code: str
    name: str
    accumulation_info: str  # 原始累計說明文字
    consecutive_days: int = 0  # 連續天數
    total_in_period: int = 0   # 區間內累計次數
    period_days: int = 0       # 區間天數
    market: str = "twse"

    @property
    def days_until_disposition(self) -> int:
        """預估距離處置的天數（連續3次或10天內6次觸發）"""
        if self.consecutive_days >= 3:
            return 0
        if self.period_days > 0 and self.period_days <= 10 and self.total_in_period >= 6:
            return 0
        
        if self.consecutive_days == 2:
            return 1
        if self.period_days <= 10 and self.total_in_period == 5:
            return 1
        if self.period_days <= 10 and self.total_in_period == 4:
            return 2
        
        return max(3 - self.consecutive_days, 1)

    @property
    def risk_level(self) -> str:
        """風險等級"""
        if self.consecutive_days >= 3 or (self.period_days <= 10 and self.total_in_period >= 6):
            return "極高"
        if self.consecutive_days == 2 or (self.period_days <= 10 and self.total_in_period >= 5):
            return "高"
        if self.consecutive_days == 1 or (self.period_days <= 10 and self.total_in_period >= 4):
            return "中"
        return "低"


@dataclass
class ExitingStock:
    """即將出關的股票（含漲跌幅比較）"""
    code: str
    name: str
    start_date: datetime
    end_date: datetime
    remaining_days: int
    price_before_pct: float = 0.0   # 處置前 N 天漲跌幅
    price_during_pct: float = 0.0   # 處置中漲跌幅
    market: str = "twse"

    @property
    def tag(self) -> str:
        if self.price_before_pct > 20 and self.price_during_pct > 20:
            return "妖股誕生"
        elif self.price_before_pct > 20 and self.price_during_pct < -5:
            return "人去樓空"
        elif self.price_during_pct > 10:
            return "強勢突圍"
        elif self.price_during_pct < -5:
            return "走勢疲軟"
        else:
            return "多空膠著"

    @property
    def tag_color(self) -> str:
        mapping = {
            "妖股誕生": "#FF4500",
            "人去樓空": "#8B5CF6",
            "強勢突圍": "#F59E0B",
            "走勢疲軟": "#6B7280",
            "多空膠著": "#3B82F6",
        }
        return mapping.get(self.tag, "#FFFFFF")


# ── API Client ─────────────────────────────────────────────────

class TWSEService:
    """台灣證券交易所 & 櫃買中心資料抓取"""

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=HEADERS)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # ── TWSE 處置股 ──

    async def fetch_disposition_list(self) -> list[DispositionStock]:
        """抓取上市處置股清單（使用 announcement/punish API）"""
        session = await self._get_session()
        url = f"{TWSE_BASE_URL}/announcement/punish"
        params = {"response": "json"}

        try:
            async with session.get(url, params=params, ssl=False) as resp:
                data = await resp.json(content_type=None)

            if not data or "data" not in data or data.get("stat") != "OK":
                return []

            stocks = []
            for row in data["data"]:
                stock = self._parse_twse_disposition_row(row)
                if stock:
                    stocks.append(stock)
            return stocks

        except Exception as e:
            print(f"[TWSE] 抓取處置股失敗: {e}")
            return []

    def _parse_twse_disposition_row(self, row: list) -> Optional[DispositionStock]:
        """解析 announcement/punish 格式：編號,公布日期,證券代號,證券名稱,...,處置起迄時間"""
        try:
            code = str(row[2]).strip() if len(row) > 2 else ""
            name = str(row[3]).strip() if len(row) > 3 else ""
            date_range = str(row[6]).strip() if len(row) > 6 else ""

            if not code or not name or not date_range:
                return None

            start_date, end_date = self._parse_date_range(date_range)
            if not start_date or not end_date:
                return None

            return DispositionStock(
                code=code, name=name,
                start_date=start_date, end_date=end_date,
                market="twse",
            )
        except Exception:
            return None

    # ── TPEX 處置股（櫃買） ──

    async def fetch_tpex_disposition_list(self) -> list[DispositionStock]:
        """抓取上櫃處置股清單（使用 OpenAPI）"""
        session = await self._get_session()
        url = f"{TPEX_BASE_URL}/openapi/v1/tpex_disposal_information"

        try:
            async with session.get(url, ssl=False) as resp:
                data = await resp.json(content_type=None)

            if not data or not isinstance(data, list):
                return []

            stocks = []
            seen = set()
            for item in data:
                stock = self._parse_tpex_disposition_item(item)
                if stock and stock.code not in seen:
                    stocks.append(stock)
                    seen.add(stock.code)
            return stocks

        except Exception as e:
            print(f"[TPEX] 抓取處置股失敗: {e}")
            return []

    def _parse_tpex_disposition_item(self, item: dict) -> Optional[DispositionStock]:
        """解析 TPEX OpenAPI 格式"""
        try:
            code = item.get("SecuritiesCompanyCode", "").strip()
            name = item.get("CompanyName", "").strip()
            period = item.get("DispositionPeriod", "").strip()

            if not code or not name or not period:
                return None

            # 解析 1150225~1150313 格式
            if "~" in period:
                parts = period.split("~")
                sp, ep = parts[0].strip(), parts[1].strip()
                start_date = datetime(int(sp[:3]) + 1911, int(sp[3:5]), int(sp[5:7]))
                end_date = datetime(int(ep[:3]) + 1911, int(ep[3:5]), int(ep[5:7]))
            else:
                return None

            return DispositionStock(
                code=code, name=name,
                start_date=start_date, end_date=end_date,
                market="tpex",
            )
        except Exception:
            return None

    # ── 注意股累計（警示股） ──

    async def fetch_twse_warning_stocks(self) -> list[WarningStock]:
        """抓取上市注意股累計狀況（notetrans API）"""
        session = await self._get_session()
        url = f"{TWSE_BASE_URL}/announcement/notetrans"
        params = {"response": "json"}

        try:
            async with session.get(url, params=params, ssl=False) as resp:
                data = await resp.json(content_type=None)

            if not data or "data" not in data:
                return []

            stocks = []
            for row in data["data"]:
                stock = self._parse_twse_warning_row(row)
                if stock:
                    stocks.append(stock)
            return stocks

        except Exception as e:
            print(f"[TWSE] 抓取注意股累計失敗: {e}")
            return []

    def _parse_twse_warning_row(self, row: list) -> Optional[WarningStock]:
        """解析 notetrans 格式：編號,證券代號,證券名稱,累計情形"""
        try:
            code = str(row[1]).strip() if len(row) > 1 else ""
            name = str(row[2]).strip() if len(row) > 2 else ""
            info = str(row[3]).strip() if len(row) > 3 else ""

            if not code or not name:
                return None

            consecutive, total, period = self._parse_accumulation_info(info)

            return WarningStock(
                code=code, name=name,
                accumulation_info=info,
                consecutive_days=consecutive,
                total_in_period=total,
                period_days=period,
                market="twse",
            )
        except Exception:
            return None

    async def fetch_tpex_warning_stocks(self) -> list[WarningStock]:
        """抓取上櫃注意股累計狀況"""
        session = await self._get_session()
        url = f"{TPEX_BASE_URL}/openapi/v1/tpex_trading_warning_note"

        try:
            async with session.get(url, ssl=False) as resp:
                data = await resp.json(content_type=None)

            if not data or not isinstance(data, list):
                return []

            stocks = []
            seen = set()
            for item in data:
                stock = self._parse_tpex_warning_item(item)
                if stock and stock.code not in seen:
                    stocks.append(stock)
                    seen.add(stock.code)
            return stocks

        except Exception as e:
            print(f"[TPEX] 抓取注意股累計失敗: {e}")
            return []

    def _parse_tpex_warning_item(self, item: dict) -> Optional[WarningStock]:
        """解析 TPEX warning_note 格式"""
        try:
            code = item.get("SecuritiesCompanyCode", "").strip()
            name = item.get("CompanyName", "").strip()
            info = item.get("AccumulationSituation", "").strip()

            if not code or not name:
                return None

            consecutive, total, period = self._parse_accumulation_info(info)

            return WarningStock(
                code=code, name=name,
                accumulation_info=info,
                consecutive_days=consecutive,
                total_in_period=total,
                period_days=period,
                market="tpex",
            )
        except Exception:
            return None

    @staticmethod
    def _parse_accumulation_info(info: str) -> tuple[int, int, int]:
        """
        解析累計說明文字
        例如：'115年2月3日至115年2月24日等九個營業日已有五次'
        例如：'115年02月10日至115年02月24日連續四次115年02月03日至115年02月24日等九個營業日已有五次'
        返回：(連續天數, 區間累計次數, 區間天數)
        """
        consecutive = 0
        total = 0
        period = 0

        cn_num = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

        consecutive_match = re.search(r"連續([一二三四五六七八九十\d]+)次", info)
        if consecutive_match:
            val = consecutive_match.group(1)
            consecutive = cn_num.get(val, int(val) if val.isdigit() else 0)

        total_match = re.search(r"([一二三四五六七八九十\d]+)個營業日已有([一二三四五六七八九十\d]+)次", info)
        if total_match:
            period_val = total_match.group(1)
            total_val = total_match.group(2)
            period = cn_num.get(period_val, int(period_val) if period_val.isdigit() else 0)
            total = cn_num.get(total_val, int(total_val) if total_val.isdigit() else 0)

        return consecutive, total, period

    async def get_all_warning_stocks(self) -> list[WarningStock]:
        """取得上市 + 上櫃所有注意股累計"""
        twse_list, tpex_list = await asyncio.gather(
            self.fetch_twse_warning_stocks(),
            self.fetch_tpex_warning_stocks(),
        )
        all_stocks = twse_list + tpex_list
        return sorted(all_stocks, key=lambda x: x.days_until_disposition)

    # ── 股價 ──

    async def fetch_stock_price(self, code: str, date: datetime) -> Optional[float]:
        """取得指定日期的收盤價（上市）"""
        session = await self._get_session()
        date_str = date.strftime("%Y%m%d")
        url = f"{TWSE_BASE_URL}/rwd/zh/afterTrading/STOCK_DAY"
        params = {"date": date_str, "stockNo": code, "response": "json"}

        try:
            async with session.get(url, params=params, ssl=False) as resp:
                data = await resp.json(content_type=None)

            if not data or "data" not in data:
                return None

            for row in reversed(data["data"]):
                try:
                    close_price = float(row[6].replace(",", ""))
                    return close_price
                except (ValueError, IndexError):
                    continue
            return None

        except Exception as e:
            print(f"[TWSE] 抓取股價失敗 {code}: {e}")
            return None

    async def fetch_stock_prices_range(
        self, code: str, start: datetime, end: datetime
    ) -> dict[str, float]:
        """取得日期區間的收盤價 {date_str: price}"""
        prices = {}
        current = datetime(start.year, start.month, 1)
        end_month = datetime(end.year, end.month, 1)

        while current <= end_month:
            session = await self._get_session()
            date_str = current.strftime("%Y%m%d")
            url = f"{TWSE_BASE_URL}/rwd/zh/afterTrading/STOCK_DAY"
            params = {"date": date_str, "stockNo": code, "response": "json"}

            try:
                async with session.get(url, params=params, ssl=False) as resp:
                    data = await resp.json(content_type=None)

                if data and "data" in data:
                    for row in data["data"]:
                        try:
                            roc_date_str = row[0].strip()
                            close_price = float(row[6].replace(",", ""))
                            d = self._parse_roc_date(roc_date_str)
                            if d and start <= d <= end:
                                prices[d.strftime("%Y-%m-%d")] = close_price
                        except (ValueError, IndexError):
                            continue

            except Exception as e:
                print(f"[TWSE] 抓取股價區間失敗 {code}: {e}")

            if current.month == 12:
                current = datetime(current.year + 1, 1, 1)
            else:
                current = datetime(current.year, current.month + 1, 1)

            await asyncio.sleep(0.5)

        return prices

    # ── 高階方法：組合資料 ──

    async def get_all_dispositions(self) -> list[DispositionStock]:
        """取得上市 + 上櫃所有處置股"""
        twse_list, tpex_list = await asyncio.gather(
            self.fetch_disposition_list(),
            self.fetch_tpex_disposition_list(),
        )
        return twse_list + tpex_list

    async def get_active_dispositions(self) -> list[DispositionStock]:
        """取得目前正在處置中的股票"""
        all_stocks = await self.get_all_dispositions()
        return [s for s in all_stocks if s.is_active]

    async def get_upcoming_dispositions(self) -> list[DispositionStock]:
        """取得即將開始處置的股票（尚未開始）"""
        all_stocks = await self.get_all_dispositions()
        return [s for s in all_stocks if s.is_upcoming]

    async def get_exiting_stocks(self, within_days: int = 5) -> list[ExitingStock]:
        """取得即將出關的股票（剩餘 N 天內）含漲跌幅"""
        all_stocks = await self.get_all_dispositions()
        now = datetime.now()

        exiting = []
        for s in all_stocks:
            remaining = (s.end_date - now).days
            if 0 <= remaining <= within_days and s.is_active:
                exiting.append(ExitingStock(
                    code=s.code, name=s.name,
                    start_date=s.start_date, end_date=s.end_date,
                    remaining_days=remaining, market=s.market,
                ))

        for stock in exiting:
            await self._fill_price_change(stock)
            await asyncio.sleep(0.3)

        return sorted(exiting, key=lambda x: x.remaining_days)

    async def _fill_price_change(self, stock: ExitingStock):
        """填入處置前/處置中漲跌幅"""
        try:
            disp_days = (stock.end_date - stock.start_date).days
            before_start = stock.start_date - timedelta(days=disp_days + 10)
            before_end = stock.start_date - timedelta(days=1)

            before_prices = await self.fetch_stock_prices_range(
                stock.code, before_start, before_end
            )
            during_prices = await self.fetch_stock_prices_range(
                stock.code, stock.start_date, datetime.now()
            )

            if before_prices:
                sorted_before = sorted(before_prices.items())
                first_before = sorted_before[0][1]
                last_before = sorted_before[-1][1]
                if first_before > 0:
                    stock.price_before_pct = round(
                        (last_before - first_before) / first_before * 100, 1
                    )

            if during_prices:
                sorted_during = sorted(during_prices.items())
                first_during = sorted_during[0][1]
                last_during = sorted_during[-1][1]
                if first_during > 0:
                    stock.price_during_pct = round(
                        (last_during - first_during) / first_during * 100, 1
                    )

        except Exception as e:
            print(f"[PRICE] 計算漲跌幅失敗 {stock.code}: {e}")

    # ── 工具方法 ──

    @staticmethod
    def _parse_date_range(date_range: str) -> tuple[Optional[datetime], Optional[datetime]]:
        """解析日期區間，如 '115/02/24～115/03/10' 或 '115/02/25~115/03/13'"""
        separators = ["～", "~", "－", "-", "—", "至"]
        for sep in separators:
            if sep in date_range:
                parts = date_range.split(sep)
                if len(parts) == 2:
                    start = TWSEService._parse_roc_date(parts[0].strip())
                    end = TWSEService._parse_roc_date(parts[1].strip())
                    return start, end
        return None, None

    @staticmethod
    def _parse_roc_date(date_str: str) -> Optional[datetime]:
        """解析民國日期 (114/02/25 or 114年02月25日)"""
        date_str = date_str.strip()
        patterns = [
            r"(\d{2,3})/(\d{1,2})/(\d{1,2})",
            r"(\d{2,3})年(\d{1,2})月(\d{1,2})日",
        ]
        for pattern in patterns:
            m = re.match(pattern, date_str)
            if m:
                year = int(m.group(1)) + 1911
                month = int(m.group(2))
                day = int(m.group(3))
                try:
                    return datetime(year, month, day)
                except ValueError:
                    return None
        return None
