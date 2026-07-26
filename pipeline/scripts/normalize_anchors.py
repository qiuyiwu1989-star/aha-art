#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
情绪锚点规范化脚本
将非标准锚点映射到14个标准锚点

标准锚点: 喜悦 鲜活 热烈 崇高 张力 恐惧 神秘 忧伤 孤独 怀旧 虚无 沉思 平静 空灵
"""
import json, psycopg2, re

# 锚点映射规则
ANCHOR_MAP = {
    # 平静系
    '平静': '平静', '沉静': '平静', '静谧': '平静', '宁静': '平静', '平和': '平静',
    '沉稳': '平静', '安详': '平静', '祥和': '平静',
    
    # 沉思系
    '沉思': '沉思', '冥想': '沉思', '深邃': '沉思', '思索': '沉思',
    
    # 喜悦系
    '喜悦': '喜悦', '愉悦': '喜悦', '欢乐': '喜悦', '快乐': '喜悦', '欣喜': '喜悦',
    '喜悦': '喜悦', '欢欣': '喜悦', '欢快': '喜悦',
    
    # 热烈系
    '热烈': '热烈', '热情': '热烈', '狂热': '热烈', '激情': '热烈', '火热': '热烈',
    
    # 鲜活系
    '鲜活': '鲜活', '活力': '鲜活', '生机': '鲜活', '活跃': '鲜活', '蓬勃': '鲜活',
    
    # 崇高系
    '崇高': '崇高', '庄严': '崇高', '庄重': '崇高', '神圣': '崇高', '威严': '崇高',
    '崇敬': '崇高', '敬畏': '崇高', '崇高': '崇高',
    
    # 张力系
    '张力': '张力', '紧张': '张力', '紧张感': '张力', '冲突': '张力', '对抗': '张力',
    
    # 恐惧系
    '恐惧': '恐惧', '惊恐': '恐惧', '恐怖': '恐惧', '畏惧': '恐惧', '不安': '恐惧',
    
    # 神秘系
    '神秘': '神秘', '梦幻': '神秘', '魔幻': '神秘', '超现实': '神秘',
    
    # 忧伤系
    '忧伤': '忧伤', '忧郁': '忧伤', '哀伤': '忧伤', '悲伤': '忧伤', '悲痛': '忧伤',
    '忧愁': '忧伤', '忧虑': '忧伤', '惆怅': '忧伤', '悲悯': '忧伤',
    
    # 孤独系
    '孤独': '孤独', '孤寂': '孤独', '孤高': '孤独', '寂寞': '孤独', '落寞': '孤独',
    
    # 怀旧系
    '怀旧': '怀旧', '怀念': '怀旧', '思念': '怀旧', '乡愁': '怀旧', '思乡': '怀旧',
    '追忆': '怀旧', '眷恋': '怀旧',
    
    # 虚无系
    '虚无': '虚无', '空虚': '虚无', '寂灭': '虚无', '幻灭': '虚无',
    
    # 空灵系
    '空灵': '空灵', '飘渺': '空灵', '轻盈': '空灵', '超脱': '空灵',
    
    # 其他映射
    '优雅': '平静', '优雅': '平静', '从容': '平静', '淡定': '平静',
    '温暖': '平静', '温馨': '平静', '温情': '平静',
    '幽默': '喜悦', '诙谐': '喜悦', '诙谐': '喜悦',
    '痛苦': '忧伤', '苦涩': '忧伤', '悲怆': '忧伤',
    '荒诞': '神秘', '怪诞': '神秘', '诡异': '神秘',
    '欲望': '热烈', '渴望': '热烈', '激情': '热烈',
    '守护': '平静', '保护': '平静', '庇护': '平静',
    '自信': '平静', '坚定': '平静', '从容': '平静',
    '胜利': '喜悦', '凯旋': '喜悦', '成功': '喜悦',
    '悲剧': '忧伤', '悲惨': '忧伤', '凄凉': '忧伤',
    '忏悔': '沉思', '反省': '沉思', '反思': '沉思',
    '怜悯': '悲悯', '同情': '悲悯', '慈悲': '悲悯',
    '自豪': '喜悦', '骄傲': '喜悦', '荣耀': '喜悦',
    '惊叹': '崇高', '惊奇': '崇高', '震撼': '崇高',
    '期待': '沉思', '盼望': '沉思', '憧憬': '沉思',
    '坚韧': '平静', '坚强': '平静', '刚毅': '平静',
    '感恩': '平静', '感激': '平静', '感谢': '平静',
    '秩序': '平静', '规律': '平静', '和谐': '平静',
    '力量': '张力', '强力': '张力', '刚强': '张力',
    '丰饶': '鲜活', '丰盈': '鲜活', '丰收': '鲜活',
    '奇迹': '崇高', '神奇': '崇高', '非凡': '崇高',
    '纯真': '平静', '天真': '平静', '无邪': '平静',
    '慵懒': '平静', '懒散': '平静', '闲适': '平静',
    '沉醉': '沉思', '陶醉': '沉思', '迷醉': '沉思',
    '堕落': '忧伤', '沉沦': '忧伤', '堕落': '忧伤',
    '叙事': '平静', '故事': '平静', '叙述': '平静',
    '狂欢': '热烈', '欢庆': '热烈', '热闹': '热烈',
    '专注': '平静', '投入': '平静', '沉浸': '平静',
    '等待': '沉思', '守候': '沉思', '期盼': '沉思',
    '权威': '崇高', '威严': '崇高', '庄严': '崇高',
    '好奇': '鲜活', '探究': '鲜活', '求知': '鲜活',
    '亲密': '平静', '亲近': '平静', '温暖': '平静',
    '紧张': '张力', '紧绷': '张力', '焦虑': '张力',
}

def normalize_anchor(anchor):
    """规范化锚点"""
    if not anchor:
        return None
    
    # 处理数组格式的锚点
    if anchor.startswith('['):
        try:
            arr = json.loads(anchor)
            if arr and len(arr) > 0:
                anchor = arr[0]
        except:
            anchor = anchor.strip('[]').split(',')[0].strip().strip('"').strip("'")
    
    # 清理字符串
    anchor = anchor.strip()
    
    # 精确匹配
    if anchor in ANCHOR_MAP:
        return ANCHOR_MAP[anchor]
    
    # 模糊匹配
    for key, value in ANCHOR_MAP.items():
        if key in anchor or anchor in key:
            return value
    
    # 如果找不到映射，返回最接近的标准锚点
    return '平静'  # 默认映射到平静

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    d = json.load(open('/home/ubuntu/.aha_pg.json'))
    con = psycopg2.connect(host=d['host'], port=d['port'], dbname=d['dbname'],
                          user=d['user'], password=d['password'])
    cur = con.cursor()

    # 获取所有需要规范化的锚点
    cur.execute('''
        SELECT DISTINCT vlm->'affect'->>'primary_anchor' as anchor
        FROM works 
        WHERE status='kept' 
        AND vlm->'affect' IS NOT NULL
        AND vlm->'affect'->>'primary_anchor' IS NOT NULL
    ''')
    anchors = [row[0] for row in cur.fetchall()]
    
    # 找出非标准锚点
    standard_anchors = {'喜悦', '鲜活', '热烈', '崇高', '张力', '恐惧', '神秘', 
                        '忧伤', '孤独', '怀旧', '虚无', '沉思', '平静', '空灵'}
    
    non_standard = [a for a in anchors if a not in standard_anchors]
    print(f'标准锚点: {len(standard_anchors)} 个')
    print(f'非标准锚点: {len(non_standard)} 个')
    
    # 规范化非标准锚点
    updates = []
    for anchor in non_standard:
        normalized = normalize_anchor(anchor)
        if normalized != anchor:
            updates.append((anchor, normalized))
            print(f'  {anchor} -> {normalized}')
    
    print(f'\n需要更新: {len(updates)} 种')
    
    if a.dry_run:
        print('预览模式，不实际修改')
        return
    
    # 执行更新
    total_updated = 0
    for old_anchor, new_anchor in updates:
        cur.execute('''
            UPDATE works 
            SET vlm = jsonb_set(
                vlm, 
                '{affect,primary_anchor}', 
                %s::jsonb
            )
            WHERE status='kept' 
            AND vlm->'affect' IS NOT NULL
            AND vlm->'affect'->>'primary_anchor' = %s
        ''', (json.dumps(new_anchor), old_anchor))
        total_updated += cur.rowcount
    
    con.commit()
    print(f'\n更新作品: {total_updated} 件')
    
    # 验证
    cur.execute('''
        SELECT 
          vlm->'affect'->>'primary_anchor' as anchor,
          count(*) as cnt
        FROM works 
        WHERE status='kept' 
        AND vlm->'affect' IS NOT NULL
        GROUP BY 1
        ORDER BY 2 DESC
    ''')
    print('\n=== 规范化后的锚点分布 ===')
    for row in cur.fetchall():
        print(f'  {row[0]:<15} {row[1]:>8,}')
    
    con.close()

if __name__ == '__main__':
    main()
