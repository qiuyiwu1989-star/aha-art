#!/usr/bin/env python3
"""聚合每个资产的全部可搜文本 → dam_text(asset_id, txt),供混合检索(向量+文本)用。
文本来源:gen prompt/工作流 · media 名称/描述 · VLM 画意(subject/caption/elements) · 全部标签 · cos文件名。
一次性重建(幂等 upsert)。VLM 标注在增长,可定期重跑(已挂进 vlm_worker)。"""
import json, os, psycopg2
def pg():
    d=json.load(open(os.path.expanduser("~/.aha_pg.json")))
    return psycopg2.connect(host=d["host"],port=d["port"],dbname=d["dbname"],user=d["user"],password=d["password"])

SQL = """
INSERT INTO dam_text(asset_id, txt)
SELECT a.asset_id,
  concat_ws(' ',
    gr.input_prompt, gr.workflow_name,
    m.display_name, m.description,
    v.data->>'subject', v.data->>'caption', v.data->>'genre', v.data->>'technique', v.data->>'mood',
    (SELECT string_agg(el,' ') FROM jsonb_array_elements_text(COALESCE(v.data->'elements','[]'::jsonb)) el),
    (SELECT string_agg(t.tag,' ') FROM dam_tag_item t WHERE t.lib=a.lib AND t.item_id=COALESCE(a.ext_id,'a'||a.asset_id::text)),
    regexp_replace(split_part(a.cos_key,'/', -1), '\\.[a-z]+$', '')
  )
FROM dam_asset a
LEFT JOIN gen_run gr ON a.ext_table='gen_run' AND gr.instance_id=a.ext_id
LEFT JOIN zaowuyun_media m ON a.ext_table='zaowuyun_media' AND m.src_id=a.ext_id
LEFT JOIN dam_vlm v ON v.lib=a.lib AND v.item_id=COALESCE(a.ext_id,'a'||a.asset_id::text)
WHERE a.status='active'
ON CONFLICT (asset_id) DO UPDATE SET txt=EXCLUDED.txt
"""

def main():
    cn=pg(); cn.autocommit=True; c=cn.cursor()
    print("重建 dam_text …", flush=True)
    c.execute(SQL)
    c.execute("SELECT count(*) FROM dam_text WHERE txt IS NOT NULL AND txt<>''")
    print("dam_text 行数:", c.fetchone()[0], flush=True)
    c.execute("CREATE INDEX IF NOT EXISTS idx_dam_text_trgm ON dam_text USING gin (txt gin_trgm_ops)")
    print("trigram 索引 OK", flush=True)
    c.close(); cn.close()

if __name__=="__main__": main()
