"""
游资量化 MCP 工具服务器

Agent 访问整个系统的入口，封装了所有底层功能为可调用的工具。

启动方式:
    python mcp_servers/trader_quant.py

工具清单:
- 核心工具: get_market_sentiment, get_nuclear_buttons, get_profit_effect
- 扫描工具: scan_capacity_dragons, scan_emotion_dragons, scan_elastic_dragons
- 信号工具: get_weak_to_strong, get_first_yin_signal, get_auction_signals
- 辅助工具: analyze_position_rank, check_logic_strength, update_watch_pool, set_strategy_config
- 龙头识别: score_theme_dragons, analyze_all_dragons
- 大资金工具: check_flow_switch, check_macro_environment
- 游资监控: get_sector_momentum, scan_stock_anomalies, check_linkage_effects
"""

from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import asdict

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from mcp.server.fastmcp import FastMCP

# 导入底层模块
from lib.data.redis_client import RedisClient
from lib.filters.calendar_filter import CalendarFilter
from lib.indicators.sentiment import SentimentMonitor
from lib.indicators.capacity import CapacityFilter, EmotionDragonScanner, ElasticDragonScanner
from lib.indicators.logic import LogicScore
from lib.indicators.position import PositionRanker
from lib.indicators.dragon_scorer import get_dragon_scorer
from lib.strategies.signal_strategy import (
    WeakToStrongStrategy,
    FirstYinStrategy,
    AuctionStrategy,
)
from lib.strategies.weak_to_strong import get_weak_to_strong_scanner
from lib.monitors.see_saw_monitor import SeeSawMonitor
from lib.monitors.macro_kill_switch import MacroKillSwitch
from lib.models import WatchPool, WatchPoolItem, StrategyConfig
from lib.trading import get_trading_service

# ===================== 初始化 =====================

# 创建 MCP 服务器
mcp = FastMCP("trader-quant")

# 初始化依赖
# - 默认：自动连接 Redis，失败则回退 mock
# - 强制 mock：设置环境变量 REDIS_USE_MOCK=1
# - 指定连接：REDIS_URL 或 REDIS_HOST/REDIS_PORT/REDIS_DB/REDIS_PASSWORD
redis_client = RedisClient.from_env()
calendar_filter = CalendarFilter()

# 初始化各模块
sentiment_monitor = SentimentMonitor(redis_client, calendar_filter)
capacity_filter = CapacityFilter(redis_client)
emotion_scanner = EmotionDragonScanner(redis_client)
elastic_scanner = ElasticDragonScanner(redis_client)
logic_scorer = LogicScore(redis_client)
position_ranker = PositionRanker(redis_client)
dragon_scorer = get_dragon_scorer()
weak_to_strong_strategy = WeakToStrongStrategy(redis_client)
first_yin_strategy = FirstYinStrategy(redis_client)
auction_strategy = AuctionStrategy(redis_client)
see_saw_monitor = SeeSawMonitor(redis_client)
macro_kill_switch = MacroKillSwitch(redis_client)
trading_service = get_trading_service(redis_client)


# ===================== 核心工具 =====================

@mcp.tool()
def get_market_sentiment(date: str = None) -> dict:
    """
    获取市场情绪状态

    这是 Engine A 的核心输出，用于判断今日作战模式。
    Agent 在盘前/盘中调用此工具来决定操作策略。

    Args:
        date: 日期，格式 YYYYMMDD，默认今天

    Returns:
        {
            "date": "20251225",
            "status": "进攻",              # 进攻/试错/防守/空仓
            "phase": "主升期",             # 主升期/震荡期/退潮期
            "indicators": {
                "profit_effect": 3.5,      # 赚钱效应 %
                "nuclear_buttons": 0,       # 核按钮数量
                "big_face_count": 2,        # 大面数量
                "max_height": 7,            # 连板高度
                "zt_count": 85,             # 涨停家数
                "explosion_rate": 15.2      # 炸板率 %
            },
            "suggestion": {
                "position": "70-100%",
                "strategy": "龙头锁仓，做强不做弱",
                "forbidden": []
            }
        }
    """
    result = sentiment_monitor.get_market_sentiment(date)

    return {
        "date": result.date,
        "status": result.status.value,
        "phase": result.phase.value,
        "indicators": {
            "profit_effect": result.indicators.profit_effect,
            "nuclear_buttons": result.indicators.nuclear_buttons,
            "big_face_count": result.indicators.big_face_count,
            "max_height": result.indicators.max_height,
            "zt_count": result.indicators.zt_count,
            "explosion_rate": result.indicators.explosion_rate,
        },
        "suggestion": {
            "position": result.position_suggestion,
            "strategy": result.strategy_suggestion,
            "forbidden": result.forbidden_operations,
        },
    }


@mcp.tool()
def get_nuclear_buttons(date: str = None) -> dict:
    """
    获取核按钮列表

    核按钮 = 昨日连板股今日竞价跌停开盘
    ≥ 3 个核按钮 = 强制防守模式

    这是风控的第一道关卡，必须在任何买入决策前检查！

    Args:
        date: 日期，格式 YYYYMMDD，默认今天

    Returns:
        {
            "count": 2,
            "alert": "CAUTION",            # CLEAR/CAUTION/WARNING
            "message": "发现核按钮，降低仓位",
            "buttons": [
                {
                    "code": "000001",
                    "name": "xxx",
                    "open_percent": -9.8,
                    "board_count": 5,
                    "danger_level": "极高"
                }
            ]
        }
    """
    result = sentiment_monitor.get_nuclear_buttons(date)

    return {
        "count": result.count,
        "alert": result.alert.value,
        "message": result.message,
        "buttons": [
            {
                "code": b.code,
                "name": b.name,
                "open_percent": b.open_percent,
                "board_count": b.board_count,
                "danger_level": b.danger_level,
            }
            for b in result.buttons
        ],
    }


@mcp.tool()
def get_profit_effect(date: str = None) -> dict:
    """
    获取赚钱效应（昨日涨停溢价率）

    > 3%: 超强赚钱效应，无脑做多
    0-3%: 正常
    < 0%: 亏钱效应，禁止接力

    Args:
        date: 日期，格式 YYYYMMDD，默认今天

    Returns:
        {
            "premium": 3.5,
            "status": "超强",
            "action": "无脑做多"
        }
    """
    return sentiment_monitor.get_profit_effect(date)


# ===================== 扫描工具 =====================

@mcp.tool()
def scan_capacity_dragons(min_amount: float = 20) -> dict:
    """
    扫描容量龙

    容量龙 = 日均成交额 ≥ 20亿的大票
    玩法 = 趋势+波段，可重仓锁仓

    这是大资金的生命线！10亿资金必须关注容量。

    Args:
        min_amount: 最低日均成交额（亿），默认20

    Returns:
        {
            "count": 8,
            "dragons": [
                {
                    "code": "600XXX",
                    "name": "某某科技",
                    "avg_amount": 25.6,
                    "capacity_level": "A",
                    "quant_ratio": 0.2,
                    "theme": "AI大模型",
                    "logic_score": 85,
                    "position_rank": "龙一"
                }
            ]
        }
    """
    dragons = capacity_filter.scan_capacity_dragons(min_amount)

    return {
        "count": len(dragons),
        "dragons": [
            {
                "code": d.code,
                "name": d.name,
                "avg_amount": d.avg_amount,
                "capacity_level": d.capacity_level.value,
                "quant_ratio": d.quant_ratio,
                "theme": d.theme,
                "logic_score": d.logic_score,
                "position_rank": d.position_rank.value,
            }
            for d in dragons
        ],
    }


@mcp.tool()
def scan_emotion_dragons() -> dict:
    """
    扫描情绪龙

    情绪龙 = 连板股，辨识度高
    玩法 = 打板接力，快进快出

    Returns:
        {
            "count": 5,
            "max_height": 7,
            "dragons": [
                {
                    "code": "000XXX",
                    "name": "某某股份",
                    "board_count": 7,
                    "seal_amount": 5.2,
                    "turnover_rate": 18.5,
                    "theme": "低空经济",
                    "position_rank": "龙一"
                }
            ]
        }
    """
    return emotion_scanner.scan_emotion_dragons()


@mcp.tool()
def scan_elastic_dragons() -> dict:
    """
    扫描弹性龙（20CM套利机会）

    弹性龙 = 创业板/科创板同属性跟风股
    玩法 = 主板龙头一字封死时做跟风

    Returns:
        {
            "main_leader": {
                "code": "600XXX",
                "name": "主板龙头",
                "is_yizi": true,
                "seal_ratio": 8.5
            },
            "dragons": [
                {
                    "code": "300XXX",
                    "name": "创业板跟风",
                    "current_pct": 5.2,
                    "avg_amount": 8.5,
                    "theme": "低空经济"
                }
            ]
        }
    """
    return elastic_scanner.scan_elastic_dragons()


# ===================== 信号工具 =====================

@mcp.tool()
def get_weak_to_strong(time: str = None) -> dict:
    """
    获取弱转强信号

    弱转强 = 昨日弱势 → 今日高开翻红
    这是最确定的买点！

    5类弱转强来源:
    1. 炸板股: 昨日涨停但开板
    2. 烂板股: 封板太晚 (>14:00)
    3. 断板股: 昨日连板今日未封
    4. 首阴股: ≥5板龙头首次收阴
    5. 大面修复: 昨日跌>7%今日高开

    Args:
        time: 时间 HH:MM，默认当前

    Returns:
        {
            "time": "09:35",
            "count": 3,
            "signals": [
                {
                    "code": "300XXX",
                    "name": "某某科技",
                    "weak_type": "炸板",
                    "strength": "强",
                    "today": {
                        "open_pct": 3.5,
                        "volume_ratio": 4.2,
                        "current_pct": 5.8
                    },
                    "confirm_results": [...],
                    "entry_points": ["竞价确认", "站上均线"],
                    "position": "20-30%",
                    "stop_loss": "跌破均线减半，破昨低清仓"
                }
            ]
        }
    """
    scanner = get_weak_to_strong_scanner()
    return scanner.get_signals()


@mcp.tool()
def scan_weak_to_strong_candidates() -> dict:
    """
    扫描所有弱转强候选（盘前分析用）

    扫描5类弱转强来源，用于盘前制定作战计划。

    Returns:
        {
            "date": "20251226",
            "total": 15,
            "by_type": {
                "炸板": [...],
                "烂板": [...],
                "断板": [...],
                "首阴": [...],
                "大面": [...]
            },
            "candidates": [...]
        }
    """
    scanner = get_weak_to_strong_scanner()
    return scanner.scan_all_candidates()


@mcp.tool()
def get_first_yin_signal() -> dict:
    """
    获取龙头首阴信号

    龙头首阴 = ≥5板龙头首次收阴
    买点 = 尾盘低吸 或 次日弱转强

    Returns:
        {
            "count": 1,
            "signals": [
                {
                    "code": "000XXX",
                    "name": "某某股份",
                    "board_count": 6,
                    "yesterday_close_pct": -5.2,
                    "turnover_rate": 18.5,
                    "entry_points": ["尾盘低吸", "次日弱转强"],
                    "position": "10-20%",
                    "stop_loss": "不反包即走"
                }
            ]
        }
    """
    return first_yin_strategy.get_first_yin_signals()


@mcp.tool()
def get_auction_signals() -> dict:
    """
    获取竞价信号（9:25后调用）

    竞价是一天的成败关键！

    Returns:
        {
            "time": "09:25",
            "market_status": "进攻",
            "nuclear_buttons": [...],
            "signals": {
                "顶一字抢筹": [
                    {"code": "...", "auction_pct": 9.5, "operation": "挂涨停排队"}
                ],
                "强势高开": [...],
                "弱转强候选": [...],
                "核按钮": [...]
            }
        }
    """
    return auction_strategy.get_auction_signals()


# ===================== 辅助工具 =====================

@mcp.tool()
def analyze_position_rank(sector: str) -> dict:
    """
    身位判定

    只做前排，剔除跟风杂毛！
    龙一/龙二 = 可参与
    杂毛 = 不做

    Args:
        sector: 板块名称

    Returns:
        {
            "sector": "AI大模型",
            "count": 5,
            "rankings": [
                {
                    "code": "000001",
                    "name": "xxx",
                    "position": "龙一",
                    "first_seal_time": "09:32",
                    "seal_ratio": 5.2,
                    "participation": "核心"
                }
            ]
        }
    """
    return position_ranker.analyze_position_rank(sector)


@mcp.tool()
def check_logic_strength(theme: str) -> dict:
    """
    检查题材逻辑硬度

    逻辑硬度决定能否重仓！
    ≥ 80分: 可重仓
    < 40分: 不建议参与

    Args:
        theme: 题材名称

    Returns:
        {
            "theme": "低空经济",
            "score": 85,
            "freshness": "新题材",
            "logic_type": "政策补贴",
            "suggestion": "逻辑硬，可重仓参与"
        }
    """
    result = logic_scorer.check_logic_strength(theme)

    return {
        "theme": result.theme,
        "score": result.score,
        "freshness": result.freshness,
        "logic_type": result.logic_type,
        "suggestion": result.suggestion,
    }


@mcp.tool()
def update_watch_pool(pool: dict) -> dict:
    """
    更新监控池

    Agent 通过此工具指挥 Python 明天盯谁！
    这是 Agent 的核心价值之一。

    Args:
        pool: {
            "dragon_queue": [{"code": "...", "name": "...", "priority": 1}],
            "candidates": [...],
            "anomaly": [...]
        }

    Returns:
        {
            "success": true,
            "message": "监控池已更新",
            "count": 25
        }
    """
    # 转换为 WatchPool
    watch_pool = WatchPool(
        dragon_queue=[WatchPoolItem(**i) for i in pool.get("dragon_queue", [])],
        candidates=[WatchPoolItem(**i) for i in pool.get("candidates", [])],
        anomaly=[WatchPoolItem(**i) for i in pool.get("anomaly", [])],
    )

    redis_client.set_today_watch_pool(watch_pool)

    return {
        "success": True,
        "message": "监控池已更新",
        "count": watch_pool.total_count,
    }


@mcp.tool()
def set_strategy_config(config: dict) -> dict:
    """
    设置策略配置

    Agent 通过此工具调整 Python 的"灵敏度"！

    Args:
        config: {
            "mode": "aggressive" / "normal" / "defensive",
            "volume_ratio_threshold": 1.5,
            "position_limit": 0.5
        }

    Returns:
        {
            "success": true,
            "message": "配置已更新",
            "config": {...}
        }
    """
    strategy_config = StrategyConfig(
        mode=config.get("mode", "normal"),
        volume_ratio_threshold=config.get("volume_ratio_threshold", 1.5),
        position_limit=config.get("position_limit", 1.0),
    )

    redis_client.set_strategy_config(strategy_config)

    return {
        "success": True,
        "message": "配置已更新",
        "config": asdict(strategy_config),
    }


# ===================== 交易工具（纸/实盘） =====================

@mcp.tool()
def get_trading_status() -> dict:
    """
    获取交易执行状态（默认纸交易）

    Returns:
        {
            "mode": "paper" / "live",
            "broker": "paper" / "binance",
            "live_enabled": false,
            "require_confirm_token": true,
            "max_order_notional": null,
            "max_order_qty": null,
            "symbol_allowlist": null,
            "symbol_blocklist": null
        }
    """
    return trading_service.get_status().to_dict()


@mcp.tool()
def get_trading_account() -> dict:
    """
    获取账户信息

    - 纸交易：返回现金/持仓/订单数
    - 实盘：返回 broker 账户信息（目前支持 Binance）
    """
    return trading_service.get_account()


@mcp.tool()
def paper_reset_account(cash: float | None = None, base_currency: str | None = None) -> dict:
    """
    重置纸交易账户（只影响 paper 模式）

    Args:
        cash: 初始现金，默认保留当前
        base_currency: 基础货币，如 CNY / USD，默认保留当前
    """
    return trading_service.paper_reset(cash=cash, base_currency=base_currency)


@mcp.tool()
def place_order(
    symbol: str,
    side: str,
    quantity: float,
    order_type: str = "MARKET",
    price: float | None = None,
    time_in_force: str | None = None,
    client_order_id: str | None = None,
    dry_run: bool = True,
    confirm_token: str | None = None,
) -> dict:
    """
    下单（默认 dry_run=True，不会真实成交）

    安全护栏（实盘必须同时满足）:
    1) TRADING_MODE=live
    2) ALLOW_LIVE_TRADING=1
    3) 环境变量 LIVE_TRADING_CONFIRM_TOKEN 已设置，且 confirm_token 传入同样的值

    Args:
        symbol: 交易标的，如 A股 "600519" 或 Binance "BTCUSDT"
        side: BUY / SELL
        quantity: 数量
        order_type: MARKET / LIMIT
        price: LIMIT 单价格（MARKET 单可不传，会尽力自动取价用于风控/纸成交）
        time_in_force: 仅 LIMIT 单（默认 GTC）
        client_order_id: 自定义订单ID（可选）
        dry_run: 默认 True，仅返回风控通过与 notional 估算
        confirm_token: 实盘确认token（见上方安全护栏）
    """
    return trading_service.place_order(
        symbol=symbol,
        side=side,
        order_type=order_type,
        quantity=quantity,
        price=price,
        time_in_force=time_in_force,
        client_order_id=client_order_id,
        dry_run=dry_run,
        confirm_token=confirm_token,
    )


# ===================== 龙头识别工具 =====================

@mcp.tool()
def score_theme_dragons(theme: str) -> dict:
    """
    对指定题材内所有龙头进行四维评分

    四维评分模型:
    - 辨识度 (30%): 连板数、成交额、换手率
    - 封单质量 (25%): 封单比、炸板次数、封板时间
    - 溢价能力 (25%): 历史溢价表现
    - 引领性 (20%): 题材涨停数、题材内排名

    Args:
        theme: 题材名称，如 "AI大模型"、"低空经济"

    Returns:
        {
            "theme": "AI大模型",
            "count": 5,
            "dragons": [
                {
                    "code": "000XXX",
                    "name": "某某股份",
                    "total_score": 85.5,
                    "rank": "龙一",
                    "participation": "核心参与，可重仓",
                    "scores": {
                        "recognition": 90,
                        "seal_quality": 85,
                        "premium": 80,
                        "leadership": 88
                    }
                }
            ]
        }
    """
    scores = dragon_scorer.score_theme(theme)

    return {
        "theme": theme,
        "count": len(scores),
        "dragons": [
            {
                "code": s.code,
                "name": s.name,
                "total_score": s.total_score,
                "rank": s.rank,
                "participation": s.participation,
                "scores": {
                    "recognition": s.recognition_score,
                    "seal_quality": s.seal_quality_score,
                    "premium": s.premium_score,
                    "leadership": s.leadership_score,
                },
            }
            for s in scores
        ],
    }


@mcp.tool()
def analyze_all_dragons() -> dict:
    """
    分析今日所有题材的龙头

    遍历今日所有活跃题材，对每个题材进行龙头评分。
    使用四维评分模型代替简单的首封时间排序。

    Returns:
        {
            "date": "20251226",
            "theme_count": 8,
            "themes": {
                "AI大模型": {
                    "dragon_1": {...},
                    "dragon_2": {...},
                    "count": 5,
                    "all_ranked": [...]
                },
                "低空经济": {...}
            }
        }
    """
    all_themes = dragon_scorer.analyze_all_themes()

    return {
        "date": datetime.now().strftime("%Y%m%d"),
        "theme_count": len(all_themes),
        "themes": all_themes,
    }


# ===================== 大资金监控 =====================

@mcp.tool()
def set_flow_switch_pools(
    yesterday_leaders: list[str] | None = None,
    today_candidates: list[str] | None = None,
) -> dict:
    """
    设置跷跷板监控池

    Args:
        yesterday_leaders: 昨日龙头代码列表
        today_candidates: 今日备选代码列表
    """
    if yesterday_leaders:
        see_saw_monitor.set_yesterday_leaders(yesterday_leaders)
    if today_candidates:
        see_saw_monitor.set_today_candidates(today_candidates)
    return {
        "success": True,
        "yesterday_leaders": yesterday_leaders or [],
        "today_candidates": today_candidates or [],
    }


@mcp.tool()
def check_flow_switch(
    yesterday_leaders: list[str] | None = None,
    today_candidates: list[str] | None = None,
    use_watch_pool: bool = True,
) -> dict:
    """
    检测资金切换信号

    跷跷板效应：旧龙头急杀 + 新标的拉升 = 最佳买点！

    Returns:
        {
            "signal": "FLOW_SWITCH" / null,
            "message": "分离确认！旧龙头资金切换到新标的",
            "old_leader": {
                "code": "...",
                "change_3min": -5.2
            },
            "new_target": {
                "code": "...",
                "change_3min": 6.8
            },
            "confidence": "HIGH",
            "operation": "买入 xxx"
        }
    """
    # 允许临时覆盖监控池
    if yesterday_leaders:
        see_saw_monitor.set_yesterday_leaders(yesterday_leaders)
    if today_candidates:
        see_saw_monitor.set_today_candidates(today_candidates)

    # 默认：从监控池补齐备选名单（若用户未显式传参）
    if use_watch_pool and not yesterday_leaders and not today_candidates:
        pool = redis_client.get_today_watch_pool()
        if pool.dragon_queue:
            see_saw_monitor.set_yesterday_leaders([i.code for i in pool.dragon_queue])
        if pool.candidates:
            see_saw_monitor.set_today_candidates([i.code for i in pool.candidates])

    return see_saw_monitor.check_flow_switch()


@mcp.tool()
def check_macro_environment() -> dict:
    """
    检测宏观环境

    宏观总闸：CNH急贬 / A50跳水 / 北向大幅流出 = 强制防守！

    Returns:
        {
            "alert": "CLEAR" / "MACRO_KILL_SWITCH",
            "trigger": "" / "CNH_CRASH" / "A50_CRASH" / "NORTH_OUTFLOW",
            "message": "宏观环境正常",
            "action": "",
            "detail": {
                "usd_cnh": 7.25,
                "a50": -0.5,
                "north_flow": 50
            }
        }
    """
    result = macro_kill_switch.check()

    return {
        "alert": result.alert_type,
        "trigger": result.trigger,
        "message": result.message,
        "action": result.action,
        "detail": result.detail,
    }


# ===================== 增量数据工具 =====================

@mcp.tool()
def get_zt_pool_delta(date: str = None) -> dict:
    """
    获取涨停池增量变化

    相比全量获取，只返回变化部分，减少数据量。
    适合盘中高频调用。

    Args:
        date: 日期，格式 YYYYMMDD，默认今天

    Returns:
        {
            "current": [...],           # 当前完整涨停池
            "added": [                  # 新增涨停
                {"code": "000XXX", "name": "某某", "first_seal_time": "10:15"}
            ],
            "removed": [                # 移除（炸板/开板）
                {"code": "000YYY", "name": "某某", "open_count": 2}
            ],
            "changed": [                # 封单变化（变化>20%）
                {"code": "000ZZZ", "old_seal": 3.5, "new_seal": 5.2, "change": 0.48}
            ],
            "is_incremental": true,
            "changed_count": 5,
            "total_count": 85
        }
    """
    from lib.data.market_data import get_market_client
    client = get_market_client()
    return client.get_zt_pool_delta(date)


@mcp.tool()
def get_realtime_delta(codes: list = None) -> dict:
    """
    获取实时行情增量变化

    只返回价格变化超过阈值的股票。
    适合监控特定股票池的实时变化。

    Args:
        codes: 股票代码列表，如 ["000001", "600519"]
               不传则使用当日涨停池

    Returns:
        {
            "all": {
                "000001": {"price": 10.5, "change_pct": 5.2, ...},
                ...
            },
            "changed": {                # 只包含变化的股票
                "000001": {
                    "current": {...},
                    "old": {...},
                    "price_change": 0.15,
                    "pct_change": 0.3
                }
            },
            "is_incremental": true,
            "changed_count": 3
        }
    """
    from lib.data.market_data import get_market_client
    client = get_market_client()

    if not codes:
        # 默认使用涨停池
        zt_pool = client.get_zt_pool()
        codes = [s.code for s in zt_pool[:50]]  # 取前50只

    return client.get_realtime_quote_delta(codes)


@mcp.tool()
def get_cache_stats() -> dict:
    """
    获取数据缓存统计

    用于监控缓存命中率和性能。

    Returns:
        {
            "size": 150,               # 缓存条目数
            "max_size": 1000,          # 最大容量
            "hits": 1250,              # 命中次数
            "misses": 80,              # 未命中次数
            "hit_rate": 0.94           # 命中率
        }
    """
    from lib.data.market_data import get_market_client
    client = get_market_client()
    return client.get_cache_stats()


@mcp.tool()
def get_calendar_info(date: str = None) -> dict:
    """
    获取交易日历信息

    包括是否交易日、是否节假日、是否股指交割日等。

    Args:
        date: 日期，格式 YYYYMMDD，默认今天

    Returns:
        {
            "date": "2025-12-26",
            "weekday": "Friday",
            "is_trading_day": true,
            "is_holiday": false,
            "is_pre_holiday": false,      # 是否节前最后交易日
            "is_delivery_day": true,      # 是否股指交割日
            "is_half_day": false,         # 是否半天交易日
            "next_trading_day": "2025-12-29",
            "prev_trading_day": "2025-12-25",
            "risk_warning": ["股指交割日，期现联动剧烈"]
        }
    """
    from lib.filters.calendar_filter import get_calendar_filter
    from datetime import datetime

    calendar = get_calendar_filter()

    if date:
        d = datetime.strptime(date, "%Y%m%d").date()
    else:
        d = datetime.now().date()

    info = calendar.get_calendar_info(d)

    # 添加风险提示
    risk = calendar.get_calendar_risk(datetime.combine(d, datetime.min.time()))
    info["risk_warning"] = risk.warnings
    info["position_limit"] = risk.position_limit

    return info


# ===================== 游资监控工具 (新增) =====================

@mcp.tool()
def get_sector_momentum(top_n: int = 10) -> dict:
    """
    获取板块涨速排名

    监控"短时爆发力"，找到资金进攻方向。
    3分钟涨速 > 0.5% = 资金正在进攻
    3分钟涨速 < -0.5% = 资金正在撤退

    Args:
        top_n: 返回前N个板块

    Returns:
        {
            "time": "09:45",
            "rising": [  # 上涨板块（3分钟涨速最快）
                {
                    "code": "BK0891",
                    "name": "低空经济",
                    "change_pct": 2.1,        # 当前涨跌幅
                    "momentum_3min": 1.5,     # 3分钟涨速
                    "momentum_5min": 2.8,     # 5分钟涨速
                    "net_inflow": 5.2,        # 主力净流入（亿）
                    "zt_count": 5,            # 涨停家数
                    "leader": {               # 领涨大哥（情绪锚点）
                        "code": "002665",
                        "name": "万丰奥威",
                        "change_pct": 8.5,
                        "is_zt": false
                    }
                }
            ],
            "falling": [  # 退潮板块
                {
                    "code": "BK0XXX",
                    "name": "AI语料",
                    "change_pct": -1.2,
                    "momentum_3min": -0.8
                }
            ],
            "alert": ""  # 空/"SECTOR_CRASH" 板块崩塌警报
        }
    """
    from lib.monitors.sector_momentum import get_sector_momentum_tracker
    from lib.data.market_data import get_market_client

    client = get_market_client()
    tracker = get_sector_momentum_tracker(client)
    result = tracker.get_sector_momentum(top_n)
    return result.to_dict()


@mcp.tool()
def scan_stock_anomalies(
    watch_codes: list = None,
    include_zt_pool: bool = True,
) -> dict:
    """
    扫描个股异动

    监控盘口语言，发现进攻/风险信号。

    异动类型:
    - ROCKET: 火箭发射，1分钟拉升 > 3%
    - BIG_BUY: 万手抢筹，主买 > 1万手
    - DIVE: 高台跳水，2分钟下杀 > 4%
    - SEAL_BREAK: 封板被砸（炸板）
    - RE_SEAL: 炸板后回封

    Args:
        watch_codes: 监控代码列表（可选）
        include_zt_pool: 是否包含涨停池股票

    Returns:
        {
            "time": "09:45",
            "attack_signals": [  # 进攻信号
                {
                    "code": "600XXX",
                    "name": "高新发展",
                    "type": "ROCKET",
                    "description": "1分钟拉升3%",
                    "trigger_time": "09:44:32",
                    "current_pct": 7.2,
                    "change_1min": 3.2,
                    "volume_ratio": 5.5
                }
            ],
            "risk_signals": [  # 风险信号
                {
                    "code": "300XXX",
                    "name": "罗博特科",
                    "type": "DIVE",
                    "description": "2分钟下杀4%",
                    "trigger_time": "09:45:15",
                    "current_pct": -2.1,
                    "change_2min": -4.1
                }
            ],
            "seal_status": [  # 封板状态变化
                {
                    "code": "000XXX",
                    "name": "某某股份",
                    "event": "SEAL_BREAK",
                    "seal_amount_before": 5.2,
                    "seal_amount_after": 0,
                    "break_count": 2
                }
            ]
        }
    """
    from lib.monitors.anomaly_detector import get_anomaly_detector
    from lib.data.market_data import get_market_client

    client = get_market_client()
    detector = get_anomaly_detector(client)
    result = detector.scan_anomalies(watch_codes, include_zt_pool)
    return result.to_dict()


@mcp.tool()
def check_linkage_effects() -> dict:
    """
    检测联动效应

    发现套利机会。当龙一封死时，检测龙二的跟随情况。

    联动类型:
    - 身位联动: 龙一封板 → 龙二跟随

    Returns:
        {
            "time": "09:45",
            "bond_linkage": [],  # 股债联动（暂未实现）
            "position_linkage": [  # 身位联动
                {
                    "theme": "低空经济",
                    "dragon_1": {
                        "code": "002665",
                        "name": "万丰奥威",
                        "status": "封死",
                        "change_pct": 10.0,
                        "seal_ratio": 8.5
                    },
                    "dragon_2": {
                        "code": "600XXX",
                        "name": "某某科技",
                        "current_pct": 5.2,
                        "target_pct": 10.0,
                        "opportunity": "龙一封死，龙二跟随中"
                    }
                }
            ]
        }
    """
    from lib.monitors.linkage_monitor import get_linkage_monitor
    from lib.data.market_data import get_market_client

    client = get_market_client()
    monitor = get_linkage_monitor(client)

    # 尝试获取题材龙头数据
    try:
        all_dragons = analyze_all_dragons()
        themes = all_dragons.get("themes", {})
        monitor.update_theme_dragons(themes)
    except Exception as e:
        pass  # 如果没有龙头数据，返回空结果

    result = monitor.check_linkage()
    return result.to_dict()


# ===================== 淘股吧抓取工具 =====================

@mcp.tool()
def get_taoguba_review(date: str = None) -> dict:
    """
    获取淘股吧"湖南人"的每日复盘（截图方式）

    使用Chrome截图获取湖南人的涨停复盘文章，返回截图路径供分析。
    淘股吧内容是动态加载的，必须用浏览器渲染后截图。

    Args:
        date: 日期，格式 MMDD 如 "1225"，默认获取最新一篇

    Returns:
        {
            "title": "12.25湖南人涨停复盘+晚间消息汇总",
            "date": "2025-12-25",
            "url": "https://www.tgb.cn/a/xxx",
            "screenshot_path": "/tmp/tgb_review_1225.png",
            "message": "截图成功，请用Read工具读取图片分析"
        }
    """
    import httpx
    from bs4 import BeautifulSoup
    import re
    import subprocess
    import os
    from datetime import datetime

    # 湖南人的用户ID
    USER_ID = "444409"
    BLOG_URL = f"https://www.tgb.cn/blog/{USER_ID}"

    try:
        # 获取博客文章列表
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

        with httpx.Client(timeout=30, follow_redirects=True) as client:
            # 获取博客主页
            resp = client.get(BLOG_URL, headers=headers)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")

            # 查找文章列表
            articles = []

            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                text = link.get_text(strip=True)

                # 匹配复盘文章链接
                if "复盘" in text and ("湖南人" in text or "涨停" in text):
                    date_match = re.search(r"(\d{1,2})\.(\d{1,2})", text)
                    if date_match:
                        month = date_match.group(1).zfill(2)
                        day = date_match.group(2).zfill(2)
                        article_date = f"{month}{day}"

                        if href.startswith("/"):
                            full_url = f"https://www.tgb.cn{href}"
                        elif href.startswith("http"):
                            full_url = href
                        else:
                            full_url = f"https://www.tgb.cn/{href}"

                        articles.append({
                            "title": text,
                            "date": article_date,
                            "url": full_url,
                        })

            if not articles:
                return {
                    "error": "未找到复盘文章",
                    "blog_url": BLOG_URL,
                    "suggestion": "请检查博客页面是否正常"
                }

            # 如果指定日期，查找对应文章
            target_article = None
            if date:
                for article in articles:
                    if article["date"] == date:
                        target_article = article
                        break
                if not target_article:
                    return {
                        "error": f"未找到 {date} 的复盘文章",
                        "available_dates": [a["date"] for a in articles[:5]],
                    }
            else:
                target_article = articles[0]

            # 使用Chrome截图
            screenshot_path = f"/tmp/tgb_review_{target_article['date']}.png"

            # Chrome路径（macOS）
            chrome_paths = [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
            ]

            chrome_path = None
            for p in chrome_paths:
                if os.path.exists(p):
                    chrome_path = p
                    break

            if not chrome_path:
                return {
                    "error": "未找到Chrome浏览器",
                    "suggestion": "请安装Google Chrome",
                    "url": target_article["url"],
                }

            # 执行截图
            cmd = [
                chrome_path,
                "--headless",
                f"--screenshot={screenshot_path}",
                "--window-size=1920,4000",  # 长截图
                "--virtual-time-budget=15000",  # 等待JS加载
                "--disable-gpu",
                "--no-sandbox",
                target_article["url"],
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if not os.path.exists(screenshot_path):
                return {
                    "error": "截图失败",
                    "stderr": result.stderr[:500] if result.stderr else "",
                    "url": target_article["url"],
                }

            # 构建完整日期
            current_year = datetime.now().year
            article_month = target_article["date"][:2]
            article_day = target_article["date"][2:]
            full_date = f"{current_year}-{article_month}-{article_day}"

            return {
                "title": target_article["title"],
                "date": full_date,
                "url": target_article["url"],
                "author": "湖南人",
                "screenshot_path": screenshot_path,
                "message": "截图成功！请用 Read 工具读取图片进行分析",
            }

    except subprocess.TimeoutExpired:
        return {
            "error": "截图超时",
            "suggestion": "请重试",
        }
    except httpx.HTTPError as e:
        return {
            "error": f"网络请求失败: {str(e)}",
            "blog_url": BLOG_URL,
        }
    except Exception as e:
        return {
            "error": f"执行失败: {str(e)}",
            "blog_url": BLOG_URL,
        }


@mcp.tool()
def list_taoguba_reviews(limit: int = 10) -> dict:
    """
    获取淘股吧"湖南人"的复盘文章列表

    Args:
        limit: 返回文章数量，默认10篇

    Returns:
        {
            "count": 10,
            "articles": [
                {
                    "title": "12.25湖南人涨停复盘...",
                    "date": "1225",
                    "url": "https://..."
                }
            ]
        }
    """
    import httpx
    from bs4 import BeautifulSoup
    import re

    USER_ID = "444409"
    BLOG_URL = f"https://www.tgb.cn/blog/{USER_ID}"

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        with httpx.Client(timeout=30, follow_redirects=True) as client:
            resp = client.get(BLOG_URL, headers=headers)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")

            articles = []
            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                text = link.get_text(strip=True)

                if "复盘" in text and ("湖南人" in text or "涨停" in text):
                    date_match = re.search(r"(\d{1,2})\.(\d{1,2})", text)
                    if date_match:
                        month = date_match.group(1).zfill(2)
                        day = date_match.group(2).zfill(2)

                        if href.startswith("/"):
                            full_url = f"https://www.tgb.cn{href}"
                        elif href.startswith("http"):
                            full_url = href
                        else:
                            full_url = f"https://www.tgb.cn/{href}"

                        articles.append({
                            "title": text,
                            "date": f"{month}{day}",
                            "url": full_url,
                        })

                        if len(articles) >= limit:
                            break

            return {
                "count": len(articles),
                "blog_url": BLOG_URL,
                "articles": articles,
            }

    except Exception as e:
        return {
            "error": str(e),
            "blog_url": BLOG_URL,
        }


# ===================== 服务器启动 =====================

if __name__ == "__main__":
    mcp.run()
