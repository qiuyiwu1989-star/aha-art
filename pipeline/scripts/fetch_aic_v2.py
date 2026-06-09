#!/usr/bin/env python3
"""扩样本 + 富字段:从 AIC 抓约 100 件公共领域作品,带颜色/流派/主题/年代等深度字段。
按多个流派/年代/文化检索以保证多样且可连接。输出 data/artworks_rich.json。"""
import json, urllib.parse, urllib.request, time, sys

API = "https://api.artic.edu/api/v1/artworks/search"
FIELDS = ",".join([
    "id", "title", "artist_title", "artist_id", "date_display", "date_start", "date_end",
    "medium_display", "classification_title", "classification_titles",
    "style_title", "style_titles", "subject_titles", "theme_titles", "technique_titles",
    "place_of_origin", "artwork_type_title", "color", "colorfulness",
    "image_id", "is_public_domain", "thumbnail",
])
# 检索词(流派/年代/文化)→ 保证多样且每簇有多件,便于自动建"同流派/同母题"边
QUERIES = [
    "impressionism", "post-impressionism", "pointillism", "realism", "romanticism",
    "baroque", "renaissance", "dutch golden age", "ukiyo-e japanese woodblock",
    "landscape painting", "portrait painting", "still life", "modernism",
    "japanese print", "chinese painting", "abstraction", "cubism", "symbolism",
    "marine seascape", "night nocturne",
]
PER = 14

def search(q):
    url = f"{API}?q={urllib.parse.quote(q)}&fields={FIELDS}&limit={PER}"
    req = urllib.request.Request(url, headers={"User-Agent": "aha-demo/0.2 (research demo)"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.load(r)

IIIF = "https://www.artic.edu/iiif/2/{}/full/1200,/0/default.jpg"
out, seen = [], set()
for q in QUERIES:
    try:
        data = search(q)
        for d in data.get("data", []):
            if not d.get("is_public_domain") or not d.get("image_id"):
                continue
            if d["id"] in seen:
                continue
            seen.add(d["id"])
            out.append({
                "aicId": d["id"],
                "title": d.get("title"), "artist": d.get("artist_title"), "artistId": d.get("artist_id"),
                "date": d.get("date_display"), "year": d.get("date_start"), "yearEnd": d.get("date_end"),
                "medium": d.get("medium_display"),
                "classification": d.get("classification_title"), "classifications": d.get("classification_titles") or [],
                "style": d.get("style_title"), "styles": d.get("style_titles") or [],
                "subjects": d.get("subject_titles") or [], "themesRaw": d.get("theme_titles") or [],
                "techniques": d.get("technique_titles") or [],
                "origin": d.get("place_of_origin"), "type": d.get("artwork_type_title"),
                "color": d.get("color"), "colorfulness": d.get("colorfulness"),
                "image": IIIF.format(d["image_id"]),
                "lqip": (d.get("thumbnail") or {}).get("lqip"),
                "alt": (d.get("thumbnail") or {}).get("alt_text"),
            })
        print(f"  {q:<32} +{len(data.get('data', []))}  (累计 {len(out)})")
        time.sleep(0.35)
    except Exception as e:
        print(f"  ERR {q}: {e}", file=sys.stderr)

json.dump(out, open("/home/ubuntu/users/qiuyiwu/aha-art-demo/data/artworks_rich.json", "w"), ensure_ascii=False, indent=1)
print(f"\nTotal unique: {len(out)} → data/artworks_rich.json")
withcolor = sum(1 for w in out if w.get("color"))
withstyle = sum(1 for w in out if w.get("styles"))
print(f"  有颜色字段: {withcolor} · 有流派: {withstyle}")
