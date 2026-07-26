#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
艺术家去重合并脚本
- 按 name_en 精确匹配
- 保留信息最完整的 artist_id 作为主 ID
- 将其他 ID 的作品迁移到主 ID
- 合并后删除旧艺术家记录

用法:
  python3 merge_artists.py              # 执行合并
  python3 merge_artists.py --dry-run    # 预览，不实际修改
"""
import json, psycopg2
from collections import defaultdict

def load_config():
    return json.load(open('/home/ubuntu/.aha_pg.json'))

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true', help='预览模式，不实际修改')
    a = ap.parse_args()

    d = load_config()
    con = psycopg2.connect(host=d['host'], port=d['port'], dbname=d['dbname'],
                          user=d['user'], password=d['password'])
    cur = con.cursor()

    # 1. 找出所有需要合并的艺术家组
    cur.execute('''
        SELECT name_en, array_agg(artist_id ORDER BY
            CASE WHEN name_cn IS NOT NULL THEN 0 ELSE 1 END +
            CASE WHEN born IS NOT NULL THEN 0 ELSE 1 END +
            CASE WHEN death IS NOT NULL THEN 0 ELSE 1 END
        ) as ids
        FROM artists
        WHERE name_en IS NOT NULL
        GROUP BY name_en
        HAVING count(*) > 1
    ''')
    merge_groups = cur.fetchall()
    print(f'找到 {len(merge_groups)} 组需要合并的艺术家')

    total_merged = 0
    total_works_moved = 0

    for name_en, ids in merge_groups:
        # 选择主 ID（信息最完整的）
        primary_id = ids[0]
        secondary_ids = ids[1:]

        # 统计每个 ID 的作品数
        cur.execute('''
            SELECT artist_id, count(*) FROM works
            WHERE artist_id = any(%s)
            GROUP BY artist_id
        ''', (ids,))
        work_counts = dict(cur.fetchall())

        # 将次要 ID 的作品迁移到主 ID
        for sec_id in secondary_ids:
            n_works = work_counts.get(sec_id, 0)
            if n_works > 0:
                if not a.dry_run:
                    cur.execute('''
                        UPDATE works SET artist_id=%s WHERE artist_id=%s
                    ''', (primary_id, sec_id))
                total_works_moved += n_works
                print(f'  合并 {sec_id} -> {primary_id}: {n_works} 件作品')

            # 删除次要艺术家的关联表数据
            if not a.dry_run:
                cur.execute('DELETE FROM artist_alias WHERE artist_id=%s', (sec_id,))
                cur.execute('DELETE FROM artists WHERE artist_id=%s', (sec_id,))

        total_merged += len(secondary_ids)

    if not a.dry_run:
        con.commit()

    print(f'\n=== 合并完成 ===')
    print(f'合并艺术家: {total_merged} 个')
    print(f'迁移作品: {total_works_moved} 件')

    # 验证
    cur.execute('SELECT count(*) FROM artists')
    print(f'合并后艺术家总数: {cur.fetchone()[0]:,}')

    cur.execute('''
        SELECT count(*) FROM (
            SELECT name_en FROM artists GROUP BY name_en HAVING count(*) > 1
        ) t
    ''')
    remaining = cur.fetchone()[0]
    print(f'剩余重复组: {remaining}')

    con.close()

if __name__ == '__main__':
    main()
