#!/usr/bin/env python3
"""Embed financial-quality and deducted-PE reports in one offline tabbed HTML."""

from __future__ import annotations

import argparse
import base64
import html
import json
from datetime import datetime, timezone
from pathlib import Path


def data64(path: Path, module_no: str, module_name: str, module_desc: str) -> str:
    document = path.read_text(encoding="utf-8")
    compact = f'''<style>.hero{{display:none!important}}.page{{padding-top:24px!important}}.module-intro{{display:flex;align-items:center;gap:16px;margin:0 0 20px;padding:18px 22px;border:1px solid #29344b;border-radius:18px;background:#121b2d;color:#edf2f7}}.module-no{{font-size:12px;font-weight:800;color:#60a5fa;letter-spacing:.08em}}.module-copy strong{{display:block;font-size:22px;letter-spacing:-.02em}}.module-copy span{{display:block;margin-top:4px;color:#8e9bb2;font-size:12px}}@media(max-width:620px){{.module-intro{{padding:15px 17px}}.module-copy strong{{font-size:19px}}}}</style><section class="module-intro"><div class="module-no">{html.escape(module_no)}</div><div class="module-copy"><strong>{html.escape(module_name)}</strong><span>{html.escape(module_desc)}</span></div></section>'''
    document = document.replace('<main class="page">', '<main class="page">' + compact, 1)
    return base64.b64encode(document.encode("utf-8")).decode("ascii")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--quality-html", type=Path, required=True)
    p.add_argument("--valuation-html", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--code", required=True)
    p.add_argument("--manifest", type=Path)
    p.add_argument("--summary-json", type=Path)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    for source in (args.quality_html, args.valuation_html):
        if not source.is_file() or source.stat().st_size == 0:
            raise FileNotFoundError(f"报告不存在或为空：{source}")

    payloads = {
        "quality": data64(args.quality_html, "01", "财务质量", "先判断企业经营质量、现金兑现与债务负担"),
        "valuation": data64(args.valuation_html, "02", "扣非PE估值", "再判断当前价格处于历史什么位置"),
    }
    title = f"{args.name}（{args.code}）综合分析"
    summary = json.loads(args.summary_json.read_text(encoding="utf-8")) if args.summary_json else {}
    summary_html = ''.join(
        f'<div class="decision-card"><span>{html.escape(label)}</span><strong>{html.escape(str(value))}</strong></div>'
        for label, value in [
            ('企业质量', summary.get('quality_state','—')),
            ('估值位置', summary.get('valuation_state','—')),
            ('综合状态', summary.get('overall_state','—')),
            ('关键条件', summary.get('key_condition','—')),
        ]
    )
    document = '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>__TITLE__</title>
<style>
*{box-sizing:border-box}html,body{height:100%;margin:0}body{background:#0b1220;color:#edf2f7;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif;overflow:hidden}
.shell{height:100%;display:grid;grid-template-rows:auto 1fr}.top{padding:13px 22px 11px;background:#10192a;border-bottom:1px solid #29344b;box-shadow:0 8px 24px rgba(0,0,0,.18);z-index:2}.row{display:flex;align-items:center;justify-content:space-between;gap:18px;flex-wrap:wrap}.title{font-size:18px;font-weight:750}.meta{font-size:11px;color:#8e9bb2;margin-top:3px}.tabs{display:flex;gap:7px;background:#0b1220;padding:5px;border-radius:11px}.tab{border:0;border-radius:8px;padding:9px 15px;color:#aeb9ca;background:transparent;font-weight:700;cursor:pointer}.tab:hover{color:#fff}.tab[aria-selected="true"]{color:#fff;background:#2563eb;box-shadow:0 4px 14px rgba(37,99,235,.28)}.decision{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-top:10px}.decision-card{background:#172238;border:1px solid #29344b;border-radius:10px;padding:8px 12px;min-width:0}.decision-card span{display:block;color:#8e9bb2;font-size:10px;margin-bottom:3px}.decision-card strong{display:block;color:#edf2f7;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.notice{margin-top:7px;color:#8e9bb2;font-size:10px}.stage{position:relative;min-height:0}.report{position:absolute;inset:0;width:100%;height:100%;border:0;background:#0b1220;display:none}.report.active{display:block}.loading{position:absolute;inset:0;display:grid;place-items:center;color:#8e9bb2}.noscript{padding:30px} @media(max-width:650px){.top{padding:11px 12px}.title{font-size:16px}.row{align-items:flex-start}.tabs{width:100%}.tab{flex:1;padding:8px}.decision{grid-template-columns:1fr 1fr}}
@media print{.top{display:none}.shell{display:block}.stage,.report{position:static;height:auto}.report{display:none}.report.active{display:block}}
</style></head><body><main class="shell"><header class="top"><div class="row"><div><div class="title">__TITLE__</div><div class="meta">先看企业质量，再看估值位置，最后核对关键条件</div></div><div class="tabs" role="tablist" aria-label="报告视图"><button class="tab" id="tab-quality" role="tab" aria-selected="true" aria-controls="quality">01 财务质量</button><button class="tab" id="tab-valuation" role="tab" aria-selected="false" aria-controls="valuation">02 扣非PE估值</button></div></div><div class="decision">__SUMMARY__</div><div class="notice">最新TTM异常先视为待验证信号；财务质量不等同于投资价值，估值信号不等同于价格预测。</div></header><section class="stage"><div class="loading" id="loading">正在载入报告…</div><iframe class="report active" id="quality" title="财务质量报告"></iframe><iframe class="report" id="valuation" title="扣非PE估值报告"></iframe><noscript><div class="noscript">需要启用浏览器JavaScript才能切换报告。</div></noscript></section></main>
<script>
const encoded=__PAYLOADS__;const loaded={};const decoder=new TextDecoder('utf-8');
function decode64(s){const b=atob(s),a=new Uint8Array(b.length);for(let i=0;i<b.length;i++)a[i]=b.charCodeAt(i);return decoder.decode(a)}
function load(id){if(loaded[id])return;document.getElementById(id).srcdoc=decode64(encoded[id]);loaded[id]=true}
function show(id){load(id);for(const name of ['quality','valuation']){const active=name===id;document.getElementById(name).classList.toggle('active',active);const tab=document.getElementById('tab-'+name);tab.setAttribute('aria-selected',String(active));tab.tabIndex=active?0:-1}document.getElementById('loading').style.display='none'}
for(const id of ['quality','valuation'])document.getElementById('tab-'+id).addEventListener('click',()=>show(id));
document.querySelector('.tabs').addEventListener('keydown',e=>{if(!['ArrowLeft','ArrowRight'].includes(e.key))return;e.preventDefault();const next=document.getElementById('quality').classList.contains('active')?'valuation':'quality';show(next);document.getElementById('tab-'+next).focus()});
show('quality');
</script></body></html>'''
    document = document.replace("__TITLE__", html.escape(title)).replace("__SUMMARY__", summary_html).replace(
        "__PAYLOADS__", json.dumps(payloads, ensure_ascii=True)
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(document, encoding="utf-8")

    manifest_path = args.manifest or args.output.with_name(args.output.stem.replace("_dashboard", "_manifest") + ".json")
    manifest = {
        "company": {"name": args.name, "code": args.code},
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "combined_html": str(args.output.resolve()),
        "financial_quality_html": str(args.quality_html.resolve()),
        "valuation_html": str(args.valuation_html.resolve()),
        "valuation_basis": "deducted PE TTM",
        "offline": True,
        "checks": {"quality_html_nonempty": True, "valuation_html_nonempty": True},
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(args.output.resolve())


if __name__ == "__main__":
    main()
