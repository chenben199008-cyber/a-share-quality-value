#!/usr/bin/env python3
"""Build a one-page deducted-PE valuation dashboard from an iFinD export."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import font_manager


SIGNAL_ORDER = ["极端低估", "低估", "合理", "高估", "极端高估"]


def choose_chinese_font() -> None:
    candidates = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Arial Unicode MS"]
    installed = {f.name for f in font_manager.fontManager.ttflist}
    for name in candidates:
        if name in installed:
            plt.rcParams["font.sans-serif"] = [name]
            break
    plt.rcParams["axes.unicode_minus"] = False


def classify(pe: pd.Series, mu: pd.Series, sigma: pd.Series, loss: pd.Series) -> pd.Series:
    out = pd.Series("数据不足", index=pe.index, dtype="object")
    out.loc[loss] = "亏损区"
    valid = pe.notna() & mu.notna() & sigma.notna() & (sigma > 0) & ~loss
    out.loc[valid & (pe < mu - 2 * sigma)] = "极端低估"
    out.loc[valid & (pe >= mu - 2 * sigma) & (pe < mu - sigma)] = "低估"
    out.loc[valid & (pe >= mu - sigma) & (pe <= mu + sigma)] = "合理"
    out.loc[valid & (pe > mu + sigma) & (pe <= mu + 2 * sigma)] = "高估"
    out.loc[valid & (pe > mu + 2 * sigma)] = "极端高估"
    return out


def pct_signal(p: float) -> str:
    if pd.isna(p): return "数据不足"
    if p <= .05: return "极端低估"
    if p <= .20: return "低估"
    if p < .80: return "合理"
    if p < .95: return "高估"
    return "极端高估"


def rolling_percentile(s: pd.Series, window: int, min_periods: int) -> pd.Series:
    return s.rolling(window, min_periods=min_periods).apply(
        lambda x: float(np.mean(x[np.isfinite(x)] <= x[np.isfinite(x)][-1])), raw=True
    )


def event_table(df: pd.DataFrame, mask: pd.Series, kind: str) -> pd.DataFrame:
    breaks = (~mask).cumsum()
    rows = []
    for _, g in df.loc[mask].groupby(breaks[mask]):
        start, end = g["date"].iloc[0], g["date"].iloc[-1]
        rows.append({
            "type": kind, "start": start.date().isoformat(), "end": end.date().isoformat(),
            "trading_days": int(len(g)), "calendar_days": int((end - start).days + 1),
            "min_pe": float(g["pe"].min()), "min_zscore": float(g["zscore"].min()),
            "ongoing": bool(g.index[-1] == df.index[-1]),
        })
    return pd.DataFrame(rows)


def shade_events(ax, events: pd.DataFrame, color: str, alpha: float) -> None:
    if events.empty: return
    for row in events.itertuples():
        ax.axvspan(pd.Timestamp(row.start), pd.Timestamp(row.end), color=color, alpha=alpha, lw=0)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("input", type=Path)
    p.add_argument("--output-dir", type=Path, default=Path("valuation_output"))
    p.add_argument("--window", type=int, default=756)
    p.add_argument("--min-periods", type=int, default=252)
    p.add_argument("--strict-prior", action="store_true", help="shift rolling thresholds by one day")
    p.add_argument("--code")
    p.add_argument("--name")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    choose_chinese_font()
    raw = pd.read_csv(args.input)
    if "date" not in raw: raise ValueError("缺少 date 列")
    df = raw.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)
    if {"market_cap", "deducted_net_profit_ttm"}.issubset(df.columns):
        cap = pd.to_numeric(df["market_cap"], errors="coerce")
        profit = pd.to_numeric(df["deducted_net_profit_ttm"], errors="coerce")
        df["loss"] = profit <= 0
        df["pe"] = (cap / profit).where(profit > 0)
    elif "deducted_pe" in df:
        direct = pd.to_numeric(df["deducted_pe"], errors="coerce")
        df["loss"] = direct <= 0
        df["pe"] = direct.where(direct > 0)
    else:
        raise ValueError("需要 market_cap + deducted_net_profit_ttm，或 deducted_pe")
    df["pe"] = df["pe"].replace([np.inf, -np.inf], np.nan)
    roll = df["pe"].rolling(args.window, min_periods=args.min_periods)
    mu, sigma = roll.mean(), roll.std(ddof=1)
    percentile = rolling_percentile(df["pe"], args.window, args.min_periods)
    if args.strict_prior:
        mu, sigma, percentile = mu.shift(1), sigma.shift(1), percentile.shift(1)
    df["mu"], df["sigma"], df["percentile"] = mu, sigma, percentile
    for n, k in [("minus_2sigma", -2), ("minus_1sigma", -1), ("plus_1sigma", 1), ("plus_2sigma", 2)]:
        df[n] = mu + k * sigma
    df["zscore"] = (df["pe"] - mu) / sigma
    df["signal"] = classify(df["pe"], mu, sigma, df["loss"])
    df["percentile_signal"] = df["percentile"].map(pct_signal)
    low_mask = (df["pe"] < df["minus_1sigma"]) & df["pe"].notna() & df["minus_1sigma"].notna()
    extreme_mask = (df["pe"] < df["minus_2sigma"]) & df["pe"].notna() & df["minus_2sigma"].notna()
    low_events = event_table(df, low_mask, "低估")
    extreme_events = event_table(df, extreme_mask, "极端低估")
    events = pd.concat([low_events, extreme_events], ignore_index=True)

    last = df.iloc[-1]
    completed = low_events.loc[~low_events.get("ongoing", pd.Series(dtype=bool))] if not low_events.empty else low_events
    ongoing = low_events.loc[low_events.get("ongoing", pd.Series(dtype=bool))] if not low_events.empty else low_events
    durations = completed["trading_days"] if not completed.empty else pd.Series(dtype=float)
    current_days = int(ongoing["trading_days"].iloc[0]) if not ongoing.empty else 0
    current_window = df["pe"].iloc[-args.window:].dropna()
    sensitivity = {}
    for sensitivity_window in (252, 504, 756, 1260):
        sample = df["pe"].iloc[-sensitivity_window:].dropna()
        if len(sample) < min(args.min_periods, sensitivity_window):
            continue
        sample_mu, sample_sigma = sample.mean(), sample.std(ddof=1)
        sensitivity[str(sensitivity_window)] = {
            "observations": int(len(sample)), "mu": float(sample_mu), "sigma": float(sample_sigma),
            "zscore": None if sample_sigma == 0 else float((last["pe"] - sample_mu) / sample_sigma),
            "percentile": float((sample <= last["pe"]).mean()),
        }
    signal_conflict = (
        str(last["signal"]) not in ("数据不足", "亏损区")
        and str(last["percentile_signal"]) not in ("数据不足", "亏损区")
        and str(last["signal"]) != str(last["percentile_signal"])
    )
    current_median = float(current_window.median()) if not current_window.empty else np.nan
    distribution_skewness = float(current_window.skew()) if not current_window.empty else np.nan
    pe_model_unreliable = bool(
        pd.notna(last["pe"]) and pd.notna(current_median) and current_median > 0
        and (last["pe"] > 10 * current_median or abs(distribution_skewness) > 3
             or (pd.notna(last["minus_1sigma"]) and last["minus_1sigma"] <= 0))
    )
    metrics = {
        "as_of": last["date"].date().isoformat(), "current_pe": None if pd.isna(last["pe"]) else float(last["pe"]),
        "mu": None if pd.isna(last["mu"]) else float(last["mu"]), "sigma": None if pd.isna(last["sigma"]) else float(last["sigma"]),
        "low_threshold": None if pd.isna(last["minus_1sigma"]) else float(last["minus_1sigma"]),
        "extreme_low_threshold": None if pd.isna(last["minus_2sigma"]) else float(last["minus_2sigma"]),
        "historical_percentile": None if pd.isna(last["percentile"]) else float(last["percentile"]),
        "normal_signal": str(last["signal"]), "percentile_signal": str(last["percentile_signal"]),
        "signal_conflict": bool(signal_conflict),
        "current_zscore": None if pd.isna(last["zscore"]) else float(last["zscore"]),
        "distribution_skewness": None if current_window.empty else distribution_skewness,
        "distribution_median": None if current_window.empty else current_median,
        "pe_model_unreliable": pe_model_unreliable,
        "model_warning": "扣非利润接近零或PE分布极端偏斜，PE估值模型暂时失真" if pe_model_unreliable else None,
        "q10": None if current_window.empty else float(current_window.quantile(.10)),
        "q20": None if current_window.empty else float(current_window.quantile(.20)),
        "window_sensitivity": sensitivity,
        "completed_low_events": int(len(completed)), "current_low_days": current_days,
        "mean_duration": None if durations.empty else float(durations.mean()),
        "median_duration": None if durations.empty else float(durations.median()),
        "p75_duration": None if durations.empty else float(durations.quantile(.75)),
        "window": args.window, "min_periods": args.min_periods, "strict_prior": args.strict_prior,
    }

    code = args.code or (str(df["code"].dropna().iloc[-1]) if "code" in df and df["code"].notna().any() else "security")
    name = args.name or (str(df["name"].dropna().iloc[-1]) if "name" in df and df["name"].notna().any() else code)
    safe_code = code.replace(".", "_").replace("/", "_")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Dark, card-based dashboard inspired by institutional research terminals.
    bg, card, grid = "#0b1220", "#121b2d", "#29344b"
    text_main, text_muted = "#edf2f7", "#8e9bb2"
    blue, green, amber, red = "#2f6fbb", "#24a47a", "#c8942e", "#ef5350"
    fig = plt.figure(figsize=(16, 12), constrained_layout=True, facecolor=bg)
    gs = fig.add_gridspec(3, 12, height_ratios=[1.02, 1.05, 1.12])
    ax_hist = fig.add_subplot(gs[0, :8])
    ax_info = fig.add_subplot(gs[0, 8:])
    ax_ts = fig.add_subplot(gs[1, :])
    ax_par = fig.add_subplot(gs[2, :])

    def style_card(ax, grid_axis="both"):
        ax.set_facecolor(card)
        for spine in ax.spines.values():
            spine.set_color(grid)
        ax.tick_params(colors=text_muted, labelsize=9)
        ax.xaxis.label.set_color(text_muted)
        ax.yaxis.label.set_color(text_muted)
        ax.grid(True, axis=grid_axis, color=grid, alpha=.55, ls=":", lw=.8)
        ax.set_axisbelow(True)

    for axis in (ax_hist, ax_ts, ax_par):
        style_card(axis)

    def panel_title(ax, title, subtitle):
        ax.set_title(title, loc="left", color=text_main, fontsize=15, weight="bold", pad=26)
        ax.text(0, 1.015, subtitle, transform=ax.transAxes, color=text_muted,
                fontsize=9, va="bottom")

    window_values = current_window
    if not window_values.empty:
        hist_lo = max(0, float(window_values.quantile(.005)))
        hist_hi = float(max(window_values.quantile(.995), last["pe"] if pd.notna(last["pe"]) else 0))
        ax_hist.set_xlim(hist_lo, hist_hi * 1.04)
        clipped_values = window_values.clip(hist_lo, hist_hi)
        _, hist_bins, _ = ax_hist.hist(clipped_values, bins=28, density=False,
                                       alpha=.75, color="#455a78", edgecolor=card,
                                       label="扣非PE出现频次")
        if pd.notna(last["mu"]) and pd.notna(last["sigma"]) and last["sigma"] > 0:
            x = np.linspace(hist_lo, hist_hi, 400)
            density = np.exp(-.5 * ((x-last["mu"])/last["sigma"])**2) / (last["sigma"] * math.sqrt(2*math.pi))
            bin_width = float(np.mean(np.diff(hist_bins)))
            expected_frequency = density * len(clipped_values) * bin_width
            ax_hist.plot(x, expected_frequency, color=red, lw=2.2, label="正态拟合频次")
            bounds = [last["minus_2sigma"], last["minus_1sigma"], last["plus_1sigma"], last["plus_2sigma"]]
            ax_hist.axvspan(hist_lo, bounds[0], color=blue, alpha=.18)
            ax_hist.axvspan(bounds[0], bounds[1], color=green, alpha=.20)
            ax_hist.axvspan(bounds[2], bounds[3], color=amber, alpha=.18)
            ax_hist.axvspan(bounds[3], hist_hi * 1.04, color=red, alpha=.16)
            line_specs = [(last["mu"], "μ", text_muted), (bounds[0], "μ-2σ", blue),
                          (bounds[1], "μ-1σ", green), (bounds[2], "μ+1σ", amber),
                          (bounds[3], "μ+2σ", red)]
            for v, label, color in line_specs:
                ax_hist.axvline(v, color=color, ls="--", lw=1.05, alpha=.95)
                if hist_lo <= v <= hist_hi * 1.04:
                    ax_hist.text(v, ax_hist.get_ylim()[1]*.98, label, color=color,
                                 rotation=90, va="top", ha="right", fontsize=8)
        if pd.notna(last["pe"]):
            ax_hist.axvline(last["pe"], color="#ffffff", lw=2.6, label="当前PE")
            ax_hist.annotate(f'当前 {last["pe"]:.2f}×', xy=(last["pe"], ax_hist.get_ylim()[1]*.68),
                             xytext=(10, 8), textcoords="offset points", color="#ffffff",
                             fontsize=9, weight="bold",
                             bbox=dict(boxstyle="round,pad=.35", fc="#26334d", ec="#51627e"))
        if metrics["q20"] is not None:
            ax_hist.axvline(metrics["q20"], color="#7dd3fc", lw=1.2, ls=":", label="20%分位线")
    panel_title(ax_hist, "主图 · 扣非PE 分布与正态拟合",
                "看位置：绿/蓝为低估区，黄/红为高估区；白线为当前估值")
    ax_hist.set_xlabel("扣非PE（倍）"); ax_hist.set_ylabel("出现频次（交易日）")
    leg = ax_hist.legend(fontsize=8, ncol=3, loc="upper right", frameon=True)
    leg.get_frame().set_facecolor("#182338"); leg.get_frame().set_edgecolor(grid)
    for t in leg.get_texts(): t.set_color(text_main)

    shade_events(ax_ts, low_events, green, .18); shade_events(ax_ts, extreme_events, blue, .23)
    ax_ts.plot(df["date"], df["pe"], color="#e6edf7", lw=1.25, label="扣非PE")
    for col, label, color, ls in [("mu","μ","#8794aa","--"),("minus_1sigma","μ-1σ",green,"--"),
                                  ("minus_2sigma","μ-2σ","#3d8be0","--"),("plus_1sigma","μ+1σ",amber,":"),
                                  ("plus_2sigma","μ+2σ",red,":")]:
        ax_ts.plot(df["date"], df[col], color=color, ls=ls, lw=1.05, label=label)
    if pd.notna(last["pe"]):
        ax_ts.scatter(last["date"], last["pe"], color=red, edgecolor="#ffffff", lw=.7, s=52, zorder=5)
        ax_ts.annotate(f'{last["pe"]:.2f}× · {last["signal"]}', xy=(last["date"], last["pe"]),
                       xytext=(-88, 16), textcoords="offset points", color="#ffffff", fontsize=8,
                       bbox=dict(boxstyle="round,pad=.4", fc=red, ec="none"),
                       arrowprops=dict(arrowstyle="-", color=red))
    panel_title(ax_ts, "副图 1 · 时间序列与低估区间",
                "看时间：绿色为 PE＜μ-1σ，蓝色为 PE＜μ-2σ，红点为当前")
    ax_ts.set_ylabel("扣非PE（倍）")
    leg = ax_ts.legend(ncol=6, fontsize=8, loc="upper left", frameon=True)
    leg.get_frame().set_facecolor("#182338"); leg.get_frame().set_edgecolor(grid)
    for t in leg.get_texts(): t.set_color(text_main)

    ax_info.set_facecolor(card); ax_info.set_xlim(0, 1); ax_info.set_ylim(0, 1); ax_info.axis("off")
    def fmt(v, pct=False):
        if v is None or pd.isna(v): return "—"
        return f"{v:.1%}" if pct else f"{v:.2f}"
    info = [
        ("数据截止", metrics["as_of"]), ("当前扣非PE", fmt(metrics["current_pe"])),
        (f'{args.window}日分位', fmt(metrics["historical_percentile"], True)), ("μ / σ", f'{fmt(metrics["mu"])} / {fmt(metrics["sigma"])}'),
        ("低估 / 极端线", f'{fmt(metrics["low_threshold"])} / {fmt(metrics["extreme_low_threshold"])}'),
        ("已结束低估次数", str(metrics["completed_low_events"])), ("平均 / 中位时长", f'{fmt(metrics["mean_duration"])} / {fmt(metrics["median_duration"])} 交易日'),
        ("P75时长", f'{fmt(metrics["p75_duration"])} 交易日'), ("当前低估已持续", f'{current_days} 交易日'),
        ("正态信号", metrics["normal_signal"]), ("分位信号", metrics["percentile_signal"]),
    ]
    signal_colors = {"极端低估": blue, "低估": green, "合理": "#65748d",
                     "高估": amber, "极端高估": red, "亏损区": "#6b7280", "数据不足": "#6b7280"}
    ax_info.text(.05, .96, "估值信号灯", fontsize=16, weight="bold", va="top", color=text_main,
                 transform=ax_info.transAxes)
    badge_text = metrics["normal_signal"] if not signal_conflict else f'{metrics["normal_signal"]}｜分位{metrics["percentile_signal"]}'
    ax_info.text(.95, .95, badge_text, ha="right", va="top", color="#ffffff",
                 fontsize=10, weight="bold",
                 bbox=dict(boxstyle="round,pad=.45", fc=signal_colors.get(metrics["normal_signal"], "#65748d"), ec="none"),
                 transform=ax_info.transAxes)
    y = .84
    for k, v in info:
        ax_info.text(.05, y, k, fontsize=9, color=text_muted, transform=ax_info.transAxes)
        value_color = signal_colors.get(v, text_main) if k in ("正态信号", "分位信号") else text_main
        ax_info.text(.95, y, v, fontsize=10, weight="bold", color=value_color, ha="right",
                     transform=ax_info.transAxes)
        ax_info.plot([.05,.95], [y-.026,y-.026], color=grid, lw=.55, transform=ax_info.transAxes)
        y -= .071

    ranked = completed.sort_values("trading_days", ascending=False).reset_index(drop=True) if not completed.empty else completed
    if not ranked.empty:
        vals_all = ranked["trading_days"].to_numpy(); cum_all = np.cumsum(vals_all)/np.sum(vals_all)
        latest_start = completed.loc[pd.to_datetime(completed["end"]).idxmax(), "start"]
        latest_rank = int(ranked.index[ranked["start"] == latest_start][0])
        display_n = min(15, len(ranked))
        labels = [r.start[:7] for r in ranked.head(display_n).itertuples()]
        vals = vals_all[:display_n].astype(float); cum = cum_all[:display_n].astype(float)
        if len(ranked) > display_n:
            labels.append(f"其余{len(ranked)-display_n}次")
            vals = np.append(vals, vals_all[display_n:].sum())
            cum = np.append(cum, 1.0)
        yy = np.arange(len(vals))
        colors = [green if i < np.argmax(cum >= .8)+1 else "#455a78" for i in range(len(vals))]
        if latest_rank < display_n:
            colors[latest_rank] = "#38bdf8"
        ax_par.barh(yy, vals, color=colors, alpha=.9, height=.64)
        ax_par.set_yticks(yy, labels=labels); ax_par.invert_yaxis()
        ax_par.tick_params(axis="y", labelsize=8)
        for i, (y_pos, value) in enumerate(zip(yy, vals)):
            suffix = "  最新一次" if i == latest_rank and latest_rank < display_n else ""
            label_color = "#38bdf8" if suffix else text_main
            ax_par.text(value + max(vals)*.008, y_pos, f"{int(value)}{suffix}",
                        va="center", color=label_color, fontsize=8, weight="bold" if suffix else "normal")
        axp = ax_par.twiny(); axp.set_xlim(0, 1.02); axp.plot(cum, yy, color=red, marker="o", ms=3.5, lw=1.5)
        axp.axvline(.8, color=amber, ls="--", lw=1.1)
        axp.set_xticks([0, .2, .4, .6, .8, 1.0], labels=["0%", "20%", "40%", "60%", "80%", "100%"])
        axp.tick_params(axis="x", colors=red, labelsize=8, direction="in", pad=-16)
        axp.set_xlabel("")
        axp.text(.8, -.65, "80%关键少数线", color=amber, fontsize=8, ha="right", va="center")
        for spine in axp.spines.values(): spine.set_color(grid)
    else:
        ax_par.text(.5, .5, "历史窗口内无有效低估事件", color=text_muted,
                    ha="center", va="center", transform=ax_par.transAxes)
    panel_title(ax_par, "副图 2 · 历史低估时长与关键少数",
                "柱形＝每次低估持续天数；蓝色＝最新一次；红线＝累计时长占比；绿柱构成主要80%时长")
    ax_par.set_xlabel("持续交易日"); ax_par.set_ylabel("低估事件")

    fig.suptitle(f"{name}（{code}）扣非PE估值状态与低估时长",
                 fontsize=20, weight="bold", color=text_main)
    fig.text(.5, .006, f"数据源：iFinD｜窗口 {args.window} 交易日｜最少样本 {args.min_periods}｜{'严格事前阈值' if args.strict_prior else '含当日阈值'}｜估值信号不等同于价格预测",
             ha="center", fontsize=8, color=text_muted)
    fig.savefig(args.output_dir / f"{safe_code}_valuation_dashboard.png", dpi=200,
                facecolor=fig.get_facecolor())
    plt.close(fig)
    df.to_csv(args.output_dir / f"{safe_code}_pe_timeseries.csv", index=False, encoding="utf-8-sig")
    events.to_csv(args.output_dir / f"{safe_code}_undervaluation_events.csv", index=False, encoding="utf-8-sig")
    (args.output_dir / f"{safe_code}_valuation_metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    constructed = {"market_cap", "deducted_net_profit_ttm"}.issubset(raw.columns)
    provenance = {"source": "iFinD export", "input_file": str(args.input.resolve()), "columns": list(raw.columns), "calculation": "market_cap / deducted_net_profit_ttm" if constructed else "direct deducted_pe", "notes": "负利润/负PE不进入估值统计；滚动统计不使用未来数据。"}
    (args.output_dir / f"{safe_code}_data_provenance.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8")
    from build_html_dashboard import build_html
    build_html(args.output_dir, safe_code, name, code)


if __name__ == "__main__":
    main()
