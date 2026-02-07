"""
金融工具 MCP 服务器

提供股票数据查询和新闻搜索工具
"""
from __future__ import annotations

import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from lib.data.market_data import get_market_client

# 创建 MCP 服务器
mcp = FastMCP("finance-tools")


# 模拟股票数据
STOCK_DATA = {
    "AAPL": {"name": "Apple Inc.", "price": "193.60", "pe_ratio": "31.2", "market_cap": "3.0T"},
    "GOOGL": {"name": "Alphabet Inc.", "price": "176.50", "pe_ratio": "25.8", "market_cap": "2.2T"},
    "MSFT": {"name": "Microsoft Corp.", "price": "430.20", "pe_ratio": "37.5", "market_cap": "3.2T"},
    "TSLA": {"name": "Tesla Inc.", "price": "248.50", "pe_ratio": "72.3", "market_cap": "790B"},
    "NVDA": {"name": "NVIDIA Corp.", "price": "137.80", "pe_ratio": "65.2", "market_cap": "3.4T"},
    "AMZN": {"name": "Amazon.com Inc.", "price": "198.30", "pe_ratio": "42.1", "market_cap": "2.1T"},
    "META": {"name": "Meta Platforms", "price": "567.80", "pe_ratio": "28.4", "market_cap": "1.4T"},
    "BABA": {"name": "Alibaba Group", "price": "85.20", "pe_ratio": "12.5", "market_cap": "210B"},
}

# 模拟新闻数据
NEWS_DATA = {
    "apple": "苹果公司宣布 Vision Pro 头显销量超预期，分析师上调目标价至 220 美元。同时，iPhone 16 系列在中国市场面临华为竞争压力，市场份额有所下滑。",
    "google": "Alphabet 旗下 Waymo 自动驾驶业务获得 50 亿美元新一轮融资。但核心广告业务增长放缓至 8%，低于市场预期，引发投资者担忧。",
    "microsoft": "微软 Azure 云服务季度增长 29%，AI 服务成为新增长引擎。Copilot 付费用户数突破 100 万，企业 AI 转型需求强劲。",
    "tesla": "特斯拉宣布 Cybertruck 产能爬坡顺利，月产量突破 2 万辆。但欧洲市场电动车补贴退坡导致订单量下滑 15%。马斯克称将在 2025 年推出更低价车型。",
    "nvidia": "英伟达 H100/H200 芯片持续供不应求，数据中心业务营收创历史新高。AI 热潮推动股价年内上涨 200%，但估值过高引发部分机构减持。",
    "amazon": "亚马逊 AWS 推出新一代自研芯片 Graviton4，性能提升 30%。电商业务在假日季表现强劲，Prime 会员数突破 2 亿。",
    "meta": "Meta 的 Llama 3 开源模型获得开发者广泛采用。Reality Labs 部门亏损收窄，Quest 3 头显销量超预期。广告业务受益于 AI 推荐算法优化。",
    "alibaba": "阿里巴巴宣布云智能集团独立上市计划推迟。国内电商业务面临拼多多激烈竞争，但国际业务 Lazada 和速卖通增长强劲。",
}


@mcp.tool()
def get_stock_data(ticker: str) -> dict:
    """
    获取指定股票代码的实时价格和关键财务指标。

    Args:
        ticker: 股票代码，如 AAPL, GOOGL, MSFT, TSLA, NVDA, AMZN

    Returns:
        包含股票名称、价格、市盈率、市值的字典
    """
    ticker_upper = ticker.upper()

    # A股：6位数字代码，使用东财实时行情
    if ticker_upper.isdigit() and len(ticker_upper) == 6:
        client = get_market_client()
        quote = client.get_realtime_quote([ticker_upper]).get(ticker_upper)
        if quote:
            return {
                "ticker": ticker_upper,
                "name": quote.get("name", ""),
                "price": quote.get("price", 0),
                "change_pct": quote.get("change_pct", 0),
                "pe_ratio": quote.get("pe", 0),
                "float_market_cap_yi": quote.get("float_market_cap", 0),
                "total_market_cap_yi": quote.get("total_market_cap", 0),
                "currency": "CNY",
                "source": "eastmoney",
            }

    if ticker_upper in STOCK_DATA:
        data = STOCK_DATA[ticker_upper]
        return {
            "ticker": ticker_upper,
            "name": data["name"],
            "price": data["price"],
            "pe_ratio": data["pe_ratio"],
            "market_cap": data["market_cap"],
            "currency": "USD"
        }

    return {
        "ticker": ticker_upper,
        "name": f"{ticker_upper} (未知公司)",
        "price": "N/A",
        "pe_ratio": "N/A",
        "market_cap": "N/A",
        "currency": "USD",
        "note": "非A股代码时当前仅提供少量模拟数据；A股请传6位代码"
    }


@mcp.tool()
def search_market_news(query: str) -> str:
    """
    搜索关于特定公司或市场的最新突发新闻。

    Args:
        query: 搜索关键词，如公司名称 Apple, Tesla, Microsoft

    Returns:
        相关新闻摘要
    """
    query_lower = query.lower()

    for key, news in NEWS_DATA.items():
        if key in query_lower:
            return f"📰 最新新闻 ({key.upper()}):\n{news}"

    return f"📰 {query} 近期市场表现平稳，暂无重大新闻事件。建议关注公司财报和行业动态。"


if __name__ == "__main__":
    mcp.run()
