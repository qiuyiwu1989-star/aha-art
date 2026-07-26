#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网藏作品注入脚本
批量标记高质量作品为 exhibited=true

用法:
  python3 inject_to_exhibition.py              # 执行注入
  python3 inject_to_exhibition.py --dry-run    # 预览
  python3 inject_to_exhibition.py --min-quality 0.9  # 设置最低质量分
"""
import json, psycopg2

def load_config():
    return json.load(open('/home/ubuntu/.aha_pg.json'))

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true', help='预览模式')
    ap.add_argument('--min-quality', type=float, default=0.8, help='最低质量分')
    a = ap.parse_args()

    d = load_config()
    con = psycopg2.connect(host=d['host'], port=d['port'], dbname=d['dbname'],
                          user=d['user'], password=d['password'])
    cur = con.cursor()

    # 1. 统计可注入的数量
    cur.execute('''
        SELECT count(*) FROM works 
        WHERE status='kept' 
        AND exhibited=false 
        AND quality >= %s
    ''', (a.min_quality,))
    total = cur.fetchone()[0]
    print(f'可注入网藏的作品: {total:,} (质量>= {a.min_quality})')

    if a.dry_run:
        print('预览模式，不实际修改')
        return

    # 2. 批量注入
    cur.execute('''
        UPDATE works SET exhibited=true 
        WHERE status='kept' 
        AND exhibited=false 
        AND quality >= %s
    ''', (a.min_quality,))
    updated = cur.rowcount
    con.commit()

    print(f'注入作品: {updated:,} 件')

    # 3. 验证
    cur.execute('SELECT count(*) FROM works WHERE exhibited=true')
    total_exhibited = cur.fetchone()[0]
    print(f'网藏作品总数: {total_exhibited:,}')

    con.close()

if __name__ == '__main__':
    main()
