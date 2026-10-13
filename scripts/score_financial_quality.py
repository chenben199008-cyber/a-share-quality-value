#!/usr/bin/env python3
"""Deterministic V4.2 financial-quality scorer."""
import argparse, json, sys
from pathlib import Path
ANCHORS={"roic":([0,4,8,12,16,20],[0,20,40,60,80,100]),"growth":([-15,0,5,10,15,25],[0,20,40,60,80,100]),"ccr":([0,.4,.6,.8,1,1.2],[0,20,40,60,80,100]),"fcf_ic":([-5,0,3,6,10,15],[0,20,40,60,80,100]),"debt_ebitda":([6,4,3,2,1,0],[0,20,40,60,80,100])}
METRIC_WEIGHTS={"roic":.70,"growth":.10,"ccr":.10,"fcf_ic":.05,"debt_ebitda":.05}
TIME_WEIGHTS=[.20,.30,.50]
def interpolate(value,xs,scores):
    descending=xs[0]>xs[-1]
    if (not descending and value<=xs[0]) or (descending and value>=xs[0]): return float(scores[0])
    if (not descending and value>=xs[-1]) or (descending and value<=xs[-1]): return float(scores[-1])
    for i in range(len(xs)-1):
        lo,hi=xs[i],xs[i+1]
        if min(lo,hi)<=value<=max(lo,hi): return scores[i]+(value-lo)/(hi-lo)*(scores[i+1]-scores[i])
    raise ValueError("value did not fall within anchors")
def metric_score(name,item):
    status=item.get("status","ok")
    if status in {"missing","review"}: return {**item,"score":None}
    if "score_override" in item:
        value=float(item["score_override"])
        if not 0<=value<=100: raise ValueError(f"{name}: score_override must be 0..100")
    else:
        if item.get("value") is None: return {**item,"status":"missing","score":None}
        value=interpolate(float(item["value"]),*ANCHORS[name])
    return {**item,"score":round(value,4)}
def score_period(period):
    metrics,contributions={},{}
    for name,weight in METRIC_WEIGHTS.items():
        metrics[name]=metric_score(name,period.get("metrics",{}).get(name,{"status":"missing"}))
        value=metrics[name]["score"]
        contributions[name]=None if value is None else round(value*weight,4)
    total=round(sum(contributions.values()),4) if all(v is not None for v in contributions.values()) else None
    return {"label":period.get("label"),"metrics":metrics,"contributions":contributions,"period_score":total}
def grade(value):
    if value is None:return None
    for floor,letter,label in [(85,"A","优质"),(75,"B","良好"),(60,"C","一般"),(45,"D","较弱"),(0,"E","较差")]:
        if value>=floor:return {"grade":letter,"label":label}
    raise ValueError("score below zero")
def score(payload):
    if len(payload.get("periods",[]))!=3:raise ValueError("periods must contain exactly 3 periods in 20/30/50 order")
    periods=[score_period(p) for p in payload["periods"]]
    final=None if any(p["period_score"] is None for p in periods) else round(sum(p["period_score"]*w for p,w in zip(periods,TIME_WEIGHTS)),2)
    return {"model":"优质企业财务质量评估模型 V4.2","company":payload.get("company",{}),"periods":periods,"time_weights":TIME_WEIGHTS,"final_score":final,"result":grade(final),"status":"ok" if final is not None else "数据不足"}
def main():
    parser=argparse.ArgumentParser();parser.add_argument("--input",type=Path);args=parser.parse_args()
    payload=json.loads(args.input.read_text(encoding="utf-8") if args.input else sys.stdin.read())
    json.dump(score(payload),sys.stdout,ensure_ascii=False,indent=2);sys.stdout.write("\n")
if __name__=="__main__":main()
