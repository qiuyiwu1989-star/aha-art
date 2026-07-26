#!/usr/bin/env python3
"""近重复聚簇(只标不删):用 pHash 汉明距离把视觉几乎一样的图归到一簇。
分带 LSH(8个8位band,保证召回汉明≤5)+ 限桶 + 并查集。每簇选最高分辨率作代表。
写 gen_file.dupe_cluster(=代表gen_file_id)+ dupe_rep(是否代表)。永不物理删。

用法: python3 dedup_cluster.py [--k 5] [--maxbucket 800]
"""
import json, os, argparse, psycopg2

def _cfg(p): return json.load(open(os.path.expanduser(p)))
def pg():
    d=_cfg("~/.aha_pg.json"); return psycopg2.connect(host=d["host"],port=d["port"],dbname=d["dbname"],user=d["user"],password=d["password"])

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--k",type=int,default=5)            # 汉明距离阈值
    ap.add_argument("--maxbucket",type=int,default=800)  # 超大桶跳过(多为偶然撞band)
    a=ap.parse_args()
    cn=pg(); cur=cn.cursor()
    cur.execute("SELECT gen_file_id, phash, COALESCE(width,0)*COALESCE(height,0) FROM gen_file WHERE source='zaowuyun_team' AND role='output' AND phash IS NOT NULL")
    rows=cur.fetchall()
    n=len(rows); print(f"载入 {n} 张",flush=True)
    ids=[r[0] for r in rows]
    res=[r[2] for r in rows]
    H=[int(r[1],16) & ((1<<64)-1) for r in rows]   # phash → 64bit int

    parent=list(range(n))
    def find(x):
        while parent[x]!=x: parent[x]=parent[parent[x]]; x=parent[x]
        return x
    def union(a,b):
        ra,rb=find(a),find(b)
        if ra!=rb: parent[ra]=rb

    def popcount(x): return bin(x).count("1")
    BANDS=8; BITS=8; MASK=(1<<BITS)-1
    for band in range(BANDS):
        shift=band*BITS
        buckets={}
        for i in range(n):
            key=(H[i]>>shift)&MASK
            buckets.setdefault(key,[]).append(i)
        for key,members in buckets.items():
            if len(members)<2 or len(members)>a.maxbucket: continue
            for ai in range(len(members)):
                for bi in range(ai+1,len(members)):
                    x,y=members[ai],members[bi]
                    if find(x)==find(y): continue
                    if popcount(H[x]^H[y])<=a.k: union(x,y)
        print(f"  band {band+1}/{BANDS} done",flush=True)

    # 归簇:代表=簇内最高分辨率(并列取最小 gen_file_id)
    from collections import defaultdict
    clusters=defaultdict(list)
    for i in range(n): clusters[find(i)].append(i)
    rep_of={}
    nclust=0; nfolded=0
    for root,members in clusters.items():
        best=max(members,key=lambda i:(res[i], -ids[i]))
        rep_id=ids[best]
        for i in members: rep_of[i]=rep_id
        if len(members)>1: nclust+=1; nfolded+=len(members)-1

    # 批量写回
    upd=[(rep_of[i], ids[i]==rep_of[i], ids[i]) for i in range(n)]
    cur.executemany("UPDATE gen_file SET dupe_cluster=%s, dupe_rep=%s WHERE gen_file_id=%s", upd)
    cn.commit()
    print(f"完成: {len(clusters)} 簇, 其中 {nclust} 个多图簇, 可折叠省 {nfolded} 张",flush=True)
    cur.close(); cn.close()

if __name__=="__main__": main()
