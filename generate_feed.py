#!/usr/bin/env python3
"""
灵构 AI 资讯 RSS 生成器
数据来源：AI HOT (aihot.virxact.com) + 中文媒体 RSS 补充源
工作日每天推送一次（周末内容累积到周一）
"""

import json
import re
import os
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom
from email.utils import parsedate_to_datetime

# ── 配置 ──────────────────────────────────────────────────────────────────────

BASE_URL = "https://aihot.virxact.com/api/public"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
SITE_URL = os.environ.get("SITE_URL", "https://your-username.github.io/linggou-rss")
CST = timezone(timedelta(hours=8))

# ── 补充 RSS 源（中文媒体）────────────────────────────────────────────────────
# 只拉与灵构相关领域的专栏/标签 RSS，减少噪音

EXTRA_RSS_SOURCES = [
    {
        "name": "量子位",
        "url": "https://www.qbitai.com/feed",
        "source_tag": "量子位"
    },
    {
        "name": "机器之心",
        "url": "https://www.jiqizhixin.com/rss",
        "source_tag": "机器之心"
    },
    {
        "name": "36氪·AI",
        "url": "https://36kr.com/feed",
        "source_tag": "36氪"
    },
]

# ── 灵构关键词规则（扩充版）──────────────────────────────────────────────────

KEYWORDS = {
    "aigc_content": [
        "短剧", "微短剧", "AI剧", "AI 剧", "漫剧", "AIGC影视", "AIGC 影视",
        "AI视频", "AI 视频", "Sora", "Runway", "Kling", "可灵", "即梦", "Vidu",
        "PixVerse", "视频生成", "分镜", "脚本生成", "虚拟角色", "数字人",
        "配音", "AI配音", "文生视频", "图生视频", "影视生成", "动漫", "AI漫画",
        "条漫", "绘本", "故事生成", "剧本", "Wan", "混元", "海螺",
        "AI动画", "动画生成", "二次元", "漫画生成", "分镜脚本", "AI创作",
        "内容创作", "创作工具", "AIGC创作", "视频制作", "影视制作",
    ],
    "tech_tools": [
        "3D", "三维", "模型生成", "资产生成", "NeRF", "Gaussian", "point cloud",
        "mesh", "纹理生成", "贴图", "Blender", "Unity", "Unreal", "游戏引擎",
        "图像生成", "ComfyUI", "LoRA", "风格化", "角色生成", "场景生成",
        "世界模型", "Flux", "Stable Diffusion", "Midjourney", "骨骼", "动捕",
        "重建", "三维重建", "Avatar", "虚拟形象", "AI绘画", "AI 绘画",
        "文生图", "图生图", "Tripo", "Rodin", "Meshy", "CSM", "Hyper3D",
        "Trellis", "InstantMesh", "Zero123", "OpenPose", "ControlNet",
        "资产管理", "3D资产", "模型库", "素材库", "PBR", "渲染",
    ],
    "industry": [
        "融资", "版权", "授权", "商业化", "平台政策", "游戏", "XR", "AR", "VR",
        "Vision Pro", "元宇宙", "文旅", "IP授权", "IP 授权", "内容平台",
        "抖音", "快手", "B站", "小红书", "字节", "腾讯游戏", "网易游戏",
        "米哈游", "莉莉丝", "次世代", "AIGC监管", "生成式AI",
        "版权保护", "内容审核", "创作者经济", "变现", "工作流",
        "影视行业", "游戏行业", "动漫行业", "出海", "AI产业",
        "数字内容", "内容生态", "平台生态",
    ]
}

def fetch_aihot(since, take=100):
    """拉取 AI HOT 精选"""
    url = f"{BASE_URL}/items?" + urllib.parse.urlencode({
        "mode": "selected", "since": since, "take": take
    })
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            items = data.get("items", [])
            print(f"  AI HOT: 获取 {len(items)} 条")
            return items
    except Exception as e:
        print(f"  AI HOT 拉取失败: {e}")
        return []

def fetch_extra_rss(source, since_dt):
    """拉取补充 RSS 源，返回标准化 item 列表"""
    items = []
    try:
        req = urllib.request.Request(source["url"], headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read()
        root = ET.fromstring(content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        # 兼容 RSS 2.0 和 Atom
        entries = root.findall(".//item") or root.findall(".//atom:entry", ns)
        count = 0
        for entry in entries[:30]:
            title = (entry.findtext("title") or
                     entry.findtext("atom:title", namespaces=ns) or "")
            link  = (entry.findtext("link") or
                     entry.findtext("atom:link", namespaces=ns) or
                     (entry.find("atom:link", ns).get("href") if entry.find("atom:link", ns) is not None else ""))
            desc  = (entry.findtext("description") or
                     entry.findtext("atom:summary", namespaces=ns) or
                     entry.findtext("atom:content", namespaces=ns) or "")
            pub   = (entry.findtext("pubDate") or
                     entry.findtext("atom:published", namespaces=ns) or "")

            # 清理 HTML 标签
            desc_clean = re.sub(r"<[^>]+>", "", desc).strip()[:300]

            # 解析时间
            pub_dt = None
            if pub:
                try:
                    pub_dt = parsedate_to_datetime(pub)
                except Exception:
                    try:
                        pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                    except Exception:
                        pass

            # 只保留 since_dt 之后的
            if pub_dt and pub_dt.astimezone(timezone.utc) < since_dt:
                continue

            items.append({
                "id": f"extra-{source['source_tag']}-{hash(link)}",
                "title": title.strip(),
                "title_en": "",
                "summary": desc_clean,
                "url": link,
                "source": source["source_tag"],
                "publishedAt": pub_dt.isoformat() if pub_dt else "",
                "_extra": True,
            })
            count += 1

        print(f"  {source['name']}: 获取 {count} 条（时间窗内）")
    except Exception as e:
        print(f"  {source['name']} 拉取失败: {e}")
    return items

def match_category(item):
    """返回匹配的灵构分类"""
    text = " ".join(filter(None, [
        item.get("title", ""),
        item.get("title_en", ""),
        item.get("summary", ""),
    ]))
    text_lower = text.lower()

    for cat in ["aigc_content", "tech_tools", "industry"]:
        for kw in KEYWORDS[cat]:
            if kw.lower() in text_lower:
                return cat
    return None

def to_cst(iso_str):
    if not iso_str:
        return None
    iso_str = iso_str.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.astimezone(CST)
    except Exception:
        return None

def fmt_time_human(dt):
    if not dt:
        return ""
    now = datetime.now(CST)
    delta = now - dt
    if delta.days == 0:
        return f"今天 {dt.strftime('%H:%M')}"
    elif delta.days == 1:
        return f"昨天 {dt.strftime('%H:%M')}"
    elif delta.days <= 3:
        return f"{delta.days}天前"
    else:
        return dt.strftime("%m/%d %H:%M")

def fmt_rfc2822(dt):
    if not dt:
        return datetime.now(CST).strftime("%a, %d %b %Y %H:%M:%S +0800")
    return dt.strftime("%a, %d %b %Y %H:%M:%S +0800")

CAT_META = {
    "aigc_content": {"label": "📽️ AIGC 内容创作", "tag": "AIGC内容创作"},
    "tech_tools":   {"label": "🛠️ 技术工具",      "tag": "技术工具"},
    "industry":     {"label": "📊 行业动态",        "tag": "行业动态"},
}

SOURCE_LABELS = {
    "量子位": "量子位 QbitAI",
    "机器之心": "机器之心 Synced",
    "36氪": "36氪",
}

def build_item_html(item, cat):
    meta = CAT_META[cat]
    title  = item.get("title") or item.get("title_en") or "（无标题）"
    source = SOURCE_LABELS.get(item.get("source", ""), item.get("source", ""))
    summary = item.get("summary", "")
    url    = item.get("url", "")
    pub_dt = to_cst(item.get("publishedAt"))
    time_str = fmt_time_human(pub_dt)

    lines = [f"<p><strong>{meta['label']}</strong> · {time_str} · {source}</p>"]
    if summary:
        lines.append(f"<p>{summary}</p>")
    if url:
        lines.append(f'<p><a href="{url}">→ 查看原文</a></p>')
    return "\n".join(lines)

def generate_social_topics(linggou_items, all_items):
    """调用 DeepSeek API 生成社媒选题，要求可落地为 2000 字文章"""
    ds_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not ds_key:
        print("  [跳过社媒选题] 未找到 DEEPSEEK_API_KEY")
        return []

    items_text = []
    for it, cat in linggou_items[:15]:
        title   = it.get("title") or it.get("title_en") or ""
        summary = it.get("summary") or ""
        source  = it.get("source", "")
        items_text.append(f"[{CAT_META[cat]['tag']}·{source}] {title}\n{summary}")

    if len(linggou_items) < 5:
        for it in all_items[:15]:
            title   = it.get("title") or it.get("title_en") or ""
            summary = it.get("summary") or ""
            source  = it.get("source", "")
            items_text.append(f"[AI动态·{source}] {title}\n{summary}")

    prompt = f"""你是「灵构」品牌的资深社媒内容策划。

【灵构是什么】
灵构是一个 3D 模型资产中心，平台上的 3D 内容服务于 AI 短剧/漫剧制作、游戏开发、XR/文旅等场景。灵构正在孵化小红书、抖音、B站账号，面向的核心读者是：AIGC 内容创作者、独立游戏开发者、AI 影视从业者、对 AI 工具感兴趣的设计师。

【今日资讯】
{chr(10).join(items_text[:12])}

【任务】
基于以上资讯，生成 3 条社媒选题。每条选题必须满足：
1. 能展开写成一篇 1500-2000 字的干货文章或图文帖
2. 标题有明确的信息量，不是泛泛的"AI改变创作"这种空话
3. 内容框架里必须有具体的操作步骤、工具名称、或数据支撑

每条选题包含：
- title: 标题（直接可发，带数字/具体工具名/具体场景，≤25字）
- platform: 最适合平台（小红书/抖音/B站，选1-2个）
- hook: 读者痛点或好奇心（一句话，说清楚读者为什么要看这篇）
- outline: 文章大纲（列出4-6个具体段落标题，每个标题后面括号注明该段的核心内容）

只输出 JSON 数组，不要其他任何文字：
[
  {{
    "title": "...",
    "platform": ["小红书"],
    "hook": "...",
    "outline": ["## 段落1（内容说明）", "## 段落2（内容说明）", ...]
  }}
]"""

    try:
        req_data = json.dumps({
            "model": "deepseek-chat",
            "max_tokens": 1500,
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
            text = re.sub(r"```json|```", "", text).strip()
            topics = json.loads(text)
            print(f"  已生成社媒选题 {len(topics)} 条")
            return topics
    except Exception as e:
        print(f"  [社媒选题生成失败] {e}")
        return []

def generate_rss(linggou_items, all_items, generated_at, social_topics=None, time_window_desc=""):
    rss = Element("rss", version="2.0", **{"xmlns:atom": "http://www.w3.org/2005/Atom"})
    channel = SubElement(rss, "channel")

    SubElement(channel, "title").text = "灵构 AI 资讯"
    SubElement(channel, "link").text = SITE_URL
    SubElement(channel, "description").text = "灵构视角 AI 资讯 · 3D资产/AIGC影视/游戏/XR/社媒运营"
    SubElement(channel, "language").text = "zh-CN"
    SubElement(channel, "lastBuildDate").text = fmt_rfc2822(generated_at)
    SubElement(channel, "ttl").text = "60"
    atom_link = SubElement(channel, "atom:link")
    atom_link.set("href", f"{SITE_URL}/feed.xml")
    atom_link.set("rel", "self")
    atom_link.set("type", "application/rss+xml")

    date_str = generated_at.strftime("%m月%d日")

    # ── 灵构视角汇总 ──────────────────────────────────────────────────────────
    if linggou_items:
        item_el = SubElement(channel, "item")
        SubElement(item_el, "title").text = f"🏗️ 灵构视角 · {date_str}{time_window_desc} · 共{len(linggou_items)}条"
        SubElement(item_el, "link").text = SITE_URL
        SubElement(item_el, "guid", isPermaLink="false").text = f"linggou-digest-{generated_at.strftime('%Y%m%d%H')}"
        SubElement(item_el, "pubDate").text = fmt_rfc2822(generated_at)

        grouped = {"aigc_content": [], "tech_tools": [], "industry": []}
        for it, cat in linggou_items:
            grouped[cat].append(it)

        # 来源统计
        sources = {}
        for it, _ in linggou_items:
            src = it.get("source", "未知")
            sources[src] = sources.get(src, 0) + 1
        src_summary = "、".join(f"{s}({n}条)" for s, n in sorted(sources.items(), key=lambda x: -x[1]))

        html_parts = [
            f"<h2>🏗️ 灵构视角</h2>",
            f"<p><small>来源：{src_summary}</small></p>",
        ]

        for cat in ["aigc_content", "tech_tools", "industry"]:
            items_in_cat = grouped[cat]
            if not items_in_cat:
                continue
            meta = CAT_META[cat]
            html_parts.append(f"<h3>{meta['label']}</h3>")
            for i, it in enumerate(items_in_cat, 1):
                t       = it.get("title") or it.get("title_en") or "（无标题）"
                src     = SOURCE_LABELS.get(it.get("source",""), it.get("source",""))
                smr     = it.get("summary", "")
                url     = it.get("url", "")
                pub_dt  = to_cst(it.get("publishedAt"))
                time_str = fmt_time_human(pub_dt)
                html_parts.append(f"<p><strong>{i}. {t}</strong><br/><small>{src} · {time_str}</small></p>")
                if smr:
                    html_parts.append(f"<p>{smr}</p>")
                if url:
                    html_parts.append(f'<p><a href="{url}">→ 查看原文</a></p>')
                html_parts.append("<hr/>")

        SubElement(item_el, "description").text = "\n".join(html_parts)

    # ── 社媒选题 ──────────────────────────────────────────────────────────────
    if social_topics:
        item_el = SubElement(channel, "item")
        SubElement(item_el, "title").text = f"💡 社媒选题建议 · {date_str} · {len(social_topics)}条含大纲"
        SubElement(item_el, "link").text = SITE_URL
        SubElement(item_el, "guid", isPermaLink="false").text = f"linggou-topics-{generated_at.strftime('%Y%m%d%H')}"
        SubElement(item_el, "pubDate").text = fmt_rfc2822(generated_at)
        SubElement(item_el, "category").text = "社媒选题"

        html_parts = ["<h2>💡 社媒选题建议</h2>",
                      "<p>每条选题含完整大纲，可直接展开写 1500-2000 字文章。</p>"]
        for i, topic in enumerate(social_topics, 1):
            t         = topic.get("title", "")
            platforms = "、".join(topic.get("platform", []))
            hook      = topic.get("hook", "")
            outline   = topic.get("outline", [])
            html_parts.append(f"<h3>选题 {i}：{t}</h3>")
            html_parts.append(f"<p>📱 <strong>平台</strong>：{platforms}</p>")
            if hook:
                html_parts.append(f"<p>🎯 <strong>读者痛点</strong>：{hook}</p>")
            if outline:
                html_parts.append("<p><strong>📝 文章大纲</strong></p><ul>")
                for sec in outline:
                    html_parts.append(f"<li>{sec}</li>")
                html_parts.append("</ul>")
            html_parts.append("<hr/>")

        SubElement(item_el, "description").text = "\n".join(html_parts)

    # ── 灵构相关单条 ──────────────────────────────────────────────────────────
    for it, cat in linggou_items:
        item_el = SubElement(channel, "item")
        title = it.get("title") or it.get("title_en") or "（无标题）"
        meta  = CAT_META[cat]
        src   = SOURCE_LABELS.get(it.get("source",""), it.get("source",""))
        SubElement(item_el, "title").text = f"{meta['tag']} · {title}"
        url = it.get("url", SITE_URL)
        SubElement(item_el, "link").text = url
        SubElement(item_el, "guid", isPermaLink="false").text = f"linggou-{it.get('id', '')}"
        pub_dt = to_cst(it.get("publishedAt"))
        SubElement(item_el, "pubDate").text = fmt_rfc2822(pub_dt or generated_at)
        SubElement(item_el, "category").text = meta["tag"]
        SubElement(item_el, "description").text = build_item_html(it, cat)

    xml_str = tostring(rss, encoding="unicode")
    dom = minidom.parseString(xml_str)
    return dom.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")


def main():
    now = datetime.now(CST)
    weekday = now.weekday()  # 0=周一 ... 6=周日

    # 周末不推送，周一拉取3天内容（覆盖周六+周日+周一）
    if weekday == 5 or weekday == 6:
        print(f"[{now.strftime('%Y-%m-%d %H:%M CST')}] 今天是周末，跳过推送。")
        return

    if weekday == 0:
        hours_back = 72   # 周一：拉取72小时（覆盖周五下班后到周一）
        time_window_desc = "（含周末）"
    else:
        hours_back = 24
        time_window_desc = ""

    since_dt = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    since    = since_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"[{now.strftime('%Y-%m-%d %H:%M CST')}] 拉取资讯（最近{hours_back}小时，since={since}）...")

    # ── 拉取所有来源 ──────────────────────────────────────────────────────────
    aihot_items = fetch_aihot(since, take=100)

    extra_items = []
    for source in EXTRA_RSS_SOURCES:
        extra_items.extend(fetch_extra_rss(source, since_dt))

    # 合并去重（以 url 为 key）
    seen_urls = set()
    all_items = []
    for it in aihot_items + extra_items:
        url = it.get("url", "")
        if url and url not in seen_urls:
            all_items.append(it)
            seen_urls.add(url)
        elif not url:
            all_items.append(it)

    print(f"  合并后共 {len(all_items)} 条")

    # ── 灵构过滤 ──────────────────────────────────────────────────────────────
    linggou_items = []
    seen_ids = set()
    for it in all_items:
        cat = match_category(it)
        item_id = it.get("id") or it.get("url", "")
        if cat and item_id not in seen_ids:
            linggou_items.append((it, cat))
            seen_ids.add(item_id)

    print(f"  灵构相关 {len(linggou_items)} 条")
    for it, cat in linggou_items:
        print(f"    [{CAT_META[cat]['tag']}·{it.get('source','')}] {it.get('title','')[:45]}")

    # ── 生成社媒选题 ──────────────────────────────────────────────────────────
    print("  生成社媒选题...")
    social_topics = generate_social_topics(linggou_items, all_items)

    # ── 写文件 ────────────────────────────────────────────────────────────────
    xml_content = generate_rss(linggou_items, all_items, now, social_topics, time_window_desc)

    base = os.path.dirname(__file__)
    with open(os.path.join(base, "feed.xml"), "w", encoding="utf-8") as f:
        f.write(xml_content)
    print(f"  已写入 feed.xml（{len(xml_content)} 字节）")

    if social_topics:
        with open(os.path.join(base, "social_topics.json"), "w", encoding="utf-8") as f:
            json.dump({"generated_at": now.isoformat(), "topics": social_topics},
                      f, ensure_ascii=False, indent=2)
        print("  已写入 social_topics.json")

    sources_breakdown = {}
    for it, _ in linggou_items:
        s = it.get("source", "未知")
        sources_breakdown[s] = sources_breakdown.get(s, 0) + 1

    meta = {
        "generated_at": now.isoformat(),
        "total": len(all_items),
        "linggou": len(linggou_items),
        "social_topics": len(social_topics),
        "sources": sources_breakdown,
        "categories": {
            cat: sum(1 for _, c in linggou_items if c == cat)
            for cat in ["aigc_content", "tech_tools", "industry"]
        }
    }
    with open(os.path.join(base, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print("  已写入 meta.json")

if __name__ == "__main__":
    main()
