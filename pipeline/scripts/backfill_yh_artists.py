#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
yh 艺术家补充脚本
从 VLM 结果中提取艺术家信息，补充缺失的艺术家

用法:
  python3 backfill_yh_artists.py              # 执行补充
  python3 backfill_yh_artists.py --dry-run    # 预览
"""
import json, psycopg2

def load_config():
    return json.load(open('/home/ubuntu/.aha_pg.json'))

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true', help='预览模式')
    a = ap.parse_args()

    d = load_config()
    con = psycopg2.connect(host=d['host'], port=d['port'], dbname=d['dbname'],
                          user=d['user'], password=d['password'])
    cur = con.cursor()

    # 1. 找出缺艺术家但 VLM 有信息的作品
    cur.execute('''
        SELECT work_id, 
               vlm->'identify'->>'artist' as artist_name
        FROM works 
        WHERE source_batch LIKE 'yh%%' 
        AND status='kept' 
        AND (artist_id LIKE '%unknown%' OR artist_id IS NULL)
        AND vlm->'identify' IS NOT NULL
        AND vlm->'identify'->>'artist' IS NOT NULL
        AND vlm->'identify'->>'artist' != ''
    ''')
    rows = cur.fetchall()
    print(f'找到 {len(rows)} 件缺艺术家但 VLM 有信息的作品')

    updated = 0
    for work_id, artist_name in rows:
        # 查找或创建艺术家
        cur.execute('''
            SELECT artist_id FROM artists 
            WHERE name_cn=%s OR name_en=%s
            LIMIT 1
        ''', (artist_name, artist_name))
        row = cur.fetchone()
        
        if row:
            artist_id = row[0]
        else:
            # 创建新艺术家
            artist_id = f'yh:name:{artist_name}'
            if not a.dry_run:
                cur.execute('''
                    INSERT INTO artists (artist_id, name_cn, created_at)
                    VALUES (%s, %s, now())
                    ON CONFLICT (artist_id) DO NOTHING
                ''', (artist_id, artist_name))

        # 更新作品
        if not a.dry_run:
            cur.execute('''
                UPDATE works SET artist_id=%s WHERE work_id=%s
            ''', (artist_id, work_id))
        updated += 1

    if not a.dry_run:
        con.commit()

    print(f'更新作品: {updated} 件')

    # 验证
    cur.execute('''
        SELECT count(*) FROM works 
        WHERE source_batch LIKE 'yh%%' 
        AND status='kept' 
        AND (artist_id LIKE '%unknown%' OR artist_id IS NULL)
    ''')
    remaining = cur.fetchone()[0]
    print(f'剩余缺艺术家: {remaining:,}')

    con.close()

if __name__ == '__main__':
    main()
