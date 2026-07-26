#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全 COS 概览扫描:遍历账号下所有桶,按「顶层前缀(前两级)」聚合对象数/字节/图像数/扩展名分布。
输出 JSON 到 --out。供 dam.alimq.com/cos/ 全景页消费。只读,不改任何对象。"""
import json, sys, time, argparse, os
from collections import defaultdict
from qcloud_cos import CosConfig, CosS3Client

IMG_EXT = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tiff', '.tif', '.avif', '.heic')

def cfg():
    d = json.load(open(os.path.expanduser('~/.aha_cos.json')))
    return d, CosS3Client(CosConfig(Region=d['region'], SecretId=d['secret_id'], SecretKey=d['secret_key']))

def pfx_of(key):
    parts = key.split('/')
    if len(parts) >= 2 and parts[1] != '':
        return parts[0] + '/' + parts[1] + '/'
    return parts[0] + ('/' if len(parts) > 1 else '')

def scan_bucket(c, bucket, cap):
    pfx = defaultdict(lambda: {'n': 0, 'bytes': 0, 'img': 0, 'ext': defaultdict(int)})
    total = 0; total_bytes = 0; total_img = 0; marker = ''; truncated_at = None
    while True:
        try:
            r = c.list_objects(Bucket=bucket, Marker=marker, MaxKeys=1000)
        except Exception as e:
            return {'error': str(e)}
        for o in r.get('Contents', []):
            k = o['Key']
            if k.endswith('/'):  # 目录占位符
                continue
            sz = int(o.get('Size', 0))
            total += 1; total_bytes += sz
            p = pfx_of(k)
            d = pfx[p]; d['n'] += 1; d['bytes'] += sz
            ext = ('.' + k.rsplit('.', 1)[1].lower()) if '.' in k.rsplit('/', 1)[-1] else '(none)'
            d['ext'][ext] += 1
            if ext in IMG_EXT:
                d['img'] += 1; total_img += 1
        if r.get('IsTruncated') == 'true' and total < cap:
            marker = r['NextMarker']
        else:
            if r.get('IsTruncated') == 'true':
                truncated_at = total
            break
    out_pfx = []
    for p, d in sorted(pfx.items(), key=lambda x: -x[1]['n']):
        out_pfx.append({'prefix': p, 'n': d['n'], 'bytes': d['bytes'], 'img': d['img'],
                        'ext': dict(sorted(d['ext'].items(), key=lambda x: -x[1])[:8])})
    return {'objects': total, 'bytes': total_bytes, 'images': total_img,
            'prefixes': out_pfx, 'truncated_at': truncated_at}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='/home/ubuntu/users/qiuyiwu/aha-art/pipeline/scripts/cos_overview.json')
    ap.add_argument('--cap', type=int, default=2_000_000, help='每桶最多扫描对象数(保护)')
    a = ap.parse_args()
    d, c = cfg()
    try:
        buckets = [b['Name'] for b in c.list_buckets()['Buckets']['Bucket']]
    except Exception as e:
        print('list_buckets 失败:', e); sys.exit(1)
    result = {'scanned_at': int(time.time()), 'buckets': []}
    grand_obj = grand_bytes = grand_img = 0
    for bk in buckets:
        t0 = time.time()
        print(f'[{time.strftime("%H:%M:%S")}] 扫 {bk} ...', flush=True)
        info = scan_bucket(c, bk, a.cap)
        info['name'] = bk
        info['elapsed'] = round(time.time() - t0, 1)
        result['buckets'].append(info)
        if 'objects' in info:
            grand_obj += info['objects']; grand_bytes += info['bytes']; grand_img += info['images']
            print(f'    -> {info["objects"]} 对象 / {info["images"]} 图 / {info["bytes"]/1e9:.1f}GB / {info["elapsed"]}s', flush=True)
        else:
            print(f'    -> ERR {info.get("error")}', flush=True)
        # 每桶写一次,便于中途观察
        result['total'] = {'objects': grand_obj, 'bytes': grand_bytes, 'images': grand_img}
        json.dump(result, open(a.out, 'w'), ensure_ascii=False, indent=1)
    result['done'] = True
    json.dump(result, open(a.out, 'w'), ensure_ascii=False, indent=1)
    print(f'DONE 共 {grand_obj} 对象 / {grand_img} 图 / {grand_bytes/1e9:.1f}GB -> {a.out}', flush=True)

if __name__ == '__main__':
    main()
