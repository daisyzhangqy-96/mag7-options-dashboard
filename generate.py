"""
MAG7 期权策略每日生成器
========================
基于富途API，获取MAG7盘前数据+期权链+IV/HV，输出三类策略：
  A. 方向性策略：基于盘前涨跌幅 → Long Call/Put
  B. 卖方策略  ：基于 IV/HV 比值 → Credit Spread / Iron Condor
  C. 综合策略  ：流动性+希腊字母综合打分

输出：data.json（前端读取）
"""
from __future__ import annotations

import json
import math
import sys
import time
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
from futu import (
    AuType,
    KLType,
    OpenQuoteContext,
    RET_OK,
)

MAG7 = [
    ("US.AAPL", "Apple"),
    ("US.MSFT", "Microsoft"),
    ("US.GOOGL", "Alphabet"),
    ("US.AMZN", "Amazon"),
    ("US.META", "Meta"),
    ("US.NVDA", "NVIDIA"),
    ("US.TSLA", "Tesla"),
    ("US.HOOD", "Robinhood"),
    ("US.SPCX", "SpaceX"),  # 占位代码，上市当日核对真实 ticker
]

# 期权选择参数
STRIKE_RANGE_PCT = 0.15           # ATM 上下 15% 范围
EXPIRY_DAYS_MIN = 14              # 最少 14 天到期（避免 0DTE 噪声）
EXPIRY_DAYS_MAX = 45              # 最多 45 天到期
MIN_OPEN_INTEREST = 100           # 最小未平仓量
MAX_CONTRACTS_PER_STOCK = 60      # 每只股票最多探测的期权快照数量
HV_LOOKBACK_DAYS = 30             # HV 回看天数

# ===== 辅助函数 =====


def safe(v: Any) -> Any:
    """把 NaN / Infinity / pandas NA 转成 None，便于 JSON 序列化。"""
    if v is None:
        return None
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None
    if isinstance(v, str) and v == "N/A":
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


def num(v: Any) -> float | None:
    """把任意值安全转成 float 或 None。"""
    v = safe(v)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def calc_hv(closes: pd.Series, days: int = HV_LOOKBACK_DAYS) -> float | None:
    """用对数收益率算年化历史波动率。"""
    if len(closes) < days:
        return None
    rets = np.log(closes / closes.shift(1)).dropna()[-days:]
    if len(rets) == 0:
        return None
    return float(rets.std() * math.sqrt(252))


def pick_expiry(exp_df: pd.DataFrame) -> str | None:
    """选最接近 30 天的到期日。"""
    if exp_df is None or len(exp_df) == 0:
        return None
    df = exp_df[
        (exp_df["option_expiry_date_distance"] >= EXPIRY_DAYS_MIN)
        & (exp_df["option_expiry_date_distance"] <= EXPIRY_DAYS_MAX)
    ].copy()
    if len(df) == 0:
        # 退而求其次，选不为零的最近月
        df = exp_df[exp_df["option_expiry_date_distance"] >= 7].copy()
        if len(df) == 0:
            return None
    df["dist_to_30"] = (df["option_expiry_date_distance"] - 30).abs()
    df = df.sort_values("dist_to_30")
    return df.iloc[0]["strike_time"]


# ===== 主流程 =====


def fetch_underlying(quote_ctx: OpenQuoteContext) -> dict[str, dict]:
    """拉 MAG7 正股快照 + HV。逐个查询，跳过未上市/不存在的代码。"""
    out: dict[str, dict] = {}
    rows = []
    for code, _name in MAG7:
        ret, snap = quote_ctx.get_market_snapshot([code])
        if ret != RET_OK or len(snap) == 0:
            print(f"  [skip] {code} 快照不可用（可能未上市）: {snap}", file=sys.stderr)
            continue
        rows.append(snap)
    if not rows:
        raise RuntimeError("no underlying snapshots available")
    snap = pd.concat(rows, ignore_index=True)

    for code, name in MAG7:
        row = snap[snap["code"] == code]
        if len(row) == 0:
            continue
        r = row.iloc[0]
        last = num(r["last_price"])
        prev = num(r["prev_close_price"])
        pre = num(r["pre_price"])
        pre_chg = num(r["pre_change_rate"])

        # HV
        ret_k, kdata, _pk = quote_ctx.request_history_kline(
            code,
            ktype=KLType.K_DAY,
            autype=AuType.QFQ,
            max_count=HV_LOOKBACK_DAYS + 5,
        )
        hv = None
        if ret_k == RET_OK and len(kdata) > 0:
            hv = calc_hv(kdata["close"])
        time.sleep(0.3)  # 限频保护

        out[code] = {
            "code": code,
            "name": name,
            "last": last,
            "prev_close": prev,
            "pre_price": pre,
            "pre_change_rate": pre_chg,  # 富途已是百分比数值
            "day_change_rate": (last / prev - 1) * 100 if (last and prev) else None,
            "hv": hv,
            "pe_ttm": num(r.get("pe_ttm_ratio")),
            "amplitude": num(r.get("amplitude")),
            "volume": num(r.get("volume")),
        }
    return out


def fetch_option_chain_one(
    quote_ctx: OpenQuoteContext, code: str, last_price: float
) -> list[dict]:
    """对单只股票，拉到期日→链→快照，返回精简期权列表。"""
    ret, exp_df = quote_ctx.get_option_expiration_date(code=code)
    if ret != RET_OK or len(exp_df) == 0:
        print(f"  [{code}] 到期日失败: {exp_df}", file=sys.stderr)
        return []

    expiry = pick_expiry(exp_df)
    if not expiry:
        print(f"  [{code}] 无合适到期日", file=sys.stderr)
        return []

    ret, chain = quote_ctx.get_option_chain(code=code, start=expiry, end=expiry)
    if ret != RET_OK or len(chain) == 0:
        print(f"  [{code}] 期权链失败: {chain}", file=sys.stderr)
        return []

    # 过滤 strike 范围
    lo = last_price * (1 - STRIKE_RANGE_PCT)
    hi = last_price * (1 + STRIKE_RANGE_PCT)
    chain = chain[(chain["strike_price"] >= lo) & (chain["strike_price"] <= hi)].copy()
    if len(chain) == 0:
        return []
    chain["dist"] = (chain["strike_price"] - last_price).abs()
    chain = chain.sort_values("dist").head(MAX_CONTRACTS_PER_STOCK)

    # 期权快照（最多 400/批）
    contract_codes = chain["code"].tolist()
    ret, snap = quote_ctx.get_market_snapshot(contract_codes)
    if ret != RET_OK:
        print(f"  [{code}] 期权快照失败: {snap}", file=sys.stderr)
        return []

    merged = chain.merge(
        snap[
            [
                "code",
                "last_price",
                "bid_price",
                "ask_price",
                "volume",
                "option_implied_volatility",
                "option_delta",
                "option_gamma",
                "option_theta",
                "option_vega",
                "option_open_interest",
            ]
        ],
        on="code",
        how="left",
    )

    items = []
    for _, r in merged.iterrows():
        oi = num(r["option_open_interest"])
        if oi is None or oi < MIN_OPEN_INTEREST:
            continue
        iv = num(r["option_implied_volatility"])
        if iv is None or iv == 0:
            continue
        items.append(
            {
                "code": r["code"],
                "type": r["option_type"],
                "strike": num(r["strike_price"]),
                "expiry": r["strike_time"],
                "dte": int(num(r.get("dist", 0)) or 0),  # placeholder, replaced below
                "last": num(r["last_price"]),
                "bid": num(r["bid_price"]),
                "ask": num(r["ask_price"]),
                "volume": num(r["volume"]),
                "oi": oi,
                "iv": iv / 100 if iv > 5 else iv,  # 富途返回的是百分数(70.5)，统一为小数
                "delta": num(r["option_delta"]),
                "gamma": num(r["option_gamma"]),
                "theta": num(r["option_theta"]),
                "vega": num(r["option_vega"]),
            }
        )
    # dte 用统一的过期天数
    if items:
        from datetime import date as _date

        try:
            exp_d = _date.fromisoformat(items[0]["expiry"])
            today = _date.today()
            dte = (exp_d - today).days
        except Exception:
            dte = None
        for it in items:
            it["dte"] = dte
    return items


# ===== 策略评分 =====


def score_directional(stock: dict, opts: list[dict]) -> list[dict]:
    """
    A. 方向性策略：基于盘前涨跌
      - pre_change_rate > 0.3% → 推 Long Call (Delta 0.30~0.45)
      - pre_change_rate < -0.3% → 推 Long Put (|Delta| 0.30~0.45)
    """
    pre = stock.get("pre_change_rate")
    if pre is None:
        return []
    out = []
    if pre > 0.3:
        target = "CALL"
    elif pre < -0.3:
        target = "PUT"
    else:
        return []

    for o in opts:
        if o["type"] != target:
            continue
        d = o.get("delta")
        if d is None:
            continue
        ad = abs(d)
        if not (0.25 <= ad <= 0.50):
            continue
        # 评分：更接近 0.35 delta 加分；流动性加分
        delta_score = 1 - abs(ad - 0.35) * 4  # 0.35→1.0
        liq_score = min(1.0, math.log10(max(o["oi"], 1)) / 4)  # OI=10000 → 1
        spread = (
            (o["ask"] - o["bid"]) / max(o["last"], 0.01)
            if o.get("ask") and o.get("bid") and o["last"]
            else 1
        )
        spread_score = max(0, 1 - spread * 5)
        magnitude = min(abs(pre) / 1.5, 1.0)  # 盘前波动越大越加分
        total = (delta_score * 0.3 + liq_score * 0.3 + spread_score * 0.2 + magnitude * 0.2) * 100
        out.append(
            {
                **o,
                "strategy": "Long Call" if target == "CALL" else "Long Put",
                "category": "directional",
                "score": round(total, 1),
                "rationale": (
                    f"盘前{'+' if pre>0 else ''}{pre:.2f}%，"
                    f"Delta {d:.2f}，OI {int(o['oi'])}"
                ),
                "summary": (
                    f"做{'多' if target=='CALL' else '空'} {stock['name']} "
                    f"${o['strike']:.0f} {target} | "
                    f"DTE {o['dte']}d | Δ{d:.2f} | "
                    f"权利金 ${o['last']:.2f}"
                ),
            }
        )
    out.sort(key=lambda x: x["score"], reverse=True)
    return out[:2]


def score_iv_hv(stock: dict, opts: list[dict]) -> list[dict]:
    """
    B. 卖方策略：基于 IV/HV
      - ATM IV / HV > 1.2 → 推 Bear Call Spread (看不涨) 或 Bull Put Spread (看不跌)
      - 优先选 |Delta| 0.20~0.30 的 OTM
    """
    hv = stock.get("hv")
    if not hv or hv <= 0:
        return []
    last = stock.get("last") or 0
    if not last:
        return []
    # ATM IV：取 strike 最接近 last_price 的合约的 IV 平均
    atm_opts = sorted(opts, key=lambda x: abs(x["strike"] - last))[:4]
    atm_ivs = [o["iv"] for o in atm_opts if o.get("iv")]
    if not atm_ivs:
        return []
    iv_atm = sum(atm_ivs) / len(atm_ivs)
    iv_hv_ratio = iv_atm / hv
    if iv_hv_ratio < 1.15:
        return []  # IV 不够贵，不值得卖

    direction = stock.get("pre_change_rate") or 0
    out = []

    # 倾向：盘前涨 → Bear Call Spread; 盘前跌 → Bull Put Spread; 平 → 都给
    plays = []
    if direction <= 0.5:
        plays.append("PUT")  # Bull Put Spread (sell put)
    if direction >= -0.5:
        plays.append("CALL")  # Bear Call Spread (sell call)

    for typ in plays:
        candidates = [o for o in opts if o["type"] == typ]
        for o in candidates:
            d = o.get("delta")
            if d is None:
                continue
            ad = abs(d)
            if not (0.18 <= ad <= 0.32):
                continue
            premium = o.get("last") or 0
            if premium <= 0.05:
                continue
            iv_score = min((iv_hv_ratio - 1) * 4, 1.0)  # 1.25→1.0
            delta_score = 1 - abs(ad - 0.25) * 8
            liq_score = min(1.0, math.log10(max(o["oi"], 1)) / 4)
            total = (iv_score * 0.5 + delta_score * 0.25 + liq_score * 0.25) * 100
            strat = "Bull Put Spread" if typ == "PUT" else "Bear Call Spread"
            out.append(
                {
                    **o,
                    "strategy": strat,
                    "category": "iv_hv",
                    "score": round(total, 1),
                    "iv_hv_ratio": round(iv_hv_ratio, 2),
                    "rationale": (
                        f"IV/HV={iv_hv_ratio:.2f}（IV {iv_atm*100:.0f}% vs HV {hv*100:.0f}%），"
                        f"Δ{d:.2f}，赚时间价值"
                    ),
                    "summary": (
                        f"卖出 {stock['name']} ${o['strike']:.0f} {typ} "
                        f"({strat}) | IV/HV {iv_hv_ratio:.2f} | "
                        f"权利金 ${premium:.2f}"
                    ),
                }
            )
    out.sort(key=lambda x: x["score"], reverse=True)
    return out[:2]


def score_income(stock: dict, opts: list[dict]) -> list[dict]:
    """
    D. 收益增强策略：Covered Call / Cash-Secured Put
      - Covered Call:   持仓增强，卖 OTM Call (Δ 0.20~0.35)
      - Cash-Secured Put: 想低价接货，卖 OTM Put (|Δ| 0.20~0.35)
      共同条件：年化收益率 ≥ 15%，OI 充足，价差合理
    收益率口径：年化收益 = (premium / strike) * (365 / DTE)
      - CC 用 strike 作分母（保守口径，等于"行权价被call走时锁定收益")
      - CSP 用 strike 作分母（等于"占用资金"基准）
    """
    out = []
    last = stock.get("last") or 0
    if not last:
        return []
    hv = stock.get("hv") or 0

    for o in opts:
        d = o.get("delta")
        if d is None:
            continue
        ad = abs(d)
        if not (0.18 <= ad <= 0.38):
            continue
        premium = o.get("last") or 0
        if premium <= 0.05:
            continue
        strike = o.get("strike") or 0
        dte = o.get("dte") or 0
        if not strike or not dte:
            continue

        # 仅考虑 OTM
        if o["type"] == "CALL" and strike <= last:
            continue
        if o["type"] == "PUT" and strike >= last:
            continue

        # 年化收益率
        annual_return = (premium / strike) * (365 / dte)
        if annual_return < 0.15:
            continue  # 年化 <15% 不值得占资金

        # 评分维度
        return_score = min(annual_return / 0.40, 1.0)  # 年化 40% 满分
        liq_score = min(1.0, math.log10(max(o["oi"], 1)) / 4)
        spread_pct = (
            (o["ask"] - o["bid"]) / max(premium, 0.01)
            if o.get("ask") and o.get("bid")
            else 1
        )
        spread_score = max(0, 1 - spread_pct * 4)
        # Δ 越小越安全（被指派概率小）
        safety_score = 1 - (ad - 0.18) / 0.20  # Δ 0.18→1.0, 0.38→0.0
        safety_score = max(0, min(1, safety_score))

        total = (
            return_score * 0.40
            + liq_score * 0.25
            + spread_score * 0.15
            + safety_score * 0.20
        ) * 100

        if o["type"] == "CALL":
            strat = "Covered Call"
            otm_pct = (strike / last - 1) * 100
            summary = (
                f"持有 {stock['name']} 卖 ${strike:.0f} CALL | "
                f"DTE {dte}d | OTM {otm_pct:.1f}% | "
                f"年化 {annual_return*100:.1f}% | 权利金 ${premium:.2f}"
            )
            rationale = (
                f"已持仓增强收益，OTM {otm_pct:.1f}%，Δ{d:.2f}（被call概率约{ad*100:.0f}%），"
                f"HV {hv*100:.0f}% 参考"
            )
        else:
            strat = "Cash-Secured Put"
            otm_pct = (1 - strike / last) * 100
            cash_needed = strike * 100
            summary = (
                f"低价接 {stock['name']} 卖 ${strike:.0f} PUT | "
                f"DTE {dte}d | OTM {otm_pct:.1f}% | "
                f"年化 {annual_return*100:.1f}% | 占资 ${cash_needed:,.0f}"
            )
            rationale = (
                f"愿意 ${strike:.0f} 接货，OTM {otm_pct:.1f}%，|Δ|{ad:.2f}（被指派概率约{ad*100:.0f}%），"
                f"权利金 ${premium:.2f}"
            )

        out.append(
            {
                **o,
                "strategy": strat,
                "category": "income",
                "score": round(total, 1),
                "annual_return": round(annual_return, 4),
                "rationale": rationale,
                "summary": summary,
            }
        )
    out.sort(key=lambda x: x["score"], reverse=True)
    return out[:2]


def score_composite(stock: dict, opts: list[dict]) -> list[dict]:
    """
    C. 综合策略：流动性 + 希腊字母 + 概率
      综合考虑 OI、Volume、Spread、|Delta|、Theta/Premium 比，选出最值得交易的合约
    """
    out = []
    for o in opts:
        d = o.get("delta")
        theta = o.get("theta") or 0
        if d is None:
            continue
        ad = abs(d)
        if not (0.20 <= ad <= 0.55):
            continue
        if not o.get("last") or o["last"] <= 0.1:
            continue

        # 流动性：OI、Volume、Spread
        liq_score = min(1.0, math.log10(max(o["oi"], 1)) / 4)
        vol_score = min(1.0, math.log10(max(o.get("volume") or 1, 1)) / 3.5)
        spread_pct = (
            (o["ask"] - o["bid"]) / max(o["last"], 0.01)
            if o.get("ask") and o.get("bid")
            else 1
        )
        spread_score = max(0, 1 - spread_pct * 4)

        # Theta/权利金：每天衰减占权利金比
        theta_efficiency = min(abs(theta) / max(o["last"], 0.01) * 100, 1)

        total = (
            liq_score * 0.30
            + vol_score * 0.20
            + spread_score * 0.25
            + theta_efficiency * 0.25
        ) * 100
        out.append(
            {
                **o,
                "strategy": "Long " + ("Call" if o["type"] == "CALL" else "Put"),
                "category": "composite",
                "score": round(total, 1),
                "rationale": (
                    f"OI {int(o['oi'])}，量 {int(o.get('volume') or 0)}，"
                    f"价差 {spread_pct*100:.1f}%，Δ{d:.2f}"
                ),
                "summary": (
                    f"{stock['name']} ${o['strike']:.0f} {o['type']} | "
                    f"DTE {o['dte']}d | Δ{d:.2f} Θ{theta:.3f} | "
                    f"权利金 ${o['last']:.2f}"
                ),
            }
        )
    out.sort(key=lambda x: x["score"], reverse=True)
    return out[:2]


# ===== 主入口 =====


def main():
    print("[1/3] 连接 OpenD...")
    quote_ctx = OpenQuoteContext(host="127.0.0.1", port=11111)
    try:
        print("[2/3] 拉取 MAG7 正股快照 + HV...")
        underlying = fetch_underlying(quote_ctx)
        print(f"      获得 {len(underlying)} 只股票数据")

        print("[3/3] 拉取期权链 + 评分...")
        all_picks = []
        for code, _name in MAG7:
            stock = underlying.get(code)
            if not stock or not stock.get("last"):
                continue
            print(f"  -> {code} ({stock['name']})")
            opts = fetch_option_chain_one(quote_ctx, code, stock["last"])
            print(f"     有效合约 {len(opts)} 个")
            time.sleep(0.5)  # 限频保护

            picks_a = score_directional(stock, opts)
            picks_b = score_iv_hv(stock, opts)
            picks_c = score_composite(stock, opts)
            picks_d = score_income(stock, opts)
            for p in picks_a + picks_b + picks_c + picks_d:
                p["underlying"] = {
                    "code": stock["code"],
                    "name": stock["name"],
                    "last": stock["last"],
                    "pre_change_rate": stock["pre_change_rate"],
                    "hv": stock["hv"],
                }
                all_picks.append(p)

        # 全局再排序
        all_picks.sort(key=lambda x: x["score"], reverse=True)

        out = {
            "generated_at": datetime.now(timezone.utc).astimezone().strftime(
                "%Y-%m-%d %H:%M:%S %Z"
            ),
            "underlying": list(underlying.values()),
            "picks": all_picks,
            "stats": {
                "total": len(all_picks),
                "directional": sum(1 for p in all_picks if p["category"] == "directional"),
                "iv_hv": sum(1 for p in all_picks if p["category"] == "iv_hv"),
                "composite": sum(1 for p in all_picks if p["category"] == "composite"),
                "income": sum(1 for p in all_picks if p["category"] == "income"),
            },
        }
        with open("data.json", "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2, default=str)
        print(f"\n完成：共 {len(all_picks)} 个策略机会写入 data.json")
        print(f"  方向性 {out['stats']['directional']}，"
              f"IV/HV {out['stats']['iv_hv']}，"
              f"综合 {out['stats']['composite']}，"
              f"收益增强 {out['stats']['income']}")
    finally:
        quote_ctx.close()


if __name__ == "__main__":
    main()
