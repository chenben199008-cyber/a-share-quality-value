# A股财务质量与扣非PE综合报告 Skill

该 Skill 内置两套独立计算引擎：

- 财务质量：评估资本回报、成长、现金兑现、自由现金流和债务负担；
- 扣非PE估值：评估当前历史位置、滚动分位和低估持续时长。

一次运行生成两部分完整结果与一个离线单文件HTML。综合页按“企业质量 → 估值位置 → 关键验证条件”组织，并通过页签切换查看明细。

当前原生融合模板为 `quality-value-v2.4`。估值页必须完整显示扣非PE频次直方图、按频次缩放的正态拟合曲线及五档估值区域，当前扣非PE使用醒目的白色实线；时间序列使用绿色表示低估、蓝色表示极端低估，区间上方只显示天数；独立历史低估持续时长模块已删除，统计汇总保留在时间序列下方。财务页必须显示最近三个完整年度与最新TTM的经营趋势，并在收入、扣非净利润和经营现金流柱形上直接标注数值。交付前使用 `node scripts/validate_latest_report.js <报告.html>` 校验，旧模板不能通过。

```powershell
python scripts/run_integrated_report.py `
  --quality-input quality_input.json `
  --valuation-input deducted_pe_timeseries.csv `
  --output-dir combined_output/002841_SZ `
  --name 视源股份 `
  --code 002841.SZ
```

财务评分与估值信号彼此独立。综合决策层只用于确定研究优先级，不直接输出买入结论。估值模块强制采用扣非PE TTM，并要求用适用市值口径与扣非归母净利润TTM交叉验证最新值。
