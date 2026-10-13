#!/usr/bin/env node
const fs=require('fs');
const path=process.argv[2];
if(!path||!fs.existsSync(path)){console.error('usage: node validate_latest_report.js <report.html>');process.exit(2)}
const h=fs.readFileSync(path,'utf8');
const checks={
 version:h.includes('data-template-version="quality-value-v2.2"'),
 native_tabs:h.includes('01 财务质量')&&h.includes('02 扣非 PE TTM 估值'),
 no_iframe:!/<iframe\b/i.test(h),
 latest_ttm:/TTM/.test(h),
 summary_cards:(h.match(/class="card"/g)||[]).length>=4,
 transposed_score:h.includes('三年评分追溯')&&h.includes('<th>指标</th>'),
 score_colors:h.includes('score-period-row')&&h.includes('score-contribution-row'),
 pe_distribution:h.includes('扣非 PE 分布')&&h.includes('出现频次（交易日）')&&h.includes('data-chart="pe-distribution"'),
 complete_distribution:h.includes('data-series="histogram-counts"')&&h.includes('data-series="normal-fit"')&&h.includes('正态拟合频次'),
 five_zones:['极端低估','低估','合理','高估','极端高估'].every(x=>h.includes(x)),
 valuation_timeseries:h.includes('时间序列与低估时长')&&h.includes('μ−1σ')&&h.includes('μ−2σ'),
 operating_trend:h.includes('三年经营趋势')&&h.includes('data-chart="operating-trend"')&&h.includes('data-value-labels="true"')&&['收入','扣非净利润','经营现金流'].every(x=>h.includes(x)),
 duration:h.includes('低估 ')&&h.includes('天'),
 decision:h.includes('综合判断'),
 notes:h.includes('数据说明')
};
const failed=Object.entries(checks).filter(([,ok])=>!ok).map(([k])=>k);
console.log(JSON.stringify({template:'quality-value-v2.2',file:path,checks,ok:failed.length===0},null,2));
if(failed.length){console.error('旧模板或缺失模块: '+failed.join(', '));process.exit(1)}
