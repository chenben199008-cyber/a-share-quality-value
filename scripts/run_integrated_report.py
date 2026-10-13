#!/usr/bin/env python3
"""Generate both analysis modules and one switchable offline report."""
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from score_financial_quality import score
def run(*args: str) -> None: subprocess.run([sys.executable, *map(str, args)], check=True)
def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument('--quality-input',type=Path,required=True); p.add_argument('--valuation-input',type=Path,required=True); p.add_argument('--output-dir',type=Path,required=True); p.add_argument('--name',required=True); p.add_argument('--code',required=True); p.add_argument('--window',type=int,default=756); p.add_argument('--min-periods',type=int,default=252); p.add_argument('--strict-prior',action='store_true'); a=p.parse_args()
    safe=a.code.replace('.','_').replace('/','_'); qdir=a.output_dir/'financial_quality'; vdir=a.output_dir/'valuation'; qdir.mkdir(parents=True,exist_ok=True); vdir.mkdir(parents=True,exist_ok=True)
    qhtml=qdir/f'{safe}_financial_quality.html'; run(HERE/'render_financial_quality.py','--input',a.quality_input,'--output',qhtml)
    va=[HERE/'render_valuation_dashboard.py',a.valuation_input,'--output-dir',vdir,'--code',a.code,'--name',a.name,'--window',str(a.window),'--min-periods',str(a.min_periods)]
    if a.strict_prior: va.append('--strict-prior')
    run(*va); vhtml=vdir/f'{safe}_valuation_dashboard.html'; combined=a.output_dir/f'{safe}_combined_dashboard.html'; manifest=a.output_dir/f'{safe}_combined_manifest.json'
    quality_payload=json.loads(a.quality_input.read_text(encoding='utf-8')); quality_result=score(quality_payload); vm=json.loads((vdir/f'{safe}_valuation_metrics.json').read_text(encoding='utf-8'))
    grade=(quality_result.get('result') or {}).get('grade'); quality_state={'A':'优秀','B':'良好','C':'一般','D':'较弱','E':'较弱'}.get(grade,'数据不足')
    pctl=vm.get('historical_percentile'); unreliable=vm.get('pe_model_unreliable',False)
    valuation_state='模型失真' if unreliable else ('偏低' if pctl is not None and pctl<=.20 else '偏高' if pctl is not None and pctl>=.80 else '中性')
    matrix={('优秀','偏低'):'重点研究',('优秀','中性'):'持续跟踪',('优秀','偏高'):'等待估值',('良好','偏低'):'积极研究',('良好','中性'):'观察',('良好','偏高'):'谨慎',('一般','偏低'):'条件观察',('一般','中性'):'观察',('一般','偏高'):'回避',('较弱','偏低'):'等待验证',('较弱','中性'):'谨慎',('较弱','偏高'):'回避'}
    overall='暂缓判断' if unreliable else matrix.get((quality_state,valuation_state),'数据不足')
    lm=quality_payload['periods'][-1]['metrics']; ccr=lm.get('ccr',{}).get('value'); fcf=lm.get('fcf_ic',{}).get('value')
    condition='经营现金流与自由现金流转正' if (ccr is not None and ccr<0) or (fcf is not None and fcf<0) else ('现金兑现连续两个报告期改善' if quality_state in ('一般','较弱') else '基本面与估值继续匹配')
    summary={'quality_state':quality_state,'quality_score':quality_result.get('final_score'),'valuation_state':valuation_state,'valuation_detail':f"3年分位 {pctl:.1%}" if pctl is not None else '分位数据不足','overall_state':overall,'key_condition':condition,'note':'最新TTM异常先作为待验证信号；连续两个报告期同向恶化后再视为结构性风险。'}
    summary_path=a.output_dir/f'{safe}_decision_summary.json'; summary_path.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    run(HERE/'build_combined_report.py','--quality-html',qhtml,'--valuation-html',vhtml,'--summary-json',summary_path,'--output',combined,'--manifest',manifest,'--name',a.name,'--code',a.code)
    payload=json.loads(manifest.read_text(encoding='utf-8')); payload['engine']='a-share-quality-valuation-suite integrated'; payload['inputs']={'financial_quality':str(a.quality_input.resolve()),'deducted_pe_ttm':str(a.valuation_input.resolve())}; payload['parameters']={'window':a.window,'min_periods':a.min_periods,'strict_prior':a.strict_prior}; payload['decision_summary']=summary; manifest.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8'); print(combined.resolve())
if __name__=='__main__': main()
