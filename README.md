# A股财务质量与扣非PE综合报告 Skill

该 Skill 内置两套独立计算引擎：

- 财务质量：评估资本回报、成长、现金兑现、自由现金流和债务负担；
- 扣非PE估值：评估当前历史位置、滚动分位和低估持续时长。

一次运行生成两部分完整结果与一个离线单文件HTML。综合页按“企业质量 → 估值位置 → 关键验证条件”组织，并通过页签切换查看明细。

```powershell
python scripts/run_integrated_report.py `
  --quality-input quality_input.json `
  --valuation-input deducted_pe_timeseries.csv `
  --output-dir combined_output/002841_SZ `
  --name 视源股份 `
  --code 002841.SZ
```

财务评分与估值信号彼此独立。综合决策层只用于确定研究优先级，不直接输出买入结论。估值模块强制采用扣非PE TTM，并要求用适用市值口径与扣非归母净利润TTM交叉验证最新值。
