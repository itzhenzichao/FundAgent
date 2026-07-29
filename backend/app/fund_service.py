import akshare as ak
import efinance as ef
import pandas as pd
import json
import os
from datetime import datetime, timedelta
from typing import Optional
from app.db import get_connection, init_tables

# efinance 基金名称缓存（模块级，只加载一次）
_fund_name_map: dict = {}


def _load_fund_name_map():
    global _fund_name_map
    if _fund_name_map:
        return
    try:
        df = ef.fund.get_fund_codes()
        for _, row in df.iterrows():
            _fund_name_map[str(row['基金代码'])] = str(row['基金简称'])
    except Exception:
        pass


class FundService:

    def search_fund(self, code: str) -> dict:
        """搜索基金基本信息 — 缓存1天过期，名称/类型不过期"""
        init_tables()
        conn = get_connection()

        # 1. 先查缓存
        row = conn.execute(
            "SELECT fund_code, fund_name, fund_type, latest_nav, latest_date, updated_at FROM fund_info WHERE fund_code = ?",
            (code,)
        ).fetchone()

        if row:
            # 名称和类型永远不过期，净值缓存1天
            from datetime import datetime, timedelta
            updated = datetime.fromisoformat(row["updated_at"])
            nav_expired = datetime.now() - updated > timedelta(days=1)

            if not nav_expired:
                conn.close()
                return {
                    "code": row["fund_code"],
                    "name": row["fund_name"],
                    "type": row["fund_type"],
                    "latest_nav": row["latest_nav"],
                    "latest_date": row["latest_date"],
                    "nav_history": [],
                }

        # 2. 缓存没有，调接口获取
        fund_name = code
        fund_type = "未知"
        latest_nav = None
        latest_date = None

        # 先用雪球接口（速度快，覆盖全）
        try:
            xq_df = ak.fund_individual_basic_info_xq(symbol=code)
            if not xq_df.empty:
                item_col = "item" if "item" in xq_df.columns else xq_df.columns[0]
                value_col = "value" if "value" in xq_df.columns else xq_df.columns[1]
                for _, r in xq_df.iterrows():
                    item = str(r[item_col])
                    val = str(r[value_col])
                    if item == "基金名称":
                        fund_name = val
                    elif item == "基金类型":
                        fund_type = val
        except Exception:
            pass

        # 再用东方财富接口获取净值
        try:
            df = ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势")
            if not df.empty:
                latest = df.iloc[-1]
                cols = df.columns.tolist()
                nav_col = "单位净值" if "单位净值" in cols else cols[1] if len(cols) > 1 else None
                date_col = "净值日期" if "净值日期" in cols else cols[0] if len(cols) > 0 else None
                if nav_col and date_col:
                    latest_nav = float(latest[nav_col])
                    latest_date = str(latest[date_col])
        except Exception:
            pass

        # 东方财富基本信息补充（如果雪球没拿到名称）
        if fund_name == code:
            try:
                fund_name_df = ak.fund_open_fund_info_em(symbol=code, indicator="基本信息")
                if not fund_name_df.empty:
                    item_col = "item" if "item" in fund_name_df.columns else fund_name_df.columns[0]
                    value_col = "value" if "value" in fund_name_df.columns else fund_name_df.columns[1]
                    name_rows = fund_name_df[fund_name_df[item_col] == "基金简称"]
                    type_rows = fund_name_df[fund_name_df[item_col] == "基金类型"]
                    if not name_rows.empty:
                        fund_name = str(name_rows[value_col].values[0])
                    if not type_rows.empty:
                        fund_type = str(type_rows[value_col].values[0])
            except Exception:
                pass

        # efinance 名称兜底（纯债基金等雪球和东方财富基本信息都拿不到名称的情况）
        if fund_name == code:
            _load_fund_name_map()
            if code in _fund_name_map:
                fund_name = _fund_name_map[code]

        if fund_name == code and fund_type == "未知" and latest_nav is None:
            conn.close()
            raise ValueError(f"未找到基金 {code}")

        # 3. 写入缓存
        from datetime import datetime
        conn.execute(
            "INSERT OR REPLACE INTO fund_info (fund_code, fund_name, fund_type, latest_nav, latest_date, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (code, fund_name, fund_type, latest_nav, latest_date, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()

        return {
            "code": code,
            "name": fund_name,
            "type": fund_type,
            "latest_nav": latest_nav,
            "latest_date": latest_date,
            "nav_history": [],
        }

    def get_holdings(self, code: str, date: Optional[str] = None) -> dict:
        """获取基金持仓股票 — 缓存7天过期"""
        init_tables()
        conn = get_connection()

        # 1. 先查缓存
        cached = conn.execute(
            "SELECT stock_code, stock_name, holding_ratio, quarter FROM fund_holdings WHERE fund_code = ? ORDER BY holding_ratio DESC",
            (code,)
        ).fetchall()

        if cached:
            # 检查是否过期
            meta = conn.execute(
                "SELECT updated_at FROM fund_holdings WHERE fund_code = ? LIMIT 1",
                (code,)
            ).fetchone()
            if meta:
                from datetime import datetime, timedelta
                updated = datetime.fromisoformat(meta["updated_at"])
                if datetime.now() - updated < timedelta(days=7):
                    holdings = [
                        {"stock_code": r["stock_code"], "stock_name": r["stock_name"],
                         "holding_ratio": r["holding_ratio"], "quarter": r["quarter"]}
                        for r in cached
                    ]
                    total_count = len(holdings)
                    truncated = total_count > 20
                    if truncated:
                        holdings = holdings[:20]
                    conn.close()
                    return {
                        "fund_code": code, "holdings": holdings,
                        "quarter": holdings[0]["quarter"] if holdings else "",
                        "total_count": total_count, "truncated": truncated,
                    }

        # 2. 缓存过期或没有，调接口
        try:
            if date is None:
                from datetime import datetime
                date = str(datetime.now().year)

            df = ak.fund_portfolio_hold_em(symbol=code, date=date)

            if df.empty and date == str(datetime.now().year):
                prev_year = int(date) - 1
                df = ak.fund_portfolio_hold_em(symbol=code, date=str(prev_year))

            if df.empty:
                conn.close()
                return {
                    "fund_code": code, "holdings": [],
                    "quarter": "", "total_count": 0, "truncated": False,
                }

            if "季度" in df.columns:
                latest_quarter = sorted(df["季度"].unique(), reverse=True)[0]
                df = df[df["季度"] == latest_quarter]

            # 清除旧缓存，写入新数据
            conn.execute("DELETE FROM fund_holdings WHERE fund_code = ?", (code,))
            from datetime import datetime as dt
            now = dt.now().isoformat()

            holdings = []
            for _, row in df.iterrows():
                stock_code = str(row.get("股票代码", ""))
                stock_name = str(row.get("股票名称", ""))
                holding_ratio = float(row.get("占净值比例", 0)) if row.get("占净值比例") else None
                quarter = str(row.get("季度", ""))
                conn.execute(
                    "INSERT INTO fund_holdings (fund_code, stock_code, stock_name, holding_ratio, quarter, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (code, stock_code, stock_name, holding_ratio, quarter, now)
                )
                holdings.append({
                    "stock_code": stock_code, "stock_name": stock_name,
                    "holding_ratio": holding_ratio, "quarter": quarter,
                })

            conn.commit()
            conn.close()

            total_count = len(holdings)
            truncated = total_count > 20
            if truncated:
                holdings = holdings[:20]

            return {
                "fund_code": code, "holdings": holdings,
                "quarter": holdings[0]["quarter"] if holdings else "",
                "total_count": total_count, "truncated": truncated,
            }
        except ValueError:
            raise
        except Exception as e:
            conn.close()
            raise ValueError(f"查询基金 {code} 持仓失败: {e}")

    def get_nav_history(self, code: str, period: str = "1y") -> dict:
        """获取基金净值历史和最大回撤数据"""
        # 时间周期映射
        period_map = {
            "1m": 30, "3m": 90, "6m": 180, "1y": 365, "3y": 1095,
        }
        days = period_map.get(period, 365)

        df = ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势")
        if df.empty:
            raise ValueError(f"未找到基金 {code} 的净值数据")

        cols = df.columns.tolist()
        nav_col = "单位净值" if "单位净值" in cols else cols[1] if len(cols) > 1 else None
        date_col = "净值日期" if "净值日期" in cols else cols[0] if len(cols) > 0 else None

        if not nav_col or not date_col:
            raise ValueError("净值数据列名无法识别")

        # 取最近 N 天数据
        from datetime import datetime, timedelta
        cutoff = datetime.now() - timedelta(days=days)
        df[date_col] = pd.to_datetime(df[date_col])
        df = df[df[date_col] >= cutoff].sort_values(date_col)

        nav_list = []
        drawdown_list = []
        max_nav = 0.0

        for _, row in df.iterrows():
            date = str(row[date_col].date()) if hasattr(row[date_col], 'date') else str(row[date_col])
            nav = float(row[nav_col])
            nav_list.append({"date": date, "nav": nav})

            # 计算回撤：当前净值相对于历史最高净值的跌幅
            max_nav = max(max_nav, nav)
            drawdown = (nav - max_nav) / max_nav * 100 if max_nav > 0 else 0
            drawdown_list.append({"date": date, "drawdown": round(drawdown, 2)})

        # 计算区间最大回撤
        max_drawdown = min(d["drawdown"] for d in drawdown_list) if drawdown_list else 0

        return {
            "fund_code": code,
            "period": period,
            "nav_data": nav_list,
            "drawdown_data": drawdown_list,
            "max_drawdown": round(max_drawdown, 2),
        }

    def get_recent_returns(self, code: str) -> dict:
        """获取最近15个交易日的每日收益率"""
        df = ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势")
        if df.empty:
            raise ValueError(f"未找到基金 {code} 的净值数据")

        cols = df.columns.tolist()
        nav_col = "单位净值" if "单位净值" in cols else cols[1] if len(cols) > 1 else None
        date_col = "净值日期" if "净值日期" in cols else cols[0] if len(cols) > 0 else None

        if not nav_col or not date_col:
            raise ValueError("净值数据列名无法识别")

        df[date_col] = pd.to_datetime(df[date_col])
        df = df.sort_values(date_col).tail(16)

        returns = []
        for i in range(1, len(df)):
            prev_row = df.iloc[i - 1]
            curr_row = df.iloc[i]
            prev_nav = float(prev_row[nav_col])
            curr_nav = float(curr_row[nav_col])
            daily_return = (curr_nav - prev_nav) / prev_nav * 100 if prev_nav > 0 else 0
            date = str(curr_row[date_col].date()) if hasattr(curr_row[date_col], 'date') else str(curr_row[date_col])
            returns.append({
                "date": date,
                "nav": round(curr_nav, 4),
                "daily_return": round(daily_return, 2),
            })

        return {
            "fund_code": code,
            "returns": returns,
        }

    def get_bond_holdings(self, code: str, date: Optional[str] = None) -> dict:
        """获取基金债券持仓 — 缓存7天过期"""
        init_tables()
        conn = get_connection()

        # 1. 先查缓存
        cached = conn.execute(
            "SELECT bond_code, bond_name, holding_ratio, holding_value, quarter FROM fund_bond_holdings WHERE fund_code = ? ORDER BY holding_ratio DESC",
            (code,)
        ).fetchall()

        if cached:
            meta = conn.execute(
                "SELECT updated_at FROM fund_bond_holdings WHERE fund_code = ? LIMIT 1",
                (code,)
            ).fetchone()
            if meta:
                from datetime import datetime, timedelta
                updated = datetime.fromisoformat(meta["updated_at"])
                if datetime.now() - updated < timedelta(days=7):
                    holdings = [
                        {"bond_code": r["bond_code"], "bond_name": r["bond_name"],
                         "holding_ratio": r["holding_ratio"], "holding_value": r["holding_value"],
                         "quarter": r["quarter"]}
                        for r in cached
                    ]
                    total_count = len(holdings)
                    truncated = total_count > 20
                    if truncated:
                        holdings = holdings[:20]
                    conn.close()
                    return {
                        "fund_code": code, "bond_holdings": holdings,
                        "quarter": holdings[0]["quarter"] if holdings else "",
                        "total_count": total_count, "truncated": truncated,
                    }

        # 2. 缓存过期或没有，调接口
        try:
            if date is None:
                from datetime import datetime
                date = str(datetime.now().year)

            df = ak.fund_portfolio_bond_hold_em(symbol=code, date=date)

            if df.empty and date == str(datetime.now().year):
                prev_year = int(date) - 1
                df = ak.fund_portfolio_bond_hold_em(symbol=code, date=str(prev_year))

            if df.empty:
                conn.close()
                return {
                    "fund_code": code, "bond_holdings": [],
                    "quarter": "", "total_count": 0, "truncated": False,
                }

            if "季度" in df.columns:
                latest_quarter = sorted(df["季度"].unique(), reverse=True)[0]
                df = df[df["季度"] == latest_quarter]

            # 清除旧缓存，写入新数据
            conn.execute("DELETE FROM fund_bond_holdings WHERE fund_code = ?", (code,))
            from datetime import datetime as dt
            now = dt.now().isoformat()

            holdings = []
            for _, row in df.iterrows():
                bond_code = str(row.get("债券代码", ""))
                bond_name = str(row.get("债券名称", ""))
                holding_ratio = float(row.get("占净值比例", 0)) if row.get("占净值比例") else None
                holding_value = float(row.get("持仓市值", 0)) if row.get("持仓市值") else None
                quarter = str(row.get("季度", ""))
                conn.execute(
                    "INSERT INTO fund_bond_holdings (fund_code, bond_code, bond_name, holding_ratio, holding_value, quarter, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (code, bond_code, bond_name, holding_ratio, holding_value, quarter, now)
                )
                holdings.append({
                    "bond_code": bond_code, "bond_name": bond_name,
                    "holding_ratio": holding_ratio, "holding_value": holding_value,
                    "quarter": quarter,
                })

            conn.commit()
            conn.close()

            total_count = len(holdings)
            truncated = total_count > 20
            if truncated:
                holdings = holdings[:20]

            return {
                "fund_code": code, "bond_holdings": holdings,
                "quarter": holdings[0]["quarter"] if holdings else "",
                "total_count": total_count, "truncated": truncated,
            }
        except Exception as e:
            conn.close()
            raise ValueError(f"查询基金 {code} 债券持仓失败: {e}")
