#!/usr/bin/env python3
"""Render a self-contained HTML financial-quality report with inline SVG charts."""
import argparse, html, json, math
from pathlib import Path
from score_financial_quality import METRIC_WEIGHTS, TIME_WEIGHTS, score

META={
 "roic":("ROIC","%"),"growth":("扣非利润增长率","%"),"ccr":("现金利润比","倍"),
 "fcf_ic":("FCF资本回报率","%"),"debt_ebitda":("净负债/EBITDA","倍")}
COLORS={"A":"#0f766e","B":"#2563eb","C":"#ca8a04","D":"#ea580c","E":"#dc2626"}
def esc(x):return html.escape("" if x is None else str(x))
def display_source(x):
 s="" if x is None else str(x)
 return s.replace("；合并报表口径","").replace(";合并报表口径","").replace(" 合并报表口径","").strip()
def conclusion_html(item):
 if isinstance(item,dict):
  point=str(item.get("point","")).strip();description=str(item.get("description","")).strip()
 else:
  text="" if item is None else str(item).strip();point=text;description=""
  for separator in ("：",":","，"):
   if separator in text:
    point,description=(part.strip() for part in text.split(separator,1));break
 if not point:return ""
 point=point.rstrip("。；;：:")+"。"
 return f'<li class="conclusion-item"><strong>{esc(point)}</strong>'+((f'<p>{esc(description)}</p>') if description else '')+'</li>'
def fmt(name,v):
 if v is None:return "—"
 return f"{v:.1f}%" if name in {"roic","growth","fcf_ic"} else f"{v:.1f}倍"
def svg_bar(labels,values,title,color="#2563eb",maximum=100):
 w,h=720,90+len(values)*48; bars=[]
 for i,(lab,val) in enumerate(zip(labels,values)):
  y=58+i*48; width=max(0,min(545,545*(val or 0)/maximum))
  bars.append(f'<text x="8" y="{y+18}" class="label">{esc(lab)}</text><rect x="150" y="{y}" width="545" height="24" rx="6" class="track"/><rect x="150" y="{y}" width="{width:.1f}" height="24" rx="6" fill="{color}"/><text x="705" y="{y+18}" class="value">{"—" if val is None else f"{val:.1f}"}</text>')
 return f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="{esc(title)}"><text x="8" y="28" class="title">{esc(title)}</text>{"".join(bars)}</svg>'
def period_trace_chart(periods,color="#2563eb"):
 labels=[p["label"] for p in periods];scores=[p["period_score"] for p in periods]
 colors=["#0a84ff","#30b0c7","#ff9f0a"]
 contributions=[None if p["period_score"] is None else p["period_score"]*TIME_WEIGHTS[i] for i,p in enumerate(periods)]
 final=sum(v for v in contributions if v is not None) if any(v is not None for v in contributions) else None
 w,h=900,350;bar_x,bar_w=185,625;parts=[]
 parts.append('<text x="24" y="38" class="trace-title">三个评价期间综合得分</text><text x="24" y="61" class="trace-subtitle">观察财务质量的稳定性与近期变化</text>')
 for i,(label,value,bar_color) in enumerate(zip(labels,scores,colors)):
  y=86+i*52;width=0 if value is None else bar_w*max(0,min(100,value))/100
  parts.append(f'<text x="24" y="{y+19}" class="trace-label">{esc(label)}</text><rect x="{bar_x}" y="{y}" width="{bar_w}" height="28" rx="9" class="trace-track"/><rect x="{bar_x}" y="{y}" width="{width:.1f}" height="28" rx="9" fill="{bar_color}"/><text x="842" y="{y+20}" class="trace-score">{"—" if value is None else f"{value:.1f}"}</text>')
 y=252;parts.append(f'<rect x="18" y="{y-14}" width="864" height="96" rx="20" class="contribution-panel"/><text x="24" y="{y+20}" class="trace-section-title">最终贡献构成</text><rect x="{bar_x}" y="{y}" width="{bar_w}" height="32" rx="10" class="trace-track"/>')
 x=bar_x
 for label,value,bar_color in zip(labels,contributions,colors):
  width=0 if value is None else bar_w*value/100
  parts.append(f'<rect x="{x:.1f}" y="{y}" width="{width:.1f}" height="32" rx="6" fill="{bar_color}"/><text x="{x+width/2:.1f}" y="{y+21}" class="contribution-value center">{"—" if value is None else f"{value:.1f}"}</text>')
  x+=width
 parts.append(f'<text x="842" y="{y+22}" class="final-score">{"—" if final is None else f"{final:.1f}"}</text>')
 for i,(label,value,bar_color) in enumerate(zip(labels,contributions,colors)):
  lx=bar_x+i*208;parts.append(f'<circle cx="{lx}" cy="{y+62}" r="5" fill="{bar_color}"/><text x="{lx+11}" y="{y+66}" class="trace-legend">{esc(label)} · {"—" if value is None else f"{value:.1f}"}</text>')
 return f'<svg class="chart period-trace-chart" viewBox="0 0 {w} {h}" role="img" aria-label="三个评价期间综合得分及最终贡献构成">{"".join(parts)}</svg>'
def radar_chart(period,color="#2563eb"):
 keys=list(METRIC_WEIGHTS); labels=[META[k][0] for k in keys]; values=[period["metrics"][k]["score"] for k in keys]
 w,h=620,500;cx,cy,radius=310,255,165;angles=[-math.pi/2+i*2*math.pi/len(keys) for i in range(len(keys))];parts=[f'<text x="18" y="30" class="title">最新期五项标准分雷达图</text>']
 def point(angle,r):return cx+math.cos(angle)*r,cy+math.sin(angle)*r
 for level in range(20,101,20):
  pts=' '.join(f'{x:.1f},{y:.1f}' for x,y in (point(a,radius*level/100) for a in angles));parts.append(f'<polygon points="{pts}" class="radar-ring"/><text x="{cx+5}" y="{cy-radius*level/100+12:.1f}" class="axis">{level}</text>')
 for a,label,value in zip(angles,labels,values):
  x,y=point(a,radius);lx,ly=point(a,radius+48);anchor='middle' if abs(math.cos(a))<.25 else ('start' if math.cos(a)>0 else 'end');score_label='—' if value is None else f'{value:.1f}';parts.append(f'<line x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}" class="radar-axis"/><text x="{lx:.1f}" y="{ly:.1f}" class="label" text-anchor="{anchor}">{esc(label)} {score_label}</text>')
 valid=[]
 for a,value in zip(angles,values):
  scaled=0 if value is None else value;valid.append((*point(a,radius*scaled/100),value))
 pts=' '.join(f'{x:.1f},{y:.1f}' for x,y,_ in valid);parts.append(f'<polygon points="{pts}" fill="{color}" class="radar-area"/>')
 for x,y,value in valid:
  parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{color}" class="radar-dot"/>')
 return f'<svg class="chart radar-chart" viewBox="0 0 {w} {h}" role="img" aria-label="最新期五项标准分雷达图">{"".join(parts)}</svg>'
def contribution_chart(period,color="#38bdf8"):
 labels=[f'{META[k][0]}（{METRIC_WEIGHTS[k]*100:.1f}%）' for k in METRIC_WEIGHTS];values=[period["contributions"][k] for k in METRIC_WEIGHTS]
 return svg_bar(labels,values,"最新期加权贡献（总分百分点）",color,40)
def smooth_path(points):
 coords=[(p[0],p[1]) for p in points]
 if len(coords)<2:return ''
 commands=[f'M {coords[0][0]:.1f} {coords[0][1]:.1f}']
 for (x0,y0),(x1,y1) in zip(coords,coords[1:]):
  offset=(x1-x0)*.38
  commands.append(f'C {x0+offset:.1f} {y0:.1f}, {x1-offset:.1f} {y1:.1f}, {x1:.1f} {y1:.1f}')
 return ' '.join(commands)
def trend_svg(name,rows):
 vals=[r.get(name) for r in rows]; numeric=[v for v in vals if v is not None]; w,h=900,250; l,r,t,b=58,24,42,54
 if not numeric:return ''
 lo,hi=min(numeric),max(numeric); pad=(hi-lo)*.15 or 1;lo-=pad;hi+=pad; pw=w-l-r;ph=h-t-b;pts=[];parts=[]
 for i,(row,v) in enumerate(zip(rows,vals)):
  x=l+(pw*i/max(1,len(rows)-1))
  parts.append(f'<text x="{x:.1f}" y="{h-14}" class="axis center">{esc(row.get("label"))}</text>')
  if v is not None:
   y=t+ph*(hi-v)/(hi-lo);pts.append((x,y,v,i==len(rows)-1));parts.append(f'<text x="{x:.1f}" y="{max(26,y-10):.1f}" class="tiny center">{v:.1f}</text>')
 for tick in range(3):
  y=t+ph*tick/2;parts.append(f'<line x1="{l}" y1="{y:.1f}" x2="{w-r}" y2="{y:.1f}" class="grid"/><text x="{l-6}" y="{y+4:.1f}" class="axis right">{hi-(hi-lo)*tick/2:.1f}</text>')
 if pts:parts.append(f'<path d="{smooth_path(pts)}" class="trend-line"/>')
 for x,y,_,latest in pts:parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{6 if latest else 4}" class="{"latest-dot" if latest else "trend-dot"}"/>')
 title,unit=META[name];return f'<svg class="mini-chart" viewBox="0 0 {w} {h}" role="img" aria-label="{esc(title)}趋势"><text x="12" y="22" class="title">{esc(title)}（{unit}）</text>{"".join(parts)}</svg>'
def render(payload):
 result=score(payload);company=payload.get("company",{});periods=result["periods"];final=result["final_score"];grade=(result.get("result") or {}).get("grade","—");grade_label=(result.get("result") or {}).get("label","数据不足");accent=COLORS.get(grade,"#64748b")
 period_rows=''.join(f'<tr><td>{esc(p["label"])}</td><td>{"—" if p["period_score"] is None else f"{p["period_score"]:.1f}"}</td><td>{TIME_WEIGHTS[i]*100:.1f}%</td><td>{"—" if p["period_score"] is None else f"{p["period_score"]*TIME_WEIGHTS[i]:.1f}"}</td></tr>' for i,p in enumerate(periods))
 latest=periods[-1];detail=''.join(f'<tr><td>{esc(META[k][0])}</td><td>{fmt(k,latest["metrics"][k].get("value"))}</td><td>{"—" if latest["metrics"][k]["score"] is None else f"{latest["metrics"][k]["score"]:.1f}"}</td><td>{METRIC_WEIGHTS[k]*100:.1f}%</td><td>{"—" if latest["contributions"][k] is None else f"{latest["contributions"][k]:.1f}"}</td></tr>' for k in METRIC_WEIGHTS)
 trend=payload.get("trend",[]);trend_table=''.join('<tr><td>'+esc(r.get("label"))+'</td>'+''.join(f'<td>{fmt(k,r.get(k))}</td>' for k in METRIC_WEIGHTS)+'</tr>' for r in trend)
 conclusions=''.join(conclusion_html(x) for x in payload.get("conclusion",[]));notes=''.join(f'<li>{esc(x)}</li>' for x in payload.get("methodology_notes",[]))
 css='''*{box-sizing:border-box}html{background:#f5f5f7}body{margin:0;background:#f5f5f7;color:#1d1d1f;font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display","SF Pro Text","Helvetica Neue","Segoe UI","Microsoft YaHei",sans-serif;-webkit-font-smoothing:antialiased}.page{max-width:1180px;margin:auto;padding:28px 24px 72px}.hero{position:relative;min-height:350px;padding:54px 58px;border-radius:28px;color:#f5f5f7;background:radial-gradient(circle at 78% 24%,#183d68 0,transparent 34%),linear-gradient(135deg,#090d14 0%,#111827 58%,#0b1220 100%);display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:42px;overflow:hidden;box-shadow:0 22px 60px rgba(15,23,42,.18)}.hero:after{content:"";position:absolute;width:300px;height:300px;border:1px solid rgba(255,255,255,.08);border-radius:50%;right:-110px;bottom:-170px}.hero h1{font-size:clamp(42px,6vw,68px);line-height:1;letter-spacing:-.048em;margin:14px 0 24px}.hero small{display:block;font-size:.27em;letter-spacing:.03em;color:#a1a1a6;margin-top:14px}.score{font-size:clamp(88px,11vw,136px);line-height:.82;letter-spacing:-.06em;font-weight:730}.badge{display:inline-flex;padding:8px 15px;border-radius:999px;background:var(--accent);color:#fff;font-weight:650}.meta{grid-column:1/-1;display:grid;grid-template-columns:minmax(0,.85fr) minmax(0,1.15fr) minmax(0,1.15fr) minmax(0,.85fr);gap:0;margin-top:8px;padding-top:24px;border-top:1px solid rgba(255,255,255,.12)}.meta-item{display:flex;flex-direction:column;gap:7px;min-width:0;padding:0 28px;border-left:1px solid rgba(255,255,255,.10)}.meta-item:first-child{padding-left:0;border-left:0}.meta-item:nth-child(2){padding-left:18px;padding-right:38px}.meta-item:last-child{padding-right:0}.meta-label{color:#8e8e93;font-size:12px}.meta-item strong{color:#f5f5f7;font-size:14px;font-weight:600;line-height:1.35;white-space:nowrap}.hero .muted{color:#a1a1a6}.hero-score{position:relative;z-index:1;text-align:right;justify-self:end;align-self:center;transform:translateX(-68px)}.card{background:#fff;border:1px solid rgba(0,0,0,.035);border-radius:26px;padding:34px;margin-top:22px;box-shadow:0 10px 35px rgba(15,23,42,.055);break-inside:avoid}.card h2{font-size:clamp(27px,3.3vw,38px);line-height:1.08;letter-spacing:-.035em;margin:0 0 26px}.period-table-wrap{max-width:100%;overflow-x:auto}.period-table{width:100%;table-layout:fixed;font-size:12px}.period-table th{font-size:11px}.period-table th,.period-table td{padding:9px 7px;white-space:nowrap}.period-viz{margin-top:20px;padding:24px;background:linear-gradient(145deg,#fbfdff 0%,#f5f8fc 100%);border-color:#e1e8f0}.period-trace-chart{display:block}.trace-title{font-size:21px;font-weight:720;fill:#1d1d1f;letter-spacing:-.02em}.trace-subtitle{font-size:12px;fill:#86868b}.trace-label{font-size:13px;font-weight:620;fill:#3a3a3c}.trace-score{font-size:13px;font-weight:720;fill:#1d1d1f}.trace-track{fill:#e8edf3}.final-score{font-size:14px;font-weight:760;fill:#0f766e}.contribution-panel{fill:#fff;stroke:#e7ebf0}.trace-section-title{font-size:15px;font-weight:700;fill:#1d1d1f}.trace-legend{font-size:11px;font-weight:600;fill:#6e6e73}.contribution-value{font-size:11px;font-weight:750;fill:#fff}.detail-viz{display:grid;grid-template-columns:minmax(0,1.28fr) minmax(0,.72fr);gap:18px;align-items:stretch;margin-top:18px}.detail-viz>div{min-width:0}.viz-panel{background:linear-gradient(180deg,#fbfbfd,#f7f7fa);border:1px solid #e8e8ed;border-radius:22px;padding:18px;display:flex;align-items:center;min-width:0;overflow:hidden}.detail-viz .chart{width:100%;height:auto}.trend-grid{display:grid;margin-top:18px;grid-template-columns:minmax(0,1fr);gap:16px}.trend-grid .mini-chart{display:block;width:100%;min-width:0;background:#fbfbfd;border:1px solid #e8e8ed;border-radius:20px;padding:10px}table{width:100%;max-width:100%;border-collapse:separate;border-spacing:0;font-size:14px;background:#fff;border:1px solid #ececf0;border-radius:18px;overflow:hidden}th,td{padding:14px 15px;border-bottom:1px solid #ececf0;text-align:right}th{background:#f7f7f9;color:#6e6e73;font-weight:600}th:first-child,td:first-child{text-align:left}tbody tr:last-child td{border-bottom:0}tbody tr:hover td{background:#fafafa}.chart,.mini-chart{width:100%;height:auto}.title{font-size:16px;font-weight:650;fill:#1d1d1f}.label{font-size:13px;fill:#3a3a3c}.value{font-size:12px;font-weight:650;fill:#1d1d1f}.axis,.tiny{font-size:10px;fill:#86868b}.tiny{font-size:11px;font-weight:600;fill:#6e6e73}.center{text-anchor:middle}.right{text-anchor:end}.track{fill:#e5e5ea}.grid{stroke:#d9d9de;stroke-width:1}.trend-line{fill:none;stroke:#147ce5;stroke-width:3}.latest-dot{fill:#ff9f0a;stroke:#fff;stroke-width:2}.trend-dot{fill:#147ce5}.radar-ring{fill:none;stroke:#d1d1d6;stroke-width:1}.radar-axis{stroke:#e5e5ea;stroke-width:1}.radar-area{fill-opacity:.14;stroke:var(--accent);stroke-width:3}.radar-dot{stroke:#fff;stroke-width:2}.disclaimer{border-left:3px solid #ff9f0a;background:#fff8eb;border-radius:12px;padding:16px 18px;color:#6e6e73}.muted{color:#6e6e73;font-weight:600;letter-spacing:.01em}.conclusion-list{list-style:none;padding:0;margin:0;display:grid;gap:14px}.conclusion-item{margin:0;padding:18px 20px;border-radius:16px;background:#f7f7f9;border:1px solid #ececf0;line-height:1.6}.conclusion-item strong{display:block;font-size:16px;color:#1d1d1f;margin-bottom:5px}.conclusion-item p{margin:0;color:#515154}.methodology-list li{margin:.6em 0;line-height:1.65}@media(max-width:620px){.detail-viz,.hero{grid-template-columns:1fr}.score-right .chart{min-height:430px}.hero{padding:40px 30px}.meta{grid-template-columns:repeat(4,minmax(160px,1fr));overflow-x:auto}.page{padding:14px 12px 48px}.card{padding:24px 18px;border-radius:22px}.viz-panel{padding:12px}table{display:block;overflow-x:auto;white-space:nowrap}}@media print{body{background:#fff}.page{max-width:none;padding:0}.card,.hero{box-shadow:none;break-inside:avoid}.viz-panel{border:1px solid #e8e8ed}}'''
 css+='''html,body{background:#0b1220;color:#edf2f7}.card{background:#121b2d;border-color:#29344b;box-shadow:0 12px 38px rgba(0,0,0,.2)}.card h2{color:#edf2f7}table{background:#121b2d;border-color:#29344b;color:#edf2f7}th,td{border-bottom-color:#29344b}th{background:#172238;color:#9eabc0}tbody tr:hover td{background:#172238}.period-viz,.viz-panel{background:#0f192b;border-color:#29344b}.trend-grid .mini-chart{background:#0f192b;border-color:#29344b}.trace-title,.trace-score,.trace-section-title,.title,.value{fill:#edf2f7}.trace-subtitle,.trace-legend,.trace-label,.label,.axis,.tiny{fill:#9eabc0}.trace-track,.track{fill:#26344b}.contribution-panel{fill:#121b2d;stroke:#29344b}.grid,.radar-ring,.radar-axis{stroke:#334158}.conclusion-item{background:#172238;border-color:#29344b}.conclusion-item strong{color:#edf2f7}.conclusion-item p,.methodology-list{color:#b7c2d3}.disclaimer{background:#272317;color:#d7c9a5;border-left-color:#f0a12b}.muted{color:#9eabc0}@media print{html,body{background:#0b1220}.card{box-shadow:none}}'''
 period_chart=period_trace_chart(periods,accent)
 contribution=contribution_chart(latest)
 radar=radar_chart(latest,accent)
 detail_charts=f'<div class="viz-panel">{contribution}</div><div class="viz-panel">{radar}</div>'
 mini=''.join(trend_svg(k,trend) for k in METRIC_WEIGHTS)
 return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(company.get("name","企业"))}财务质量评估</title><style>:root{{--accent:{accent}}}{css}</style></head><body><main class="page"><section class="hero"><div class="hero-copy"><div class="muted">优质企业财务质量评估模型 V4.2</div><h1>{esc(company.get("name"))} <small>{esc(company.get("code"))}</small></h1><span class="badge">{esc(grade)}级 · {esc(grade_label)}</span></div><div class="hero-score"><div class="score">{"—" if final is None else f"{final:.1f}"}</div></div><div class="meta"><div class="meta-item"><span class="meta-label">行业</span><strong>{esc(company.get("industry"))}</strong></div><div class="meta-item"><span class="meta-label">数据源</span><strong>{esc(display_source(company.get("source")))}</strong></div><div class="meta-item"><span class="meta-label">最新报告期</span><strong>{esc(company.get("latest_period"))}</strong></div><div class="meta-item"><span class="meta-label">更新于</span><strong>{esc(company.get("updated_at"))}</strong></div></div></section><section class="card"><h2>综合评分追溯</h2><div class="period-table-wrap"><table class="period-table"><thead><tr><th>期间</th><th>单期得分</th><th>时间权重</th><th>最终贡献</th></tr></thead><tbody>{period_rows}</tbody></table></div><div class="period-viz viz-panel">{period_chart}</div></section><section class="card"><h2>最新期指标明细</h2><table><thead><tr><th>指标</th><th>指标值</th><th>标准分</th><th>权重</th><th>加权得分</th></tr></thead><tbody>{detail}</tbody></table><div class="detail-viz">{detail_charts}</div></section><section class="card"><h2>五年财务趋势</h2><table><thead><tr><th>期间</th>{''.join(f'<th>{esc(META[k][0])}</th>' for k in METRIC_WEIGHTS)}</tr></thead><tbody>{trend_table}</tbody></table><div class="trend-grid">{mini}</div></section><section class="card"><h2>评价结论</h2><ul class="conclusion-list">{conclusions}</ul></section><section class="card"><h2>计算口径与限制</h2><ul class="methodology-list">{notes}</ul><p class="disclaimer">本报告仅用于企业财务质量评价，不等同于股票投资价值判断或买卖建议。</p></section></main></body></html>'''
def main():
 p=argparse.ArgumentParser();p.add_argument("--input",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();payload=json.loads(a.input.read_text(encoding="utf-8"));a.output.write_text(render(payload),encoding="utf-8");print(a.output.resolve())
if __name__=="__main__":main()


