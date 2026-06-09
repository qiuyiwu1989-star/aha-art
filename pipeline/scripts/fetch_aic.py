#!/usr/bin/env python3
"""拉取 Art Institute of Chicago 公共领域名画,生成 artworks.json。
仅保留 is_public_domain=True 且有 image_id 的作品。图片走 AIC IIIF CDN。"""
import json, urllib.parse, urllib.request, time, sys

API = "https://api.artic.edu/api/v1/artworks/search"
FIELDS = "id,title,artist_title,date_display,date_start,image_id,medium_display,classification_title,is_public_domain,place_of_origin,thumbnail"

# (slug 我们自定义的稳定 id, 搜索词, 期望艺术家关键词)
TARGETS = [
    ("paris-rainy",      "Paris Street; Rainy Day",            "Caillebotte"),
    ("grande-jatte",     "A Sunday on La Grande Jatte",        "Seurat"),
    ("vg-bedroom",       "The Bedroom",                        "Gogh"),
    ("waterlilies",      "Water Lilies",                       "Monet"),
    ("haystacks",        "Stacks of Wheat",                    "Monet"),
    ("two-sisters",      "Two Sisters On the Terrace",         "Renoir"),
    ("basket-apples",    "The Basket of Apples",               "Cezanne"),
    ("great-wave",       "Under the Wave off Kanagawa",        "Hokusai"),
    ("childs-bath",      "The Child's Bath",                   "Cassatt"),
    ("moulin-rouge",     "At the Moulin Rouge",                "Lautrec"),
    ("el-greco-assump",  "The Assumption of the Virgin",       "Greco"),
    ("gauguin-day",      "Day of the God",                     "Gauguin"),
    ("vg-selfportrait",  "Self-Portrait",                      "Gogh"),
    ("hiroshige",        "plum",                               "Hiroshige"),
    ("monet-cliff",      "Cliff Walk at Pourville",            "Monet"),
    ("seurat-study",     "study Grande Jatte",                 "Seurat"),
    ("renoir-lunch",     "Lunch at the Restaurant Fournaise",  "Renoir"),
    ("toulouse-jane",    "Jane Avril",                         "Lautrec"),
]

def search(q):
    url = f"{API}?q={urllib.parse.quote(q)}&fields={FIELDS}&limit=12"
    req = urllib.request.Request(url, headers={"User-Agent":"aha-demo/0.1 (research demo)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

def pick(data, artist_kw):
    for d in data.get("data", []):
        if not d.get("is_public_domain"): continue
        if not d.get("image_id"): continue
        if artist_kw.lower() not in (d.get("artist_title") or "").lower(): continue
        return d
    return None  # 不做任意 fallback,artist 不匹配宁可丢弃

IIIF = "https://www.artic.edu/iiif/2/{}/full/1200,/0/default.jpg"

out = []
seen_ids = set()
for slug, q, artist in TARGETS:
    try:
        data = search(q)
        d = pick(data, artist)
        if not d:
            print(f"  MISS  {slug}: no public-domain match for '{q}'", file=sys.stderr); continue
        if d["id"] in seen_ids:
            print(f"  DUP   {slug}: {d['title']} already taken", file=sys.stderr); continue
        seen_ids.add(d["id"])
        out.append({
            "slug": slug,
            "aicId": d["id"],
            "title": d.get("title"),
            "artist": d.get("artist_title"),
            "date": d.get("date_display"),
            "year": d.get("date_start"),
            "medium": d.get("medium_display"),
            "classification": d.get("classification_title"),
            "origin": d.get("place_of_origin"),
            "image": IIIF.format(d["image_id"]),
            "lqip": (d.get("thumbnail") or {}).get("lqip"),
            "alt": (d.get("thumbnail") or {}).get("alt_text"),
        })
        print(f"  OK    {slug}: {d.get('artist_title')} — {d.get('title')} ({d.get('date_display')})")
        time.sleep(0.4)
    except Exception as e:
        print(f"  ERR   {slug}: {e}", file=sys.stderr)

json.dump(out, open("/home/ubuntu/users/qiuyiwu/aha-art-demo/data/artworks_raw.json","w"),
          ensure_ascii=False, indent=2)
print(f"\nTotal: {len(out)} works -> data/artworks_raw.json")
