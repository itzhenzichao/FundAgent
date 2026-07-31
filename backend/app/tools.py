import json
from app.fund_service import FundService
from app.industry_service import IndustryService
from app.db import get_connection, init_tables

_fund_service = FundService()
_industry_service = IndustryService()

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_fund",
            "description": "查询基金基本信息（名称、类型、最新净值、净值日期）。当用户提到某只基金、需要了解基金概况时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "6位基金代码，如 003293"}
                },
                "required": ["code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_fund_holdings",
            "description": "查询基金股票持仓（重仓股、持仓占比、季度）。当用户想了解基金买了什么股票、持仓结构时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "6位基金代码"},
                    "date": {"type": "string", "description": "查询年份，如 2025，可选，默认当年"}
                },
                "required": ["code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_fund_industry",
            "description": "查询基金持仓的行业分布（各行业占比、偏离度分析）。当用户想了解基金行业集中度、是否偏离声称方向时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "6位基金代码"},
                    "date": {"type": "string", "description": "查询年份，可选"},
                    "fund_name": {"type": "string", "description": "基金名称，可选，用于偏离度分析"}
                },
                "required": ["code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_fund_nav",
            "description": "查询基金净值历史和最大回撤数据。当用户想了解基金净值走势、回撤情况时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "6位基金代码"},
                    "period": {
                        "type": "string",
                        "enum": ["1m", "3m", "6m", "1y", "3y"],
                        "description": "时间周期：1m=近1月, 3m=近3月, 6m=近6月, 1y=近1年, 3y=近3年，默认1y"
                    }
                },
                "required": ["code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_fund_returns",
            "description": "查询基金近15个交易日每日收益率。当用户想了解基金近期表现、每日涨跌时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "6位基金代码"}
                },
                "required": ["code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_fund_bond_holdings",
            "description": "查询基金债券持仓（债券代码、名称、占比、市值）。当用户想了解债券型基金或偏债基金的债券持仓时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "6位基金代码"},
                    "date": {"type": "string", "description": "查询年份，可选"}
                },
                "required": ["code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_watchlist",
            "description": "获取用户自选基金列表（含持仓、余额、收益信息）。当用户问'我的自选''我的持仓''我关注的基金'等与用户个人投资组合相关的问题时使用。无需参数。",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    }
]

TOOL_NAME_MAP = {
    "search_fund": "查询基金信息",
    "get_fund_holdings": "查询股票持仓",
    "get_fund_industry": "查询行业分布",
    "get_fund_nav": "查询净值回撤",
    "get_fund_returns": "查询近期收益",
    "get_fund_bond_holdings": "查询债券持仓",
    "get_watchlist": "查询自选列表",
}


def execute_tool(name: str, arguments: dict) -> str:
    """执行工具调用，返回 JSON 字符串"""
    try:
        if name == "search_fund":
            result = _fund_service.search_fund(arguments["code"])
        elif name == "get_fund_holdings":
            result = _fund_service.get_holdings(arguments["code"], arguments.get("date"))
        elif name == "get_fund_industry":
            result = _industry_service.analyze_fund_industry(
                arguments["code"], arguments.get("date"), arguments.get("fund_name")
            )
        elif name == "get_fund_nav":
            result = _fund_service.get_nav_history(arguments["code"], arguments.get("period", "1y"))
            # 截断过长的净值数据，避免 token 溢出
            if "nav_data" in result and len(result["nav_data"]) > 30:
                result["nav_data"] = result["nav_data"][-30:]
                result["nav_data_truncated"] = True
            if "drawdown_data" in result and len(result["drawdown_data"]) > 30:
                result["drawdown_data"] = result["drawdown_data"][-30:]
        elif name == "get_fund_returns":
            result = _fund_service.get_recent_returns(arguments["code"])
        elif name == "get_fund_bond_holdings":
            result = _fund_service.get_bond_holdings(arguments["code"], arguments.get("date"))
        elif name == "get_watchlist":
            result = _get_watchlist_data()
        else:
            return json.dumps({"error": f"未知工具: {name}"}, ensure_ascii=False)

        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def _get_watchlist_data() -> list:
    """获取自选基金列表"""
    init_tables()
    conn = get_connection()
    rows = conn.execute(
        "SELECT fund_code, fund_name, added_at, position_amount, profit_amount, "
        "cost_nav, cost_nav_date, position_updated_at FROM watchlist ORDER BY added_at DESC"
    ).fetchall()
    conn.close()

    result = []
    for r in rows:
        pos = r["position_amount"] or 0
        prof = r["profit_amount"] or 0
        cost_nav = r["cost_nav"] or 0
        is_holding = pos > 0 and cost_nav > 0
        result.append({
            "code": r["fund_code"],
            "name": r["fund_name"],
            "is_holding": is_holding,
            "position_amount": pos if is_holding else 0,
            "profit_amount": prof if is_holding else 0,
        })
    return result
