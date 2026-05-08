#!/usr/bin/env python3
"""
灵构 AI 资讯 RSS 生成器
数据来源：aihot.virxact.com
每次运行拉取最近 24 小时精选，按灵构视角过滤，生成 feed.xml
"""

import json
import re
import os
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

# ── 配置 ──────────────────────────────────────────────────────────────────────

BASE_URL = "https://aihot.virxact.com/api/public"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# GitHub Pages 部署后的公网地址，从环境变量读（Actions 里自动注入）
SITE_URL = os.environ.get("SITE_URL", "https://your-username.github.io/linggou-rss")

# 北京时间
CST = timezone(timedelta(hours=8))

# ── 灵构关键词规则 ────────────────────────────────────────────────────────────

KEYWORDS = {
    "aigc_content": [
        "短剧", "微短剧", "AI剧", "AI 剧", "漫剧", "AIGC影视", "AIGC 影视",
        "AI视频", "AI 视频", "Sora", "Runway", "Kling", "可灵", "即梦", "Vidu",
        "PixVerse", "视频生成", "分镜", "脚本生成", "IP", "虚拟角色", "数字人",
        "配音", "AI配音", "文生视频", "图生视频", "影视生成", "动漫", "AI漫画",
        "条漫", "绘本", "故事生成", "剧本", "Wan", "混元", "海螺"
    ],
    "tech_tools": [
        "3D", "三维", "模型生成", "资产生成", "NeRF", "Gaussian", "point cloud",
        "mesh", "纹理生成", "贴图", "Blender", "Unity", "Unreal", "游戏引擎",
        "图像生成", "ComfyUI", "LoRA", "风格化", "角色生成", "场景生成",
        "世界模型", "Flux", "Stable Diffusion", "Midjourney", "骨骼", "动捕",
        "重建", "三维重建", "Avatar", "虚拟形象", "AI绘画", "AI 绘画",
        "文生图", "图生图", "Tripo", "Rodin", "Meshy", "CSM", "Hyper3D"
    ],
    "industry": [
        "融资", "版权", "授权", "商业化", "平台政策", "游戏", "XR", "AR", "VR",
        "Vision Pro", "元宇宙", "文旅", "IP授权", "IP 授权", "竞品", "内容平台",
        "抖音", "快手", "B站", "小红书", "字节", "腾讯游戏", "网易游戏",
        "米哈游", "莉莉丝", "二次元", "次世代", "AIGC监管", "生成式AI",
        "版权保护", "内容审核", "创作者", "变现"
    ]
}

def fetch(path, params=None):
    url = f"{BASE_URL}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())

def match_category(item):
    """返回匹配的灵构分类，优先级：aigc_content > tech_tools > industry > None"""
    text = " ".join(filter(None, [
        item.get("title", ""),
        item.get("title_en", ""),
        item.get("summary", ""),
    ])).lower()

    for cat in ["aigc_content", "tech_tools", "industry"]:
        for kw in KEYWORDS[cat]:
            if kw.lower() in text:
                return cat
    return None

def to_cst(iso_str):
    """ISO UTC 字符串转北京时间 datetime"""
    if not iso_str:
        return None
    iso_str = iso_str.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.astimezone(CST)
    except Exception:
        return None

def fmt_time_human(dt):
    """转成人话时间：今天 14:30 / 昨天 09:15"""
    if not dt:
        return ""
    now = datetime.now(CST)
    delta = now - dt
    if delta.days == 0:
        return f"今天 {dt.strftime('%H:%M')}"
    elif delta.days == 1:
        return f"昨天 {dt.strftime('%H:%M')}"
    else:
        return dt.strftime("%m/%d %H:%M")

def fmt_rfc2822(dt):
    """RSS pubDate 格式"""
    if not dt:
        return datetime.now(CST).strftime("%a, %d %b %Y %H:%M:%S +0800")
    return dt.strftime("%a, %d %b %Y %H:%M:%S +0800")

CAT_META = {
    "aigc_content": {
        "label": "📽️ AIGC 内容创作",
        "desc": "短剧/漫剧/AI影视制作相关",
        "tag": "AIGC内容创作"
    },
    "tech_tools": {
        "label": "🛠️ 技术工具",
        "desc": "3D生成、AI影视制作工具、新模型",
        "tag": "技术工具"
    },
    "industry": {
        "label": "📊 行业动态",
        "desc": "市场、融资、竞品、平台政策",
        "tag": "行业动态"
    },
}

def build_item_html(item, cat):
    """生成单条资讯的 RSS description HTML"""
    meta = CAT_META[cat]
    title = item.get("title") or item.get("title_en") or "（无标题）"
    source = item.get("source", "")
    summary = item.get("summary", "")
    url = item.get("url", "")
    pub_dt = to_cst(item.get("publishedAt"))
    time_str = fmt_time_human(pub_dt)

    lines = [
        f"<p><strong>{meta['label']}</strong> · {time_str} · {source}</p>",
    ]
    if summary:
        lines.append(f"<p>{summary}</p>")
    if url:
        lines.append(f'<p><a href="{url}">→ 查看原文</a></p>')
    return "\n".join(lines)

def generate_rss(linggou_items, all_items, generated_at, social_topics=None):
    """生成完整 RSS XML"""
    rss = Element("rss", version="2.0", **{"xmlns:atom": "http://www.w3.org/2005/Atom"})
    channel = SubElement(rss, "channel")

    # channel meta
    SubElement(channel, "title").text = "灵构 AI 资讯"
    SubElement(channel, "link").text = SITE_URL
    SubElement(channel, "description").text = "每日 AI HOT 精选，灵构视角过滤 · 3D资产/AIGC影视/游戏/XR/社媒运营"
    SubElement(channel, "language").text = "zh-CN"
    SubElement(channel, "lastBuildDate").text = fmt_rfc2822(generated_at)
    SubElement(channel, "ttl").text = "60"
    atom_link = SubElement(channel, "atom:link")
    atom_link.set("href", f"{SITE_URL}/feed.xml")
    atom_link.set("rel", "self")
    atom_link.set("type", "application/rss+xml")

    # ── 灵构视角汇总条目（置顶，1条聚合） ────────────────────────────────────
    if linggou_items:
        item_el = SubElement(channel, "item")
        date_str = generated_at.strftime("%m月%d日")
        SubElement(item_el, "title").text = f"🏗️ 灵构视角 · {date_str} · 共{len(linggou_items)}条"
        SubElement(item_el, "link").text = SITE_URL
        SubElement(item_el, "guid", isPermaLink="false").text = f"linggou-digest-{generated_at.strftime('%Y%m%d%H')}"
        SubElement(item_el, "pubDate").text = fmt_rfc2822(generated_at)

        # 按分类分组
        grouped = {"aigc_content": [], "tech_tools": [], "industry": []}
        for it, cat in linggou_items:
            grouped[cat].append(it)

        html_parts = ["<h2>🏗️ 灵构视角</h2>",
                      "<p>从 AI HOT 今日精选中提取，与灵构（3D资产中心）高度相关的内容。</p>"]

        for cat in ["aigc_content", "tech_tools", "industry"]:
            items_in_cat = grouped[cat]
            if not items_in_cat:
                continue
            meta = CAT_META[cat]
            html_parts.append(f"<h3>{meta['label']}</h3>")
            for i, it in enumerate(items_in_cat, 1):
                t = it.get("title") or it.get("title_en") or "（无标题）"
                src = it.get("source", "")
                smr = it.get("summary", "")
                url = it.get("url", "")
                pub_dt = to_cst(it.get("publishedAt"))
                time_str = fmt_time_human(pub_dt)
                html_parts.append(f"<p><strong>{i}. {t}</strong><br/>")
                html_parts.append(f"<small>{src} · {time_str}</small></p>")
                if smr:
                    html_parts.append(f"<p>{smr}</p>")
                if url:
                    html_parts.append(f'<p><a href="{url}">→ 查看原文</a></p>')
                html_parts.append("<hr/>")

        SubElement(item_el, "description").text = "\n".join(html_parts)

    # ── 社媒选题（必出，紧跟灵构视角之后） ──────────────────────────────────
    if social_topics:
        item_el = SubElement(channel, "item")
        date_str = generated_at.strftime("%m月%d日")
        SubElement(item_el, "title").text = f"💡 本周社媒选题建议 · {date_str} · 共{len(social_topics)}条"
        SubElement(item_el, "link").text = SITE_URL
        SubElement(item_el, "guid", isPermaLink="false").text = f"linggou-topics-{generated_at.strftime('%Y%m%d%H')}"
        SubElement(item_el, "pubDate").text = fmt_rfc2822(generated_at)
        SubElement(item_el, "category").text = "社媒选题"

        html_parts = [
            "<h2>💡 本周社媒选题建议</h2>",
            "<p>基于今日灵构视角资讯，提炼适合小红书/抖音/B站发布的选题角度。</p>",
        ]
        for i, topic in enumerate(social_topics, 1):
            t = topic.get("title", "")
            platforms = "、".join(topic.get("platform", []))
            hook = topic.get("hook", "")
            direction = topic.get("direction", "")
            html_parts.append(f"<h3>选题 {i}：{t}</h3>")
            html_parts.append(f"<p>📱 <strong>平台</strong>：{platforms}</p>")
            if hook:
                html_parts.append(f"<p>🎯 <strong>切入角度</strong>：{hook}</p>")
            if direction:
                html_parts.append(f"<p>💡 <strong>内容方向</strong>：{direction}</p>")
            html_parts.append("<hr/>")

        SubElement(item_el, "description").text = "\n".join(html_parts)

    # ── 灵构相关单条条目（每条单独一个 RSS item） ─────────────────────────────
    for it, cat in linggou_items:
        item_el = SubElement(channel, "item")
        title = it.get("title") or it.get("title_en") or "（无标题）"
        meta = CAT_META[cat]
        SubElement(item_el, "title").text = f"{meta['tag']} · {title}"
        url = it.get("url", SITE_URL)
        SubElement(item_el, "link").text = url
        SubElement(item_el, "guid", isPermaLink="false").text = f"linggou-{it.get('id', '')}"
        pub_dt = to_cst(it.get("publishedAt"))
        SubElement(item_el, "pubDate").text = fmt_rfc2822(pub_dt or generated_at)
        SubElement(item_el, "category").text = meta["tag"]
        SubElement(item_el, "description").text = build_item_html(it, cat)

    # ── AI HOT 完整精选（附在后面） ──────────────────────────────────────────
    for it in all_items:
        item_el = SubElement(channel, "item")
        title = it.get("title") or it.get("title_en") or "（无标题）"
        SubElement(item_el, "title").text = f"[AI HOT] {title}"
        url = it.get("url", SITE_URL)
        SubElement(item_el, "link").text = url
        SubElement(item_el, "guid", isPermaLink="false").text = f"aihot-{it.get('id', '')}"
        pub_dt = to_cst(it.get("publishedAt"))
        SubElement(item_el, "pubDate").text = fmt_rfc2822(pub_dt or generated_at)
        cat_en = it.get("category", "")
        if cat_en:
            SubElement(item_el, "category").text = cat_en
        smr = it.get("summary", "")
        src = it.get("source", "")
        desc_parts = []
        if src:
            desc_parts.append(f"<p><small>来源：{src}</small></p>")
        if smr:
            desc_parts.append(f"<p>{smr}</p>")
        if url:
            desc_parts.append(f'<p><a href="{url}">→ 查看原文</a></p>')
        SubElement(item_el, "description").text = "\n".join(desc_parts)

    xml_str = tostring(rss, encoding="unicode")
    dom = minidom.parseString(xml_str)
    return dom.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")

def generate_social_topics(linggou_items, all_items):
    """调用 DeepSeek API，基于灵构视角内容生成社媒选题，每次必出至少3条"""
    ds_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not ds_key:
        print("  [跳过社媒选题] 未找到 DEEPSEEK_API_KEY")
        return []

    # 整理灵构相关条目摘要
    items_text = []
    for it, cat in linggou_items[:15]:
        title = it.get("title") or it.get("title_en") or ""
        summary = it.get("summary") or ""
        items_text.append(f"[{CAT_META[cat]['tag']}] {title}\n{summary}")

    # 灵构相关条目不足5条时，补充全量精选里的内容
    if len(linggou_items) < 5:
        for it in all_items[:20]:
            title = it.get("title") or it.get("title_en") or ""
            summary = it.get("summary") or ""
            items_text.append(f"[AI动态] {title}\n{summary}")

    prompt = f"""你是一个服务于「灵构」品牌的社媒内容策划。

灵构是一个 3D 模型资产中心，服务于 AI 短剧、AI 漫剧、游戏、XR、文旅等内容产业。灵构同时在运营小红书、抖音、B站账号，每周需要持续输出内容。

以下是今日 AI HOT 资讯中与灵构相关的内容：

{chr(10).join(items_text[:12])}

请基于以上资讯，生成至少 3 条社媒选题。每条选题必须包含：
1. title: 直接可用的帖子标题（有钩子，不是描述性标题）
2. platform: 最适合的平台（小红书/抖音/B站，可多选）
3. hook: 用户会点开的理由（一句话，站在创作者/从业者视角）
4. direction: 内容大概怎么写/拍（2-3句话）

只输出 JSON 数组，格式如下，不要有任何其他文字：
[
  {{
    "title": "...",
    "platform": ["小红书", "抖音"],
    "hook": "...",
    "direction": "..."
  }}
]"""

    try:
        req_data = json.dumps({
            "model": "deepseek-chat",
            "max_tokens": 1000,
            "messages": [{"role": "user", "content": prompt}]
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.deepseek.com/v1/chat/completions",
            data=req_data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {ds_key}"
            }
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            text = result["choices"][0]["message"]["content"].strip()
            # 清理可能的 markdown 代码块
            text = re.sub(r"```json|```", "", text).strip()
            topics = json.loads(text)
            print(f"  已生成社媒选题 {len(topics)} 条")
            return topics
    except Exception as e:
        print(f"  [社媒选题生成失败] {e}")
        return []


def main():
    now = datetime.now(CST)
    since_dt = datetime.now(timezone.utc) - timedelta(hours=24)
    since = since_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"[{now.strftime('%Y-%m-%d %H:%M CST')}] 拉取 AI HOT 精选（since={since}）...")

    data = fetch("/items", {"mode": "selected", "since": since, "take": 80})
    all_items = data.get("items", [])
    print(f"  共获取 {len(all_items)} 条精选")

    # 灵构过滤
    linggou_items = []
    seen_ids = set()
    for it in all_items:
        cat = match_category(it)
        if cat and it.get("id") not in seen_ids:
            linggou_items.append((it, cat))
            seen_ids.add(it.get("id"))

    print(f"  灵构相关 {len(linggou_items)} 条")
    for it, cat in linggou_items:
        print(f"    [{CAT_META[cat]['tag']}] {it.get('title', '')[:50]}")

    # 生成社媒选题（每次必出）
    print("  生成社媒选题...")
    social_topics = generate_social_topics(linggou_items, all_items)

    xml_content = generate_rss(linggou_items, all_items, now, social_topics)

    output_path = os.path.join(os.path.dirname(__file__), "feed.xml")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(xml_content)

    print(f"  已写入 feed.xml（{len(xml_content)} 字节）")

    # 写入选题 JSON（供 index.html 单独展示）
    if social_topics:
        topics_path = os.path.join(os.path.dirname(__file__), "social_topics.json")
        with open(topics_path, "w", encoding="utf-8") as f:
            json.dump({
                "generated_at": now.isoformat(),
                "topics": social_topics
            }, f, ensure_ascii=False, indent=2)
        print(f"  已写入 social_topics.json")

    # 生成简单的 last_updated 文件，供 index.html 读取
    meta = {
        "generated_at": now.isoformat(),
        "total": len(all_items),
        "linggou": len(linggou_items),
        "social_topics": len(social_topics),
        "categories": {
            cat: sum(1 for _, c in linggou_items if c == cat)
            for cat in ["aigc_content", "tech_tools", "industry"]
        }
    }
    with open(os.path.join(os.path.dirname(__file__), "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print("  已写入 meta.json")

if __name__ == "__main__":
    main()
