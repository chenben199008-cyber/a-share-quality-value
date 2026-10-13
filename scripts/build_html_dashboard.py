#!/usr/bin/env python3
"""Create a concise, standalone HTML valuation dashboard with inline SVG charts."""

from __future__ import annotations

import io
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


BG, CARD, GRID = "#0b1220", "#121b2d", "#29344b"
TEXT, MUTED = "#edf2f7", "#8e9bb2"
GREEN, BLUE, AMBER, RED = "#24a47a", "#38bdf8", "#c8942e", "#ef5350"


def _svg(fig) -> str:
    out = io.StringIO()
    fig.savefig(out, format="svg", transparent=True, bbox_inches="tight")
    plt.close(fig)
    return out.getvalue()[out.getvalue().find("<svg"):]


def _style(ax):
    ax.set_facecolor(CARD)
    ax.tick_params(colors=MUTED, labelsize=8)
    for spine in ax.spines.values():
        spine.set_color(GRID)
    ax.grid(True, color=GRID, alpha=.5, ls=":", lw=.7)
    ax.set_axisbelow(True)
    ax.xaxis.label.set_color(MUTED); ax.yaxis.label.set_color(MUTED)


def build_html(output_dir: Path, safe_code: str, name: str, code: str) -> Path:
    output_dir = Path(output_dir)
    df = pd.read_csv(output_dir / f"{safe_code}_pe_timeseries.csv", parse_dates=["date"])
    events = pd.read_csv(output_dir / f"{safe_code}_undervaluation_events.csv")
    metrics = json.loads((output_dir / f"{safe_code}_valuation_metrics.json").read_text(encoding="utf-8"))
    low_all = events[events["type"] == "低估"].copy()
    extreme_all = events[events["type"] == "极端低估"].copy()
    low = low_all[~low_all["ongoing"].astype(bool)].copy()

    # Histogram: actual trading-day counts; fitted curve is scaled to the same unit.
    values = df["pe"].tail(metrics["window"]).dropna()
    lo, hi = float(values.quantile(.005)), float(values.quantile(.995))
    clipped = values.clip(lo, hi)
    fig, ax = plt.subplots(figsize=(8.2, 3.0), facecolor="none")
    _style(ax)
    mu, sigma = metrics["mu"], metrics["sigma"]
    low2, low1 = metrics["extreme_low_threshold"], metrics["low_threshold"]
    high1, high2 = mu + sigma, mu + 2*sigma
    chart_lo, chart_hi = max(0, min(lo, low2)), max(hi, high2)
    ax.axvspan(chart_lo, low2, color=BLUE, alpha=.22)
    ax.axvspan(low2, low1, color=GREEN, alpha=.23)
    ax.axvspan(low1, high1, color="#65748d", alpha=.10)
    ax.axvspan(high1, high2, color=AMBER, alpha=.20)
    ax.axvspan(high2, chart_hi, color=RED, alpha=.18)
    _, bins, _ = ax.hist(clipped, bins=24, color="#455a78", edgecolor=CARD, alpha=.82)
    x = np.linspace(lo, hi, 300)
    expected = np.exp(-.5*((x-mu)/sigma)**2)/(sigma*np.sqrt(2*np.pi))*len(clipped)*np.mean(np.diff(bins))
    ax.plot(x, expected, color=RED, lw=2, label="正态拟合频次")
    for value, label, color in [(low2, "极端低估", BLUE), (low1, "低估", GREEN),
                                (mu, "均线 μ", "#64748b"), (high1, "高估", AMBER),
                                (high2, "极端高估", RED)]:
        ax.axvline(value, color=color, lw=1, ls="--")
        ax.text(value, ax.get_ylim()[1]*.98, label, rotation=90, va="top", ha="right",
                color=color, fontsize=7)
    current_display = min(metrics["current_pe"], chart_hi * .995)
    current_line = ax.axvline(current_display, color="#ffffff", lw=2.8, ls="-")
    current_line.set_gid("current-pe-solid-white")
    current_label = f'当前 {metrics["current_pe"]:.1f}×' + (" → 超出图示" if metrics["current_pe"] > chart_hi else "")
    ax.text(current_display, ax.get_ylim()[1]*.88, current_label, color="#ffffff", fontsize=9,
            weight="bold", ha="right" if metrics["current_pe"] > chart_hi else "left")
    ax.set(xlabel="扣非PE（倍）", ylabel="出现频次（交易日）", xlim=(chart_lo, chart_hi))
    hist_svg = _svg(fig)

    # Timeline: focus on the latest five years so recent changes remain readable.
    trend_start = df["date"].max() - pd.DateOffset(years=5)
    trend = df.loc[df["date"] >= trend_start].copy()
    fig, ax = plt.subplots(figsize=(13.2, 3.25), facecolor="none")
    _style(ax)
    ax.plot(trend["date"], trend["pe"], color="#e6edf7", lw=1.0, label="扣非PE")
    ax.plot(trend["date"], trend["mu"], color="#cbd5e1", lw=1.1, ls="--", label="滚动均线 μ")
    ax.plot(trend["date"], trend["minus_1sigma"], color=GREEN, lw=1.2, ls="--", label="低估线 μ−1σ")
    ax.plot(trend["date"], trend["minus_2sigma"], color=BLUE, lw=1.1, ls="--", label="极端线 μ−2σ")
    for row in low_all.itertuples():
        if pd.Timestamp(row.end) >= trend_start:
            ax.axvspan(max(pd.Timestamp(row.start), trend_start), pd.Timestamp(row.end), color=GREEN, alpha=.13, lw=0)
    for row in extreme_all.itertuples():
        if pd.Timestamp(row.end) >= trend_start:
            ax.axvspan(max(pd.Timestamp(row.start), trend_start), pd.Timestamp(row.end), color=BLUE, alpha=.22, lw=0)
    shown_labels = 0
    for row in low_all.itertuples():
        if int(row.trading_days) <= 1 or pd.Timestamp(row.end) < trend_start: continue
        start = max(pd.Timestamp(row.start), trend_start); end = pd.Timestamp(row.end)
        midpoint = start + (end - start) / 2
        suffix = "·进行中" if bool(row.ongoing) else ""
        ax.text(midpoint, .96 - (shown_labels % 2) * .075, f"{int(row.trading_days)}天{suffix}",
                transform=ax.get_xaxis_transform(), ha="center", va="top", color="#a7f3d0",
                fontsize=7, clip_on=True)
        shown_labels += 1
    last = df.iloc[-1]
    ax.scatter(last["date"], last["pe"], color=RED, edgecolor="white", s=38, zorder=5)
    ax.set_ylabel("扣非PE（倍)")
    leg = ax.legend(ncol=4, fontsize=8, loc="upper left", frameon=False)
    for t in leg.get_texts(): t.set_color(TEXT)
    trend_svg = _svg(fig)

    # Pareto: latest completed event is blue; red line has a clearly named percentage axis.
    ranked = low.sort_values("trading_days", ascending=False).reset_index(drop=True)
    latest_start = low.loc[pd.to_datetime(low["end"]).idxmax(), "start"] if not low.empty else None
    shown = ranked.head(12).copy()
    remainder_count = max(0, len(ranked) - len(shown))
    remainder_days = int(ranked.iloc[len(shown):]["trading_days"].sum()) if remainder_count else 0
    vals = shown["trading_days"].to_numpy()
    labels = [str(v)[:7] for v in shown["start"]]
    if remainder_count:
        vals = np.append(vals, remainder_days)
        labels.append(f"其余{remainder_count}次")
    total = ranked["trading_days"].sum()
    cum = np.cumsum(vals)/total if total else np.array([])
    key_count = int(np.argmax(ranked["trading_days"].cumsum().to_numpy()/total >= .8) + 1) if total else 0
    colors = [BLUE if row.start == latest_start else GREEN if i < key_count else "#455a78"
              for i, row in enumerate(shown.itertuples())]
    if remainder_count:
        colors.append("#455a78")
    fig, ax = plt.subplots(figsize=(8.2, 3.0), facecolor="none")
    _style(ax)
    y = np.arange(len(vals))
    ax.barh(y, vals, color=colors, height=.65)
    ax.set_yticks(y, labels); ax.invert_yaxis(); ax.set_xlabel("持续交易日")
    for i, v in enumerate(vals):
        suffix = "  最新" if i < len(shown) and shown.iloc[i]["start"] == latest_start else ""
        ax.text(v+1, i, f"{v}{suffix}", va="center", fontsize=8, color=BLUE if suffix else TEXT, weight="bold")
    ax2 = ax.twiny(); ax2.set_xlim(0, 1); ax2.plot(cum, y, color=RED, marker="o", ms=3, lw=1.5)
    ax2.axvline(.8, color=AMBER, ls="--", lw=1)
    ax2.set_xticks([0, .2, .4, .6, .8, 1], ["0%", "20%", "40%", "60%", "80%", "100%"])
    ax2.tick_params(colors=RED, labelsize=8); ax2.set_xlabel("红线：累计低估时长占比", color=RED, fontsize=8)
    for spine in ax2.spines.values(): spine.set_color(GRID)
    pareto_svg = _svg(fig)

    conflict = metrics.get("signal_conflict", False)
    unreliable = metrics.get("pe_model_unreliable", False)
    verdict = "扣非利润接近零，当前PE失真，暂不适合用PE判断估值" if unreliable else ("历史偏低，尚未跌破3年正态低估线" if conflict else metrics["normal_signal"])
    state_value = "PE失真" if unreliable else ("历史偏低" if conflict else metrics["normal_signal"])
    state_hint = metrics.get("model_warning") if unreliable else f'正态：{metrics["normal_signal"]}｜分位：{metrics["percentile_signal"]}'
    mean_relation = "高于" if metrics["current_pe"] >= metrics["mu"] else "低于"
    if metrics["normal_signal"] == "极端高估":
        reference_label, reference_value = "极端高估线", metrics["mu"] + 2*metrics["sigma"]
    elif metrics["normal_signal"] == "高估":
        reference_label, reference_value = "高估线", metrics["mu"] + metrics["sigma"]
    elif metrics["normal_signal"] == "极端低估":
        reference_label, reference_value = "极端低估线", metrics["extreme_low_threshold"]
    else:
        reference_label, reference_value = "低估线", metrics["low_threshold"]
    position_text = (f'当前扣非PE为 {metrics["current_pe"]:.1f}倍，远离常态区间，主要由扣非利润接近零造成，均值和标准差不再具有稳定解释。'
                     if unreliable else f'当前扣非PE为 {metrics["current_pe"]:.1f}倍，{mean_relation}3年均线 {metrics["mu"]:.1f}倍；{reference_label}为 {reference_value:.1f}倍，因此正态规则判断为“{metrics["normal_signal"]}”。')
    conclusion_text = ("当前应先观察扣非利润能否恢复正常，再使用PE比较；可暂用PB、ROE、经营现金流和利润率辅助判断。"
                       if unreliable else ("当前处于历史偏低位置，但还没有进入3年正态低估区。两个信号不同，主要因为PE分布右偏，少数高PE阶段抬高了均值。"
                       if conflict else f'正态规则与历史分位均指向“{metrics["normal_signal"]}”。这是相对历史估值位置，不代表股价会立即反向运行。'))
    latest = low.loc[pd.to_datetime(low["end"]).idxmax()] if not low.empty else None
    latest_text = "无" if latest is None else f'{str(latest["start"])[:10]} 至 {str(latest["end"])[:10]}，{int(latest["trading_days"])}个交易日'
    html = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{name} 扣非PE估值</title><style>
*{{box-sizing:border-box}}html{{background:{BG}}}body{{margin:0;background:{BG};color:{TEXT};font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif;-webkit-font-smoothing:antialiased}}
.page{{max-width:1180px;margin:auto;padding:28px 24px 72px}}.hero{{position:relative;min-height:350px;padding:54px 58px;border-radius:28px;color:#f5f5f7;background:radial-gradient(circle at 78% 24%,#183d68 0,transparent 34%),linear-gradient(135deg,#090d14 0%,#111827 58%,#0b1220 100%);display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:42px;overflow:hidden;box-shadow:0 22px 60px rgba(0,0,0,.22)}}.hero:after{{content:"";position:absolute;width:300px;height:300px;border:1px solid rgba(255,255,255,.08);border-radius:50%;right:-110px;bottom:-170px}}.eyebrow{{color:#a1a1a6;font-size:15px;font-weight:650}}h1{{font-size:clamp(42px,6vw,68px);line-height:1;letter-spacing:-.048em;margin:14px 0 18px}}h1 small{{display:block;font-size:.27em;letter-spacing:.03em;color:#a1a1a6;margin-top:14px}}.hero-badge{{display:inline-flex;padding:8px 15px;border-radius:999px;background:#14866d;color:#fff;font-weight:700}}.hero-value{{position:relative;z-index:1;text-align:right;justify-self:end;transform:translateX(-58px)}}.hero-number{{font-size:clamp(88px,11vw,136px);line-height:.82;letter-spacing:-.06em;font-weight:730}}.hero-unit{{color:#a1a1a6;font-size:13px;margin-top:14px}}.hero-meta{{grid-column:1/-1;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));margin-top:8px;padding-top:24px;border-top:1px solid rgba(255,255,255,.12)}}.hero-meta div{{display:flex;flex-direction:column;gap:7px;padding:0 28px;border-left:1px solid rgba(255,255,255,.10)}}.hero-meta div:first-child{{padding-left:0;border-left:0}}.hero-meta div:last-child{{padding-right:0}}.hero-meta span{{color:#8e8e93;font-size:12px}}.hero-meta strong{{color:#f5f5f7;font-size:14px}}
.verdict{{margin:22px 0 15px;padding:20px 24px;background:linear-gradient(90deg,#17382f,{CARD});border-left:5px solid {GREEN};border-radius:18px;font-size:20px;font-weight:700;color:{TEXT}}}
.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:18px}}.card,.panel{{background:{CARD};border:1px solid {GRID};border-radius:24px;box-shadow:0 12px 38px rgba(0,0,0,.18)}}
.card{{padding:19px 20px}}.label{{color:{MUTED};font-size:12px}}.value{{font-size:25px;font-weight:750;margin-top:6px}}.hint{{color:{MUTED};font-size:11px;margin-top:4px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}.panel{{padding:24px;overflow:hidden}}.wide{{grid-column:1/-1}}h2{{font-size:21px;letter-spacing:-.02em;margin:0 0 5px}}.desc{{color:{MUTED};font-size:12px;margin-bottom:10px;line-height:1.6}}svg{{width:100%;height:auto;display:block}}
.read{{margin:18px 0;background:{CARD};border:1px solid {GRID};border-radius:24px;padding:24px 28px;box-shadow:0 12px 38px rgba(0,0,0,.18)}}.read h2{{margin-bottom:12px}}.read ul{{margin:0;padding-left:20px}}.read li{{margin:9px 0;line-height:1.7;color:#d9e2ef}}.term{{color:{BLUE};font-weight:700}}
.zones{{display:flex;flex-wrap:wrap;gap:8px;margin:7px 0 3px}}.zone{{padding:5px 10px;border-radius:999px;font-size:11px;font-weight:700;color:#fff}}.z1{{background:#2f6fbb}}.z2{{background:#24a47a}}.z3{{background:#64748b}}.z4{{background:#c8942e}}.z5{{background:#b9434b}}
.foot{{color:{MUTED};font-size:11px;text-align:center;padding:16px}}@media(max-width:850px){{.cards,.grid{{grid-template-columns:1fr 1fr}}.wide{{grid-column:1/-1}}}}@media(max-width:620px){{.hero{{grid-template-columns:1fr;padding:40px 30px}}.hero-value{{justify-self:start;text-align:left;transform:none}}.hero-meta{{grid-template-columns:repeat(4,minmax(150px,1fr));overflow-x:auto}}.cards,.grid{{grid-template-columns:1fr}}}}
</style></head><body><main class="page"><section class="hero"><div><div class="eyebrow">扣非PE历史估值模型</div><h1>{name}<small>{code}</small></h1><span class="hero-badge">{state_value}</span></div><div class="hero-value"><div class="hero-number">{metrics["current_pe"]:.2f}</div><div class="hero-unit">当前扣非PE · 倍</div></div><div class="hero-meta"><div><span>数据源</span><strong>iFinD</strong></div><div><span>行情截止日</span><strong>{metrics["as_of"]}</strong></div><div><span>滚动窗口</span><strong>{metrics["window"]}个交易日</strong></div><div><span>历史分位</span><strong>{metrics["historical_percentile"]:.1%}</strong></div></div></section>
<div class="verdict">{verdict}</div><section class="cards">
<div class="card"><div class="label">当前扣非PE</div><div class="value">{metrics["current_pe"]:.1f}×</div><div class="hint">{reference_label} {reference_value:.1f}×</div></div>
<div class="card"><div class="label">3年历史分位</div><div class="value">{metrics["historical_percentile"]:.1%}</div><div class="hint">低于约八成历史交易日</div></div>
<div class="card"><div class="label">综合判断</div><div class="value">{state_value}</div><div class="hint">{state_hint}</div></div>
<div class="card"><div class="label">最近一次低估</div><div class="value">{int(latest["trading_days"]) if latest is not None else 0}天</div><div class="hint">{latest_text}</div></div></section>
<section class="grid"><article class="panel"><h2>现在贵不贵</h2><div class="desc">柱形是实际出现天数，白色实线是当前PE</div><div class="zones"><span class="zone z1">极端低估</span><span class="zone z2">低估</span><span class="zone z3">合理</span><span class="zone z4">高估</span><span class="zone z5">极端高估</span></div><div data-current-pe-line="solid-white">{hist_svg}</div></article>
<article class="panel"><h2>历史低估通常多久</h2><div class="desc">蓝柱为最新一次；红线是累计低估时长占比</div>{pareto_svg}</article>
<article class="panel wide"><h2>当前处在什么位置</h2><div class="desc">近5年走势；灰色虚线是最近756个有效交易日扣非PE的动态平均值，绿色阴影为低估，蓝色阴影为极端低估，红点为当前</div><div data-zone-colors="low-green extreme-low-blue" data-duration-label-format="days-only">{trend_svg}</div></article></section>
<section class="read"><h2>怎么看这份结果</h2><ul>
<li><span class="term">位置：</span>{position_text}</li>
<li><span class="term">分位：</span>3年历史分位为 {metrics["historical_percentile"]:.1%}，意思是在最近 {metrics["window"]} 个交易日中，约 {metrics["historical_percentile"]:.1%} 的PE不高于当前值，约 {1-metrics["historical_percentile"]:.1%} 的PE高于当前值。分位法因此判断为“{metrics["percentile_signal"]}”。</li>
<li><span class="term">滚动均线：</span>每个交易日只使用截至当天最近 {metrics["window"]} 个有效交易日的扣非PE求平均。窗口每天向前移动，所以均线会随历史高估和低估数据进入或退出窗口而变化；它表示动态历史中枢，不是股价技术分析中的短期均线，也不是预测线。</li>
<li><span class="term">结论：</span>{conclusion_text}</li>
</ul></section>
<div class="foot">估值信号不等同于价格预测；扣非利润为负时不按低估处理。</div></main></body></html>'''
    path = output_dir / f"{safe_code}_valuation_dashboard.html"
    path.write_text(html, encoding="utf-8")
    return path
