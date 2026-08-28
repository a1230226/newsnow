#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每日金融简报(v4.1最终版+UA修复)：23品种真实行情全覆盖 + 规则定方向 + 情绪统计 + 受限AI"""
import json, os, re, urllib.request, urllib.parse, sys
from datetime import datetime, timezone, timedelta

BASE     = os.environ["NEWSNOW_BASE"].rstrip("/")
CF_TOKEN = os.environ["CF_API_TOKEN"]
CF_ACC   = os.environ["CF_ACCOUNT_ID"]
CF_MODEL = os.environ.get("CF_MODEL", "@cf/meta/llama-3.3-70b-instruct-fp8-fast")
SCT_KEY  = os.environ["SCT_KEY"]

KEYWORDS = {
    "螺纹钢": ["螺纹钢","螺纹","期螺","沪螺","粗钢","限产","钢铁"],
    "铁矿石": ["铁矿石","铁矿","普氏","澳矿","高炉"],
    "焦煤":   ["焦煤","蒙煤","澳煤"],
    "焦炭":   ["焦炭","焦化","焦企","提涨","提降"],
    "铜":     ["沪铜","期铜","电解铜","伦铜","LME","铜矿","铜"],
    "铝":     ["沪铝","期铝","电解铝","氧化铝","铝锭"],
    "黄金":   ["黄金","金价","沪金","COMEX","伦敦金","央行购金"],
    "白银":   ["白银","银价","沪银","金银比"],
    "原油":   ["原油","布伦特","WTI","OPEC","EIA","伊朗","石油"],
    "PTA":    ["PTA","PX","聚酯","涤纶"],
    "甲醇":   ["甲醇","煤制甲醇"],
    "纯碱":   ["纯碱","轻碱","重碱"],
    "玻璃":   ["玻璃","浮法玻璃","沙河"],
    "豆粕":   ["豆粕","美豆","大豆","USDA","压榨"],
    "豆油":   ["豆油","大豆油"],
    "棕榈油": ["棕榈油","马棕","MPOB","生柴"],
    "白糖":   ["白糖","原糖","ICE糖","开榨","收榨"],
    "棉花":   ["棉花","郑棉","新疆棉","纺织"],
    "玉米":   ["玉米","新粮","陈粮","售粮"],
    "生猪":   ["生猪","猪价","能繁母猪","猪粮比"],
    "鸡蛋":   ["鸡蛋","蛋价","淘鸡"],
    "工业硅": ["工业硅","多晶硅","硅料","有机硅"],
    "碳酸锂": ["碳酸锂","锂价","锂矿","盐湖"],
}
SPECIFIC = {
    "螺纹钢": (["限产","压减","去库","降库","收储","挺价"], ["增产","复产","扩产","累库","补库","抛售"]),
    "铁矿石": (["发运下降","港口库存下降","矿山事故","停运"], ["发运回升","累库"]),
    "焦煤":   (["安监","通关下降"], ["提降","通关回升"]),
    "焦炭":   (["提涨"], ["提降"]),
    "铜":     (["罢工","TC下降","库存下降","供给中断","矿"], ["美元走强","抛售"]),
    "铝":     (["封存","限电"], ["复产"]),
    "黄金":   (["央行购金","实际利率下行","避险","降息"], ["加息","实际利率上行","限制","收紧","缩表"]),
    "白银":   (["光伏","金银比"], []),
    "原油":   (["制裁","停运","袭击","供应中断","紧张","出口下降"], ["增产","出口恢复","扫清","缓解","通航","协议达成"]),
    "豆粕":   (["USDA下调","关税","天气"], ["USDA上调"]),
    "棕榈油": (["出口增长","MPOB下调","生柴","厄尔尼诺"], ["出口下滑"]),
    "碳酸锂": (["排产回升"], ["排产下滑","盐湖放量"]),
}
GENERIC = {
    "利好": ["上涨","大涨","走高","走强","反弹","回升","攀升","创新高","涨停","提价","涨价",
             "减产","停产","检修","收储","去库","降库","限产","制裁","停运","紧张","地缘","避险","降息","短缺","紧缺"],
    "利空": ["下跌","大跌","走低","走弱","回落","跳水","创新低","跌停","降价","抛售",
             "增产","复产","扩产","累库","补库","需求疲软","缓解","加息","缩表","美元走强","抛储","过剩"],
}
EXCLUDE = {"玻璃": ["玻璃纤维"]}
FS = "m:113,m:114,m:115,m:142,m:225"
NAME_FIX = {"沪铜": "铜", "沪铝": "铝", "沪银": "白银", "沪金": "黄金",
            "沪铅": "铅", "沪锡": "锡", "沪锌": "锌", "沪镍": "镍"}

def _http_text(url, headers, timeout=20):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")

def fetch_quotes():
    hdrs = {"Referer": "https://quote.eastmoney.com/", "User-Agent": "Mozilla/5.0"}
    rows = []
    for pn in range(1, 13):
        try:
            url = (f"https://push2delay.eastmoney.com/api/qt/clist/get?pn={pn}&pz=100&po=1&np=1&fltt=2&invt=2&fid=f3"
                   f"&fs={FS}&fields=f2,f3,f12,f14")
            d = json.loads(_http_text(url, hdrs))
        except Exception:
            break
        diff = (d.get("data") or {}).get("diff") or []
        if not diff:
            break
        rows += diff
    quotes, movers = {}, []
    for it in rows:
        nm = it.get("f14") or ""
        if not nm.endswith("主连") or "次主连" in nm:
            continue
        base = nm[:-2]
        for p, s in NAME_FIX.items():
            if base.startswith(p):
                base = s + base[len(p):]
        quotes[base] = {"p": it.get("f2"), "zdf": it.get("f3")}
        if it.get("f3") is not None and it.get("f2") is not None:
            movers.append((nm, it.get("f2"), it.get("f3")))
    movers.sort(key=lambda x: x[2], reverse=True)
    return quotes, movers

def fetch_body(url, maxlen=120):
    if not url:
        return None
    try:
        html = _http_text(url, {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/"}, timeout=10)
    except Exception:
        return None
    html = re.sub(r'<script.*?</script>', ' ', html, flags=re.S)
    html = re.sub(r'<style.*?</style>', ' ', html, flags=re.S)
    m = re.search(r'<title>【金十数据】(.*?)\s*-\s*金十数据</title>', html, re.S)
    if m:
        return m.group(1).strip()[:maxlen] or None
    m = re.search(r'id="ContentBody"', html)
    if m:
        chunk = html[m.end():m.end() + 3000]
        t = re.sub(r'<[^>]+>', ' ', chunk)
        t = re.sub(r'\s+', ' ', t).strip()
        return t[:maxlen] if len(t) >= 10 else None
    m = re.search(r'<title>(.*?)</title>', html, re.S)
    if m:
        t = m.group(1).strip()
        return t[:maxlen] if len(t) >= 10 else None
    return None

SOURCES = ["cls-telegraph", "jin10", "wallstreetcn-quick", "xueqiu-hotstock", "myeastmoney"]

def http_json(url, data=None, headers=None, method=None):
    h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))

news = {}
for sid in SOURCES:
    try:
        j = http_json(f"{BASE}/api/s?id={sid}&latest=false")
        for it in j.get("items", []):
            t = (it.get("title") or "").strip()
            if t and t not in news:
                news[t] = {"source": sid, "title": t, "url": it.get("url", "")}
    except Exception as e:
        print(f"[warn] {sid} 抓取失败: {e}")

items = list(news.values())[:15]
if not items:
    print("无新闻，退出"); sys.exit(1)

for it in items[:5]:
    if it["source"] == "jin10":
        it["body"] = it["title"][:120]
    else:
        it["body"] = fetch_body(it["url"])

def analyze_news(title):
    hits = []
    for v, kws in KEYWORDS.items():
        if any(e in title for e in EXCLUDE.get(v, [])):
            continue
        kw = [k for k in kws if k in title]
        if not kw:
            continue
        d, dw = "中性", []
        sp = SPECIFIC.get(v, ([], []))
        for direction, words in (("利好", sp[0]), ("利空", sp[1])):
            h = [w for w in words if w in title]
            if h:
                d, dw = direction, h
                break
        if d == "中性":
            for direction, words in (("利好", GENERIC["利好"]), ("利空", GENERIC["利空"])):
                h = [w for w in words if w in title]
                if h:
                    d, dw = direction, h
                    break
        hits.append((v, d, kw, dw))
    return hits

def ai_analyze(prompt):
    body = json.dumps({"messages": [
        {"role": "system", "content": "你是金融新闻分析助手。对每条新闻写：reason(1句逻辑说明，必须基于提供的标题和正文摘录，禁止编造任何数字、价格、百分比、事件、目标价位) 和 outlook(1句定性前瞻，禁止任何数字和价位)。信息不足写'信息不足，需进一步核实'。只输出JSON数组。"},
        {"role": "user", "content": prompt},
    ]}).encode("utf-8")
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACC}/ai/run/{CF_MODEL}"
    j = http_json(url, data=body, headers={"Authorization": f"Bearer {CF_TOKEN}", "Content-Type": "application/json"})
    return j["result"]["response"]

def make_prompt(n):
    lines = []
    for i in items[:n]:
        b = i.get("body") or ""
        lines.append(f"- [{i['source']}] {i['title']}" + (f"（正文摘录:{b}）" if b else "（无正文）"))
    return f"""逐条分析以下 {n} 条财经新闻，输出JSON数组，每条字段:
title(原标题), reason(1句逻辑,基于事实,禁数字), outlook(1句定性前瞻,禁数字)
新闻:
{'\n'.join(lines)}"""

rows = []
try:
    raw = ai_analyze(make_prompt(10)).strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    rows = json.loads(raw)
except Exception:
    try:
        raw = ai_analyze(make_prompt(8)).strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        rows = json.loads(raw)
    except Exception:
        rows = []

quotes, movers = fetch_quotes()
bj = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")

if not movers:
    sentiment, sent_desc = "无法统计", "行情获取失败，情绪无法计算"
else:
    ups = sum(1 for _, _, z in movers if z > 0)
    downs = sum(1 for _, _, z in movers if z < 0)
    if ups >= 2 * downs and ups >= 4:
        sentiment, sent_desc = "偏乐观", f"全市场主连 涨{ups}家 / 跌{downs}家"
    elif downs >= 2 * ups and downs >= 4:
        sentiment, sent_desc = "偏谨慎", f"全市场主连 涨{ups}家 / 跌{downs}家"
    else:
        sentiment, sent_desc = "中性", f"全市场主连 涨{ups}家 / 跌{downs}家"

up3 = [m for m in movers if m[2] > 0][:3]
down3 = [m for m in movers if m[2] < 0][-3:][::-1]
big = [(n, p, z) for n, p, z in movers if abs(z) >= 1.5]

md = ["# 📰 每日金融新闻简报（v4.1最终版）",
      f"生成时间: 北京时间 {bj}",
      "> ⚠️ 行情为最近收盘/夜盘数据（非实时盘中）；数字来自东财真实接口（23品种全覆盖），方向判定为规则命中（可核对），AI 不参与编数。", ""]
md.append("## 📊 行情快照（真实数据·23品种）")
md.append("| 品种 | 最新价 | 涨跌幅 |")
md.append("|---|---|---|")
for name in KEYWORDS:
    q = quotes.get(name)
    if q and q["p"] is not None and q["zdf"] is not None:
        arrow = "▲" if q["zdf"] > 0 else ("▼" if q["zdf"] < 0 else "—")
        md.append(f"| {name} | {q['p']:.0f} | {arrow}{abs(q['zdf']):.2f}% |")
    else:
        md.append(f"| {name} | — | 获取失败 |")
md.append("")
md.append(f"## 📈📉 市场情绪（真实数据统计）：{sentiment}")
md.append(f"- {sent_desc}")
md.append("")
md.append("## 🎯 规则前瞻（基于真实涨跌幅）")
if up3:
    md.append("- " + "、".join(n for n, _, _ in up3) + " 领涨，短期偏强，关注冲高回落风险")
if down3:
    md.append("- " + "、".join(n for n, _, _ in down3) + " 领跌，短期偏弱，关注超跌反抽可能")
if big:
    md.append(f"- 波动≥1.5%品种 {len(big)} 个（{'、'.join(n for n, _, _ in big[:5])}…），波动加剧，注意仓位风险")
md.append("")
md.append("## 📰 新闻×方向（规则判定·命中词可核对）")
for i, it in enumerate(items[:10], 1):
    hits = analyze_news(it["title"])
    if hits:
        parts = []
        for v, d, kw, dw in hits:
            mark = "📈利好" if d == "利好" else ("📉利空" if d == "利空" else "➡️中性")
            parts.append(f"{v}{mark}(品种词:{'/'.join(kw)},{'方向词:' + '/'.join(dw) if dw else '无方向词'})")
        rule_txt = "；".join(parts)
    else:
        rule_txt = "未匹配到品种（中性，不硬猜）"
    ai = next((r for r in rows if r.get("title") == it["title"]), None)
    summary = it.get("body") or it["title"][:80]
    md.append(f"### {i}. {it['title']}")
    md.append(f"- 🧭 规则判定：{rule_txt}")
    md.append(f"- 📝 摘要（真实正文/标题）：{summary}")
    md.append(f"- 🔗 逻辑：{ai.get('reason', '—') if ai else '—'}")
    md.append(f"- 🔭 前瞻：{ai.get('outlook', '—') if ai else '—'}")
    md.append("")
brief = "\n".join(md)
print(brief[:500])
with open(os.environ.get("GITHUB_STEP_SUMMARY", "/dev/null"), "a", encoding="utf-8") as f:
    f.write(brief)

if SCT_KEY:
    data2 = urllib.parse.urlencode({"title": "📰 每日金融新闻简报（v4.1最终版）", "desp": brief}).encode()
    http_json(f"https://sctapi.ftqq.com/{SCT_KEY}.send", data=data2,
              headers={"Content-Type": "application/x-www-form-urlencoded"})
    print("已推送到微信")
