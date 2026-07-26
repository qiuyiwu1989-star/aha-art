#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
yishujia 元数据提取脚本
从 VLM 结果中提取艺术家、标题等元数据，更新到数据库

用法:
  python3 extract_yishujia_metadata.py              # 执行提取
  python3 extract_yishujia_metadata.py --dry-run    # 预览
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

    # 1. 提取有艺术家信息的作品
    cur.execute('''
        SELECT work_id, 
               vlm->'identify'->>'artist' as artist_name,
               vlm->'identify'->>'title' as title
        FROM works 
        WHERE source_batch='yishujia:art' 
        AND status='kept' 
        AND vlm->'identify' IS NOT NULL
        AND vlm->'identify'->>'artist' IS NOT NULL
        AND vlm->'identify'->>'artist' != ''
    ''')
    rows = cur.fetchall()
    print(f'找到 {len(rows)} 件有艺术家信息的作品')

    updated = 0
    for work_id, artist_name, title in rows:
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
            artist_id = f'yishujia:{artist_name}'
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
        WHERE source_batch='yishujia:art' 
        AND status='kept' 
        AND artist_id NOT LIKE '%unknown%'
    ''')
    print(f'yishujia 有艺术家的作品: {cur.fetchone()[0]:,}')

    con.close()

if __name__ == '__main__':
    main()
