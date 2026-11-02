# 页面迁移核验

已迁移 reading/archive/trail：先读当前用户记录，再按引用 resolve（每批60），不请求全馆。test-album 使用服务器 q/wv/min_quality 游标分页，入册历史独立 resolve，界面显示当前已加载数量。五个非3D hero 设计方案使用精选候选池并标注样本；art-layouts 换画使用精选池。

exhibitions 使用 rule-summary 的全域规则聚合count/cover。wander-talk 将完整意图评分移至 intent 接口，返回8幅。curate 使用 catalog-facets 全域聚合、40件游标选画、服务器语义匹配和邻近作品；收藏/草稿/hash/展厅种子/保存展览按引用恢复。页面不再把当前页当全馆。打乱功能明确只打乱已加载作品。

待核验：新后端接口尚由主代理集成；这些前端改动不能仅凭语法即称端到端验收。dashboard 管理全集仍由其他任务负责。

验证：修改页面内联脚本 node --check通过；catalog-resolve.cjs 测试125个唯一引用分60/60/5请求、去重和失败传播通过。未进行登录历史及后台写入回归；只读预览禁止后台写。

## 画框后台收尾

画框后台已去掉最后的 exhibit?limit=8000 全集下载。改为 frame-catalog 40件游标页，搜索、待复核、人工指定均由服务端筛选；全库图表读取全域聚合，不拿当前页冒充全库。保存接口和管理口令校验保持原路径，保存成功刷新统计。请求版本防过期覆盖，分页失败恢复按钮并提供重试。

backend/frame-engine.cjs 在隔离 Node vm 中直接执行原 frames.js，因此供应链样式覆盖、AI建议、人工覆盖和默认匹配保持同一个算法来源；无分叉算法。单元测试验证人工优先、0.8复核阈值和统计守恒。后台全部内联脚本语法通过。服务端frame-catalog集成及真实浏览器验收待主任务完成。
