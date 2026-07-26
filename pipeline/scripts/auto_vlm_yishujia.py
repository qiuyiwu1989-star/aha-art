#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
yishujia VLM 自动处理脚本
- 检查 pending 数量
- 分批处理（默认每批 500 张）
- 记录日志
- 支持 cron 定时运行

用法:
  python3 auto_vlm_yishujia.py                    # 处理一批（500张）
  python3 auto_vlm_yishujia.py --limit 1000       # 处理1000张
  python3 auto_vlm_yishujia.py --loop             # 循环处理直到完成
  python3 auto_vlm_yishujia.py --status           # 只查看状态
"""
import os, sys, json, time, argparse, subprocess
from datetime import datetime

# 配置
WORK_DIR = "/home/ubuntu/users/qiuyiwu/aha-art"
LOG_DIR = os.path.join(WORK_DIR, "pipeline/scripts/logs")
BATCH = "yishujia:art"
DEFAULT_LIMIT = 500
WORKERS = 8

def ensure_log_dir():
    os.makedirs(LOG_DIR, exist_ok=True)

def get_status():
    """获取当前处理状态"""
    import psycopg2
    d = json.load(open(os.path.expanduser("~/.aha_pg.json")))
    con = psycopg2.connect(host=d['host'], port=d['port'], dbname=d['dbname'],
                          user=d['user'], password=d['password'])
    cur = con.cursor()

    cur.execute("""
        SELECT status, count(*) FROM works
        WHERE source_batch=%s GROUP BY status ORDER BY count(*) DESC
    """, (BATCH,))
    status = {row[0]: row[1] for row in cur.fetchall()}

    cur.execute("""
        SELECT count(*) FROM works
        WHERE source_batch=%s AND status='pending'
    """, (BATCH,))
    pending = cur.fetchone()[0]

    con.close()
    return status, pending

def is_gate_running():
    """检查 gate.py 是否在运行"""
    try:
        r = subprocess.run(['pgrep', '-f', 'gate.py.*yishujia'],
                          capture_output=True, text=True)
        return r.returncode == 0
    except:
        return False

def run_vlm(limit):
    """运行 VLM 处理"""
    log_file = os.path.join(LOG_DIR, f"vlm_yishujia_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

    cmd = f"cd {WORK_DIR} && python3 pipeline/scripts/gate.py vlm --batch '{BATCH}' --workers {WORKERS}"
    if limit:
        cmd += f" --limit {limit}"

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始处理 {limit or '全部'} 张...")
    print(f"日志: {log_file}")

    with open(log_file, 'w') as f:
        proc = subprocess.Popen(
            cmd, shell=True, stdout=f, stderr=subprocess.STDOUT,
            cwd=WORK_DIR
        )
        proc.wait()

    return proc.returncode

def main():
    ap = argparse.ArgumentParser(description="yishujia VLM 自动处理")
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="每批处理数量")
    ap.add_argument("--loop", action="store_true", help="循环处理直到完成")
    ap.add_argument("--status", action="store_true", help="只查看状态")
    ap.add_argument("--workers", type=int, default=WORKERS, help="并发数")
    a = ap.parse_args()

    ensure_log_dir()

    # 查看状态
    if a.status:
        status, pending = get_status()
        print("=== yishujia:art 状态 ===")
        for s, n in status.items():
            print(f"  {s:<12} {n:>8,}")
        print(f"\npending: {pending:,}")
        return

    # 检查是否在运行
    if is_gate_running():
        print("gate.py 正在运行中，跳过本次")
        return

    # 循环模式
    if a.loop:
        print("进入循环模式...")
        while True:
            status, pending = get_status()
            if pending == 0:
                print("所有数据处理完成！")
                break

            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] pending: {pending:,}")
            rc = run_vlm(a.limit)

            if rc != 0:
                print(f"处理异常退出 (code={rc})，等待5分钟后重试...")
                time.sleep(300)
            else:
                # 处理完一批，等待30秒再继续
                time.sleep(30)
    else:
        # 单次模式
        status, pending = get_status()
        if pending == 0:
            print("没有待处理的数据")
            return

        limit = min(a.limit, pending)
        print(f"pending: {pending:,}，本次处理: {limit:,}")
        rc = run_vlm(limit)

        # 输出结果
        status, pending = get_status()
        print(f"\n处理完成，剩余 pending: {pending:,}")
        sys.exit(rc)

if __name__ == "__main__":
    main()
