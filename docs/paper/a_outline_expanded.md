# a · 论文逐节要点稿(主线 A · IUI 2027 体裁,可直接往里填)

**题目**:Finding the *Aha*, Not the Nearest: A Shared, Interpretable Aesthetic Manifold for Human–Artwork Recommendation
**目标会议**:IUI 2027(正文 2026/08/20)首选;加厚版 → CHI 2027(2026/09/10)

---

## 1. Introduction
- **开场张力**:站在一幅画前打动你的,往往**不是最像你口味的那幅**,而是"刚好新、又接得住"的那幅——心理学叫 Berlyne 倒U(唤起/新异的倒U偏好)。但主流审美/艺术推荐仍是相似度匹配,系统性地错过了 serendipity。
- **我们做了什么**:museum 级系统 aha,把**作品与用户嵌进同一张可解释的 12 维审美流形**;推荐用「熟悉↔惊喜」混合;四种交互模态 × 三层时间尺度;并配一套**可证伪的评估**。
- **三条贡献**:(1) 人画共享、可解释的审美表示;(2) 多模态信号→三层时间尺度的整合,且陈述偏好不覆盖揭示偏好;(3) **诚实评估**:发现准确率指标惩罚 serendipity、用户分两类,从而主张"用户旋钮+成熟度门控"而非单一全局模型。
- 强调**诚实立场**:我们不声称跑赢基线(数据规模有限),贡献在表示/系统/评估洞见。

## 2. Related Work
- **Serendipity & novelty in RecSys**:Berlyne 倒U;serendipity 定义与度量难题(Kotkov et al. 综述);beyond-accuracy 指标(diversity/novelty/unexpectedness)。点出"准确率与 serendipity 张力"是已知开放问题,我们给了量化证据。
- **Computational aesthetics & aesthetic embeddings**:美学质量评估(Datta 等)、风格/美学表示学习;区别于"打分美不美",我们做**可解释的多维审美坐标**。
- **Art / cultural-heritage recommendation & VLM for art**:艺术品推荐、博物馆个性化;用 VLM 抽取作品多维语义(新)。
- **Stated vs. revealed preference;cold-start**:推荐系统两类偏好如何结合、冷启动困境——我们用"三层时间尺度+成熟度门控"回应。

## 3. A Shared Aesthetic Manifold(表示层)
- **三可观测层 = 12 维**:世界观(再现-表现 ⊥ 结构-感知,2D)+ 语言(构图/空间/造型/光影/色彩/笔触/边缘,7D)+ 情绪 VAD(愉悦/唤起/控制,3D)。给定义与刻度标杆。
- **作品入嵌**:VLM(MiMo)沿这三层给 8106 幅 kept 真迹打坐标;覆盖率(worldview 89%、VAD ~100%、language7 ~100%)。
- **用户入嵌**:从行为(收藏/心动/停留/跳过,权重 EVENT_W)做**掩码加权均值质心 μ**,与作品/大师同维 → 可直接算余弦。
- **距离与原型**:`dKG = 0.5·dWV + 0.3·dLang + 0.2·dAff`;6 世界观区 × 8 亚型 = 48 门派原型;"风格是其它层的投影"的本体立场。**(放 Fig 1)**

## 4. Recommendation as Familiar ↔ Surprise(算法层)
- **倒U 惊奇带**:`aha = exp(−(d−d*)²/2σ²)`,σ=0.20;d* 从"用户接受的跳跃幅度"**自学习**(因人而异,不写死)。
- **熟悉–惊喜混合**:`rel = (1−ex)·sim + ex·aha`,ex=探索度;**默认随成熟度** `clamp(0.25+0.45·maturity, 0.2, 0.7)`(冷启动偏熟悉、成熟才偏惊喜);用户可手动拨。**(放 Table 2:旋钮可控性)**
- **近来意图偏置**:把锚点 μ 朝近期"心愿"目标推 `μ_eff = clamp(μ + γ·conf·(target−μ))`,只动被提到的维度,**不改长期身份 μ**。

## 5. Multi-Modal Signals across Three Time Scales(系统层)
- **四种逛法 → 三张信号表**:看展(mu_event)/相框电台(expose·like·dislike)/语音心愿(mu_wish,**ASR→LLM 解析,会处理否定**)/生成(mu_generation)。
- **三层时间尺度**:此刻心情(≤30min→相框)/ 近来意图(7天半衰期→为你推荐)/ 长期身份(只看行为→审美档案);**陈述 vs 揭示偏好分离**——"说的话调给你看什么,做的事定你是谁"。
- **相框电台特有逻辑**:展示≠观看(presence gating)、曝光衰减 strike 的时间自愈(τ=3天)、召回冷却——一个把"被动环境展示"也变成信号的设计点。

## 6. Honest Evaluation(★ 卖点,放 Table 1)
- **可证伪评估台**:留一法 + 99 随机负采样 ×20;协同热度排除自身(去穿帮)。
- **基线对照与结果**:random/popularity/nearest/纯倒U/生产;诚实报"生产尚非赢"(AUC 0.32)。
- **准确率–serendipity 张力**:倒U被 next-item 准确率系统性惩罚——这正是它该做的(不预测下一次点击,而造惊喜);**消费一致 vs 探索两类用户需相反策略**的逐用户证据。
- **冷启动置信门控**:μ 在 12 维上需 ~20+ 正反馈才稳;档案按数据量分级(初识/成形中/清晰),不把猜测当定论。**(放 Fig 2)**

## 7. Discussion & Limitations
- **诚实交代规模**:N 用户少、serendipity 的在线 lift 尚未证明;不能宣称实证优越。
- **走向在线度量**:已上线推荐曝光日志 + rec_lift(曝光→后续参与的提升),离线代理看不见 serendipity,需在线/用户研究补(见 §6 的用户研究)。
- **设计含义(IUI/CHI 重点)**:当系统无法自动判别用户类型时,**把维度暴露成可控旋钮 + 诚实表达不确定性**,是比"赌一个全局模型"更负责任的人-AI 协作设计。

## 8. Conclusion
- 一张可解释的人画共享流形 + 倒U serendipity + 诚实评估;贡献不在"赢基线",在表示、系统与"准确率≠好审美推荐"的方法论洞见。开源评估台与 KG 切片。

---
**配图/表清单**:Fig 1 流形 · Fig 2 倒U+真实分布 · Table 1 基线对照 · Table 2 旋钮可控性 · (建议补)Fig 3 系统架构(四逛法→三层)· Fig 4 用户研究 serendipity 结果。
