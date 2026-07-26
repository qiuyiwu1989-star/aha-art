# Finding the *Aha*, Not the Nearest: A Shared, Interpretable Aesthetic Manifold for Human–Artwork Recommendation

**Working draft v1 — target: ACM IUI 2027 (full paper, due 2026-08-20); fallback CHI 2027 (2026-09-10).**
Authors: **TBD（作者待定）**. *Affiliations TBD. Note: IUI/CHI use double-blind review — the submitted PDF must be fully anonymized (no names, affiliations, or self-identifying URLs such as `aha.yishujia.art`; cite your own prior work in third person).*

> **How to use this draft.** Prose is written for the sections that do **not** depend on new data (Intro, Related Work, System, Representation). Sections that need data you will add later are written with current real numbers **plus clearly marked `⟦FILL: …⟧` placeholders** (the user study, the larger-scale and online evaluation). Real numbers already in the text come from `eval_recsys.py` and `gen_figures.py`.

---

## Abstract

Aesthetic recommendation is usually framed as similarity matching, yet what delights a viewer before a painting is rarely the *most similar* work but the one that produces an *aha* — novel enough to surprise, anchored enough to be understood. We present **aha**, a museum-scale system that embeds **both artworks and users in a single, interpretable 12-dimensional aesthetic manifold** spanning worldview (2D), pictorial language (7D), and affective valence–arousal–dominance (3D). Over 8,000 paintings are positioned along these axes by a vision–language model, and each user is embedded in the *same* space from behaviour, making people and masters directly cosine-comparable. Recommendation combines an inverted-U "surprise-band" term (after Berlyne) with a similarity term under a user-tunable **familiar↔surprise** control, and integrates four interaction modalities — gallery browsing, an ambient "radio" frame, spoken wishes, and generation — across **three time scales** (momentary mood, recent intent, long-term identity), so that *stated* preferences never overwrite *revealed* ones. We contribute a **falsifiable offline evaluation harness** and an honest finding: standard next-item accuracy **systematically penalizes the very serendipity the system optimizes for**, and users split into "consistent" and "exploratory" types that demand opposite strategies — motivating maturity-gated confidence and explicit user control over a single global model. ⟦FILL: one sentence with the user-study headline once collected.⟧ We release the evaluation harness and a slice of the knowledge graph.

**CCS Concepts:** Information systems → Recommender systems; Human-centered computing → Interactive systems and tools. **Keywords:** aesthetic recommendation, serendipity, computational aesthetics, knowledge graph, vision–language models, cold-start, interactive control.

---

## 1 Introduction

Stand in front of a painting that moves you, and ask why. The answer is rarely *"because it is the most similar to what I already like."* More often it is a small jolt of recognition — *"oh, so this is possible too"* — a work novel enough to surprise yet anchored enough to be grasped. Experimental aesthetics has a name for this shape: Berlyne's inverted-U, in which preference peaks at an intermediate level of novelty/arousal rather than at maximal familiarity [Berlyne 1971]. Yet most art and aesthetic recommenders optimize similarity, and thereby optimize *away* the very experience that makes looking at art worthwhile.

We argue that aesthetic recommendation needs three things it usually lacks: (i) a representation in which *people and artworks live in the same interpretable space*, so that "what fits you" is a geometric statement rather than an opaque score; (ii) a scoring rule that can deliberately target the **surprise band** — close enough to be understood, far enough to be new — instead of the nearest neighbour; and (iii) an honest reckoning with the fact that **the metrics we usually optimize cannot see serendipity at all.**

This paper presents **aha**, a deployed, museum-scale system (`aha.yishujia.art`) built around these three commitments. Our contributions are:

1. **A shared, interpretable aesthetic manifold (§3).** Both 8,106 artworks and every user are embedded in the same 12-dimensional space — worldview (2D), pictorial language (7D), and affect (3D, valence–arousal–dominance). Artworks are positioned by a vision–language model (VLM); users by their behaviour. People and masters become directly cosine-comparable (Fig. 1).
2. **Recommendation as a familiar↔surprise blend, with multi-modal signals over three time scales (§4–§5).** An inverted-U surprise-band term with a self-learned per-user width is mixed with a similarity term under a user-tunable control. Four interaction modalities (browsing, an ambient frame, spoken wishes, generation) feed three time scales — momentary mood, recent intent, long-term identity — keeping stated preferences from overwriting revealed ones.
3. **An honest evaluation (§6).** We build a falsifiable offline harness and report a negative-but-instructive result: next-item accuracy *penalizes* the inverted-U by construction, and data-rich users split into "consistent" and "exploratory" types requiring opposite strategies — which motivates exposing the familiar↔surprise dimension as user control and gating confidence by data maturity, rather than betting on one global model.

We deliberately **do not** claim to beat baselines on an accuracy benchmark; at our current scale that claim would be unsupportable and, we will argue, partly beside the point. Our contributions are a representation, a system design, and a methodological insight about what "good aesthetic recommendation" should even be measured against.

## 2 Related Work

**Visual art recommendation (closest prior work).** Yilma and Leiva learn *latent* semantic representations of paintings from textual and visual features and their fusion for personalised recommendation [Yilma & Leiva 2023], and extend visual-art recommender systems (VA RecSys) to therapeutic, affect-oriented settings — recommending art to mitigate post-intensive-care syndrome, validated against expert curation in a 150-participant study [Yilma et al. 2024]. Our work differs on three axes. *(i) Interpretable vs. latent:* instead of latent embeddings we use an explicit, axis-aligned aesthetic coordinate system (worldview / pictorial language / affect), so distances, regions, and the recommendations themselves are legible. *(ii) A shared user–artwork space:* we embed users in the *same* space as artworks and master-artist centroids, yielding cosine-comparable "soulmate" artists and 48 archetypes — not only item embeddings. *(iii) Serendipity over relevance:* we centre an inverted-U surprise objective and give an honest account of why accuracy metrics penalize it. Their affect-driven, wellbeing framing motivates our affective (VAD) layer and low-arousal "calm" channel; their large user studies set a bar our (smaller, §6.5) study acknowledges.

**Art knowledge graphs and contextual visual features.** Castellano et al. build *ArtGraph* (from WikiArt and DBpedia) and inject KG embeddings into deep models to improve fine-art **attribute classification** [Castellano et al. 2021, 2022]. We likewise fuse structured knowledge with visual reading, but toward **recommendation inside a shared aesthetic manifold** rather than classification: the graph's geometry *is* the recommendation space, and users inhabit it.

**Cultural-heritage multimodal knowledge graphs.** A growing line builds multimodal KGs for heritage management, retrieval, and QA [Huang et al. 2023], including Chinese-art resources: **WuMKG**, a Chinese painting-and-calligraphy multimodal KG with a domain ontology, seal/subject extraction, and cross-modal retrieval/QA [Wan et al. 2024], and CICHMKG for intangible heritage [CICHMKG 2023]. Our graph shares the Chinese-art domain (e.g., Ni Zan, Bada Shanren) and multimodality, but rests on an **aesthetic** ontology (worldview/language/affect axes) for **personalised, serendipitous recommendation with users embedded in the graph**, rather than bibliographic organisation or QA. This also positions a resource-framed version of our system for venues such as *Heritage Science*.

**Computational aesthetics, art-emotion, serendipity, cold-start.** Beyond predicting aesthetic *quality* [Datta et al. 2006] or learning style embeddings [Karayev et al. 2014], we build an interpretable coordinate system shared by artworks and people; the *affective* response to art has dedicated resources — e.g., ArtEmis's 455K emotion attributions for visual art [Achlioptas et al. 2021] — that motivate our VAD layer. Beyond-accuracy objectives have long been argued to matter more than raw accuracy [McNee et al. 2006; Kotkov et al. 2016], and serendipity is especially hard to measure offline [Ge et al. 2010], usually needing user judgement. Berlyne's inverted-U [1971] grounds our surprise band; we add evidence that leave-one-out accuracy is *anti-correlated* with it. Finally, recommenders must reconcile *stated* (explicit) and *revealed* (implicit-feedback [Hu et al. 2008]) preferences and survive cold-start [Schein et al. 2002]; we separate these into three time scales and gate confidence by data maturity, surfacing uncertainty rather than hiding it.

## 3 A Shared Aesthetic Manifold

### 3.1 Three observable layers (12 dimensions)
We represent every artwork and every user as a point in a 12-D manifold composed of three psychologically and art-historically motivated layers:
- **Worldview (2D)** — a *representation→expression* axis (x: faithful depiction → subjective/abstract) orthogonal to a *structure→sensation* axis (y: order/geometry → atmosphere/light/instant).
- **Pictorial language (7D)** — composition, space, form, light-and-shade, colour, brushwork, edge — each a 0–1 axis.
- **Affect (3D)** — valence, arousal, dominance (VAD).

The two worldview axes act as a low-dimensional "mounting point" onto which the other layers project; we adopt the stance that *style is a projection* of these layers rather than an independent attribute.

### 3.2 Artworks: VLM extraction at scale
A vision–language model (MiMo) reads each painting and scores the layers above, calibrated against anchored exemplars (e.g., photorealism ≈ 0.10 on the representation axis; *Water-Lilies*-style diffuse light ≈ 0.93 on the sensation axis). Of 8,106 curated ("kept") works, coverage is: worldview 89%, affect (VAD) ~100%, pictorial language ~100%. ⟦FILL: VLM agreement/validation — e.g., correlation between VLM axes and a held-out human-labelled subset; we have partial signals to report.⟧

### 3.3 Users: same space, from behaviour
A user's centroid **μ** is the masked, weighted mean of the vectors of the works they engaged, with event weights (like/collect = 3, dwell/generate = 2, open = 1, view = 0.3, skip = −1). Masking lets partially-vectorized works still contribute on the dimensions they have. Because μ lives in the same 12-D space as artworks and master-artist centroids, "fit" is a distance and the *soulmate artist* is simply the nearest master (Fig. 1).

### 3.4 Distance, archetypes, "style as projection"
We use a subspace-weighted distance `dKG = 0.5·dWV + 0.3·dLang + 0.2·dAff` (each subspace normalized to [0,1]). The six worldview regions × eight binary sub-types (focus/settled/cautious) yield **48 aesthetic archetypes**, a legible "MBTI-for-taste" surface over a continuous space. **Figure 1** plots 1,600 sampled works, the six region centres, six master centroids, and a user μ in the worldview plane: people and masters demonstrably inhabit the same manifold.

## 4 Recommendation as Familiar ↔ Surprise

### 4.1 The inverted-U surprise band
The surprise term is `aha(d) = exp(−(d−d*)²/2σ²)` with σ = 0.20, peaking at distance **d\*** — the user's personal "surprise band," **self-learned** as the mean accepted-jump distance (clamped to [0.15, 0.6]); for data-rich users d* ≈ 0.19–0.23. Too-near works (already known) and too-far works (ungraspable) both score low; "just-new" scores highest. **Figure 2** shows the curve together with the *actual* distribution of a deployed user's top-24 recommendations (0.158–0.206), which cluster on d\* rather than at the nearest neighbour.

### 4.2 A tunable familiar–surprise blend
Crucially (and motivated by §6), production scoring is **not** pure inverted-U. We mix in a similarity term:
`rel = (1 − ex)·sim + ex·aha`, with `sim = 1 − d`, and final score `= rel + w_calm·calm + w_qual·qual`. The **explore weight ex** is the user-facing *familiar↔surprise* slider; its default tracks data maturity, `ex = clamp(0.25 + 0.45·maturity, 0.2, 0.7)` (cold start leans familiar/similar — the only content signal that beats random at low data; matured profiles lean toward surprise). Table 2 shows the control is effective: setting ex = 0.2 yields recommendations at median distance 0.112 (close to μ), ex = 0.85 yields 0.184 (on the band).

### 4.3 Recent-intent bias from spoken wishes
A spoken "wish" ("show me something quiet," "nothing too calm — something bold") is transcribed by ASR and parsed by an LLM into target (region, valence, arousal), **handling negation** that keyword matching gets backwards. Recent wishes (45-day window, 7-day half-life) shift the anchor: `μ_eff = clamp(μ + γ·conf·(target − μ))` on the mentioned dimensions only (γ = 0.6), **never altering the long-term identity μ**.

## 5 Multi-Modal Signals across Three Time Scales

**Figure 3** summarizes the architecture. Four ways of "browsing" leave different traces in three signal tables, which feed three time scales:

- **Gallery browsing** (open/dwell/like/collect/skip; a two-alternative onboarding where the *unchosen* option is a weak negative) → `mu_event`.
- **An ambient "radio" frame** — passive rotation where *display ≠ viewing*: an exposed-but-uninteracted work counts only as a weak "exposure," whose suppression **heals over time** (decay τ = 3 days), so the system behaves like a radio gradually learning a listener's taste.
- **Spoken wishes** → `mu_wish` (§4.3).
- **Generation** in an intent-compiler → `mu_generation`.

These resolve into **(i) momentary mood** (≤30 min → the frame), **(ii) recent intent** (7-day half-life → recommendations), and **(iii) long-term identity** (behaviour-only → the aesthetic profile μ, archetype, and "three lamps" of journey quality). The guiding principle: *what you say tunes what you are shown; what you do defines who you are* — stated and revealed preferences combined but never overwriting one another.

## 6 Honest Evaluation

### 6.1 A falsifiable harness
We evaluate with leave-one-out and 99 sampled negatives (×20 repeats); collaborative "popularity" excludes the held-out user to remove self-leakage. The harness (`eval_recsys.py`) is released. **Scale caveat (stated up front):** the deployment currently has 29 users and 1,631 interaction events (median 5 events/user); only 6 users clear the threshold for leave-one-out evaluation. We therefore treat these results as *directional*, not conclusive.

### 6.2 Baselines and results
Table 1 compares production scoring against random, popularity, nearest-neighbour, and pure inverted-U.

| Strategy | HR@5 | HR@10 | MRR | AUC |
|---|---|---|---|---|
| Production (old: inverted-U + calm + qual) | 0.167 | 0.167 | 0.15 | **0.32** |
| Pure inverted-U | 0.00 | 0.04 | 0.03 | 0.48 |
| Nearest-neighbour (similarity) | 0.30 | **0.33** | 0.22 | **0.54** |
| Collaborative (others' likes)¹ | 1.00 | 1.00 | 0.85 | 1.00 |
| Random (baseline) | 0.08 | 0.11 | 0.07 | 0.51 |

¹ Inflated by a small, highly-overlapping demo community; an upper bound, not a fair score. Random calibrates at HR@10 ≈ 0.10, AUC ≈ 0.50.

### 6.3 The accuracy–serendipity tension, and two user types
Two facts stand out. First, **the inverted-U scores *below random* on next-item accuracy (AUC 0.32–0.48)** — *by construction*, because it deliberately avoids the nearest neighbour, which is exactly what a "predict the next click" metric rewards. This is not a bug to be tuned away; it is evidence that **next-item accuracy is the wrong yardstick for serendipity.** Second, among data-rich users the right strategy *inverts per person*: for user A (n = 318) nearest-neighbour ranks the held-out like **1st** while inverted-U ranks it **92nd**; for user B (n = 621) inverted-U ranks it **1.2** on average while nearest-neighbour ranks it **68th**. No single global blend can serve both: some users' next love is *near* their taste ("consistent"), others' is a *jump* ("exploratory"). When a system cannot yet infer the type, the honest design is to **expose the dimension as a control** (§4.2) rather than gamble on a global weight.

### 6.4 Cold-start confidence gating
A 12-D μ needs ~20+ positive signals to stabilize; with a median of 6, most users are deep in cold-start. The interface therefore grades each profile by **maturity** (`clamp(n/22)`; levels *nascent < 8 / forming < 20 / clear ≥ 20*) and labels low-maturity archetypes as *preliminary*, refusing to present a guess as a verdict.

### 6.5 Toward measuring serendipity directly ⟦FILL — user study⟧
Because offline proxies cannot see serendipity, we ran a within-subject study (N = ⟦FILL⟧) contrasting *familiar* (ex≈0.2), *surprise* (ex≈0.8), and *random* conditions, rating each recommendation on liking, familiarity, **aha**, and graspability. ⟦FILL: report Aha-rate per condition, liking parity, RQ2 knob-preference bimodality, RQ3 trust under confidence gating; insert Fig. 4 (grouped bars).⟧ We additionally instrument recommendation impressions online (`rec_lift`: post-impression engagement vs. base rate) ⟦FILL: report lift once accumulated.⟧

## 7 Discussion and Limitations

**What we can and cannot claim.** We do not demonstrate empirical superiority on accuracy; our data is small and homogeneous, and the inverted-U is, by design, ill-served by accuracy metrics. What we offer is an interpretable shared representation, a multi-modal three-timescale system, and the methodological point that **serendipitous aesthetic recommendation must be evaluated by what it is for** (the *aha*), not by next-click prediction.

**Validity threats.** VLM-extracted axes are point estimates without uncertainty, and some dimensions do correlate: across the corpus the 12 axes have a **mean absolute correlation of only 0.17** (max 0.51); an eigenvalue participation ratio gives an **effective dimensionality ≈ 8 of 12**, and 8 principal components capture 90% of variance. The strongest pairs are intuitive — space↔light (r=0.51), composition↔form (r=0.49), representation↔arousal (r=0.49) — suggesting future axis consolidation but confirming the space is **far from degenerate**. The collaborative signal is inflated by a small community. The user study is the load-bearing evidence for the serendipity claim.

**Design implications (for IUI/CHI).** When a system cannot infer a user's type, surfacing the latent dimension as a legible control, and *honestly communicating uncertainty* (maturity gating), is a more responsible human–AI design than committing to a single opaque global model. This generalizes beyond art to any taste domain where "more of the same" and "show me something new" genuinely conflict.

## 8 Conclusion
We presented a human-and-artwork **shared aesthetic manifold**, an inverted-U **familiar↔surprise** recommender fed by multi-modal signals across three time scales, and an **honest evaluation** showing why accuracy metrics misjudge serendipity and why users demand opposite strategies. The contribution is a representation, a system, and a stance: aesthetic recommendation should help you find the *aha*, not the nearest. We release the evaluation harness and a knowledge-graph slice.

---

### Figures & Tables
- **Fig. 1** Shared aesthetic manifold (worldview plane): works · region centres · master centroids · user μ. — `figures/fig1_manifold.svg`
- **Fig. 2** Inverted-U surprise band + real top-24 recommendation distribution (peak at self-learned d\*). — `figures/fig2_invertedU.svg`
- **Fig. 3** System architecture: four modalities → three signal tables → three time scales → scoring. — `figures/fig3_architecture.svg`
- **Fig. 4** ⟦FILL⟧ User-study results (Aha / Liking / Graspability by condition).
- **Table 1** Offline baseline comparison (LOO + sampled negatives). **Table 2** Familiar↔surprise control (distance vs. ex).

### References
- Yilma, B.A., Leiva, L.A. **The Elements of Visual Art Recommendation: Learning Latent Semantic Representations of Paintings.** CHI 2023. DOI 10.1145/3544548.3581477.
- Yilma, B.A., Kim, C.M., Cupchik, G.C., Leiva, L.A. **Artful Path to Healing: Using Machine Learning for Visual Art Recommendation to Prevent and Reduce Post-Intensive Care Syndrome (PICS).** CHI 2024. DOI 10.1145/3613904.3642636.
- Yilma, B.A., Leiva, L.A. **Together Yet Apart: Multimodal Representation Learning for Personalised Visual Art Recommendation.** UMAP 2023. DOI 10.1145/3565472.3592964.
- Castellano, G., Sansaro, G., Vessio, G. **Integrating Contextual Knowledge to Visual Features for Fine Art Classification.** DL4KG 2021. arXiv:2105.15028. *(journal ext.: Castellano et al., Leveraging Knowledge Graphs and Deep Learning for automatic art analysis, KBS 2022.)*
- Wan, J., Zhang, H., Zou, J., et al. **WuMKG: a Chinese painting and calligraphy multimodal knowledge graph.** Heritage Science 12, 159 (2024). DOI 10.1186/s40494-024-01268-4.
- Huang, Y., Yu, S., Chu, J., Fan, H., Du, B. **Using knowledge graphs and deep learning algorithms to enhance digital cultural heritage management.** Heritage Science 11, 204 (2023). DOI 10.1186/s40494-023-01042-y. · CICHMKG: a large-scale Chinese intangible cultural heritage multimodal KG. Heritage Science, 2023.
- Achlioptas, P., Ovsjanikov, M., Haydarov, K., Elhoseiny, M., Guibas, L. **ArtEmis: Affective Language for Visual Art.** CVPR 2021. DOI 10.1109/CVPR46437.2021.01140.
- Karayev, S., Trentacoste, M., Han, H., Agarwala, A., Darrell, T., Hertzmann, A., Winnemoeller, H. **Recognizing Image Style.** BMVC 2014.
- Ge, M., Delgado-Battenfeld, C., Jannach, D. **Beyond Accuracy: Evaluating Recommender Systems by Coverage and Serendipity.** RecSys 2010.
- Hu, Y., Koren, Y., Volinsky, C. **Collaborative Filtering for Implicit Feedback Datasets.** IEEE ICDM 2008.
- Schein, A.I., Popescul, A., Ungar, L.H., Pennock, D.M. **Methods and Metrics for Cold-Start Recommendations.** SIGIR 2002.
- Berlyne, D.E. *Aesthetics and Psychobiology*, 1971. · McNee, S., Riedl, J., Konstan, J. *Being Accurate is Not Enough*, CHI EA 2006. · Kotkov, D., Wang, S., Veijalainen, J. *A survey of serendipity in recommender systems*, KBS 2016. · Datta, R. et al. *Studying Aesthetics in Photographic Images*, ECCV 2006.

### Reproducibility
`python3 aha-art/pipeline/eval_recsys.py` (Table 1) · `python3 aha-art/docs/paper/gen_figures.py && gen_fig3.py` (Figs 1–3). Release plan: evaluation harness + KG schema and a sample of work vectors (worldview/language/VAD).
