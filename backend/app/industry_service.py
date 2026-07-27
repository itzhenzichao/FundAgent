import re
from typing import Optional
from app.db import get_connection, init_tables
from app.fund_service import FundService


class IndustryService:
    _db_loaded = False
    fund_service = FundService()

    def _ensure_db(self):
        if not self._db_loaded:
            init_tables()
            self._db_loaded = True

    def _find_stock_industry(self, stock_code: str) -> Optional[str]:
        """从本地 SQLite 数据查找股票行业（数据由 build_industry_cache.py 构建）"""
        self._ensure_db()
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT industry FROM stock_industry WHERE stock_code = ?",
                (stock_code,)
            ).fetchone()
            return row["industry"] if row else None
        finally:
            conn.close()

    def analyze_fund_industry(self, code: str, date: Optional[str] = None, fund_name: Optional[str] = None) -> dict:
        """分析基金持仓的行业分布"""
        holdings_data = self.fund_service.get_holdings(code, date)

        if not fund_name:
            fund_info = self.fund_service.search_fund(code)
            fund_name = fund_info.get("name", "")

        industry_distribution = {}
        unmatched_stocks = []

        for holding in holdings_data["holdings"]:
            stock_code = holding["stock_code"].strip()
            industry = self._find_stock_industry(stock_code)

            if industry:
                if industry not in industry_distribution:
                    industry_distribution[industry] = {
                        "industry": industry,
                        "stocks": [],
                        "total_ratio": 0,
                    }
                industry_distribution[industry]["stocks"].append({
                    "stock_code": stock_code,
                    "stock_name": holding["stock_name"],
                    "holding_ratio": holding["holding_ratio"],
                })
                if holding["holding_ratio"]:
                    industry_distribution[industry]["total_ratio"] += holding["holding_ratio"]
            else:
                unmatched_stocks.append({
                    "stock_code": stock_code,
                    "stock_name": holding["stock_name"],
                    "holding_ratio": holding["holding_ratio"],
                })

        claimed_industry = self._extract_claimed_industry(fund_name)
        deviation = None
        if claimed_industry:
            claimed_ratio = 0
            for ind_name, ind_data in industry_distribution.items():
                if claimed_industry.lower() in ind_name.lower() or ind_name.lower() in claimed_industry.lower():
                    claimed_ratio += ind_data["total_ratio"]
            deviation = {
                "claimed_industry": claimed_industry,
                "claimed_ratio": round(claimed_ratio, 2),
                "threshold": 80,
                "is_deviant": claimed_ratio < 80,
            }

        return {
            "fund_code": code,
            "fund_name": fund_name,
            "quarter": holdings_data["quarter"],
            "industry_distribution": list(industry_distribution.values()),
            "unmatched_stocks": unmatched_stocks,
            "deviation": deviation,
            "total_count": holdings_data.get("total_count", len(holdings_data["holdings"])),
            "truncated": holdings_data.get("truncated", False),
        }

    def _extract_claimed_industry(self, fund_name: str) -> Optional[str]:
        """从基金名称提取声称的行业方向"""
        industry_keywords = {
            "科技": "科技", "信息": "信息技术", "医药": "医药生物",
            "医疗": "医药生物", "消费": "消费", "新能源": "新能源",
            "汽车": "汽车", "金融": "金融", "银行": "银行",
            "地产": "房地产", "军工": "国防军工", "半导体": "半导体",
            "芯片": "半导体", "红利": "红利", "白酒": "食品饮料",
            "互联网": "互联网", "创新": "创新", "成长": "成长",
            "价值": "价值", "蓝筹": "蓝筹", "债券": "债券",
            "股票": "股票", "混合": "混合", "QDII": "QDII",
        }
        for keyword, industry in industry_keywords.items():
            if keyword in fund_name:
                return industry
        return None
