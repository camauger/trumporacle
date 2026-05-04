# Roadmap TRUMPORACLE

> Feuille de route du **dépôt** : état d'implémentation par rapport à [`trumporacle.mdc`](../trumporacle.mdc) §13 et à [`stack.md`](../stack.md). La spec gelée reste la source de vérité sur le périmètre fonctionnel et les critères de succès.

## État au 3 mai 2026

| Composant | État |
|---|---|
| Stockage | Neon Postgres ; Alembic à `head` ; ~880 fenêtres outcomes, 239 items annotés |
| Collecte | Task Scheduler Windows @ 15 min : Trump's Truth + Breitbart + Federalist |
| Rubrique LLM active | `llm_v1.2` — κ=0.317, MAE=0.50, biais=−0.34 sur audit 38 items |
| Modèle live | `mvp-baseline-b4soft-001` (formule sigmoïde non entraînée) |
| XGBoost entraîné | `c2_{3,4}_xgb_v1` en pickle ; **n'a pas dépassé MVP** sur ce volume — non promu en pipeline |
| Backtest | `evaluate-baseline` complet (B1, B2, B3, B4 calibrée, MVP) sur 267 fenêtres test |
| Dashboard | `/escalation-now` rendu (current window + 7j + escalades + calibration) |

**Verdict de phase** : Phase 0 finalisée, Phase 1 code complet (reste annotation humaine), Phase 2 partiellement faite (B4 calibrée + XGB feature-set), Phase 3 partielle (2 sources RSS), Phase 4 cœur livré, Phase 5 non commencée.

## Légende

| Symbole | Signification |
|--------|----------------|
| **Fait** | Présent dans ce repo et exploitable (éventuellement encore perfectible) |
| **En cours** | Amorcé : reste du filage, de la donnée ou de la validation |
| **À faire** | Non couvert ou critères spec non encore atteints |

## Phases (spec §13)

### Phase 0 — Fondations (**finalisée** côté dépôt)

Objectif spec §13 : environnement reproductible et schéma v1 — **atteint pour le périmètre code/outillage**.

- **Gelé** : paquets `uv`, recettes `just` (Git Bash + préfixe `.venv/Scripts`), `pytest`, CI minimale, `pydantic-settings` / `.env`, pré-commit prévu dans la stack.
- **Postgres** : Docker optionnel (`docker-compose` + image Timescale/pgvector pour le local) ; **Neon en production de fait** (Alembic sans `CREATE EXTENSION timescaledb` ni hypertable sur `raw_items`, extensions `vector` + `pg_trgm`).
- **Qualité config** : variables optionnelles vides (`TELEGRAM_*`, etc.) normalisées pour ne pas casser le chargement Settings.

**Suite hors gel Phase 0** (facultatif) : activer les tests d'intégration DB sur la CI ; vérifier que chaque machine de dev a les hooks pre-commit installés.

### Phase 1 — Corpus Truth + annotations

**Pipeline + outils livrés**

- Connecteur **RSS générique** (`TruthSocialRSSConnector` + `TRUTH_SOCIAL_RSS_URL`), persistance `raw_items` → `items`, annotation LLM si `ANTHROPIC_API_KEY`, CLI `ingest-truth`, boucle `mvp-tick`, jobs schedulés.
- **Backfill calendaire** : CLI `backfill-truth --since YYYY-MM --until YYYY-MM [--base-url URL]` boucle mois par mois sur `?start_date=…&end_date=…`. Module : `trumporacle.ingestion.backfill`.
- **Échantillonnage stratifié spec §9.5** branché DB : CLI `sample-validation --n 950 [--out path.jsonl] [--seed N]`. Quotas `100×4 (niveaux 0-3) + 150×3 (niveaux 4-6) + 100 low-confidence + 100 boundary` (proxy `boundary` = `confidence ∈ [0.6, 0.75]`). Module : `trumporacle.ingestion.sampling`.
- **Calcul Cohen's κ + MAE + biais signé** : CLI `validation-report [--out path.json]` apparie la dernière annotation LLM et la dernière humaine par item, applique les seuils spec §9.6, émet une décision `go | partial | no_go`. Module : `trumporacle.evaluation.validation_report`.
- **UI d'audit + analyseur** : `scripts/audit_ui.html` (vanilla JS, dark theme, autosave localStorage), `scripts/audit_rubric.py` (matrice de confusion, κ, MAE, mismatches niveau 4), `scripts/reannotate.py` (idempotent par version, ré-annoter à chaque bump `RUBRIC_VERSION`).

**Flux RSS recommandé**

- **Trump's Truth** ([Defending Democracy Together](https://defendingdemocracytogether.org/)) : `https://www.trumpstruth.org/feed` (XML). Fenêtre optionnelle `?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`. Respecter leurs conditions d'usage ; ce n'est pas un flux officiel Truth Social.

**Audit pilote rubrique LLM (mai 2026)**

- Sample 40 items zone décisive (LLM 2-6) annoté manuellement.
- Itérations : `v1.0` (κ=0.198, MAE=0.50, biais=−0.50, palier 4 raté 5/6 fois) → `v1.1` (κ=0.258, MAE=0.76, **5 items niveau 3 régressent vers 0/1**) → **`v1.2` actif** (κ=**0.317**, MAE=**0.50**, biais=**−0.34**) avec procédure de décision top-down et palier 3 élargi aux attaques de crédibilité non-littérales.
- Refactor `MAX(valence_level)` → `DISTINCT ON (item_id) ORDER BY annotated_at DESC, llm_labeler_version DESC` dans 5 requêtes (`mvp_features.py`, `outcomes_live.py`, `backtest_report.py`) : la pipeline utilise désormais la dernière annotation par item.
- **Recompute outcomes** (DELETE + re-materialize) avec les nouvelles requêtes : `v_max=4` passe de 0 à 41 fenêtres. Décision tracée : DELETE+recompute des outcomes calculés est légitime hors append-only (ce sont des dérivés des annotations).

**Reste pour alignement complet spec Phase 1** (données + temps humain, plus de code bloquant)

- Lancer `backfill-truth` sur la fenêtre cible (~24 mois) puis annoter le corpus historique avec `ingest-truth` (clé Anthropic requise).
- Annoter humainement les **500–950** items du JSONL produit par `sample-validation`, ré-importer dans `valence_annotations` (annotateur ≠ `llm*`), puis `validation-report` pour la décision Go/No-Go formelle.
- **CLI `import-human-validation` à écrire** : pas encore de chemin code pour ré-importer le JSONL annoté humainement vers `valence_annotations`.
- Si l'audit humain élargi révèle d'autres trous : itérer vers **rubrique v1.3** (cas-limites identifiés, regression tests sur le sample d'audit avant mass re-annotation).

### Phase 2 — Fox & modèle tabulaire

- **Fait (rapport backtest pragmatique)** : CLI `evaluate-baseline --since YYYY-MM-DD --until YYYY-MM-DD [--train-until ...] [--out path.json]` joint `predictions ⨝ outcomes`, recalcule **B1** (marginales train), **B2** (step sur `v_recent` 24 h Trump), **B3** (step sur `v_max` fenêtre précédente), **B4** sur les mêmes fenêtres test, et émet AUC-PR (sklearn) + ECE + MAE par cible × modèle. Pas de stats inférentielles. Module : `trumporacle.evaluation.backtest_report` (mypy strict).
- **Fait (B4 calibrée spec §10.3)** : remplacement du step `eco_mean ≥ k` par binning empirique 7 bins × `P(v_max ≥ k | bin)` appris sur le train, fallback marginal pour bins vides. ECE C2.3/C2.4 divisé par ~3-4 (0.14→0.04, 0.09→0.05). **Résultat scientifique** : sur ~9 jours d'écosystème (Breitbart + Federalist), AUC-PR ≈ base rate sur C2.3/C2.4 — **le signal écosystème seul n'a pas de pouvoir prédictif sur la valence Trump à 2 h** dans cette fenêtre. Hypothèse spec §1.2 non validée tant que la couverture écosystème reste à 2 sources.
- **Fait (XGBoost feature set `fs_xgb_001`)** : 20 features tabulaires versionnées (volumes 1/6/24h, valence agg + max, trends 3h, calendrier ET) dans `trumporacle.features.extended` (mypy strict). Script `scripts/train_xgb.py` : fit `XGBClassifier` + `CalibratedClassifierCV` isotonique 5-fold, MLflow tracking (`mlruns/`), pickle dans `artifacts/models/`. **Verdict empirique** : C2.3 XGB=0.245 vs MVP=0.250 (delta −0.005), C2.4 XGB=0.198 vs MVP=0.178 (delta +0.020 marginal). XGB bat B4 calibrée de +0.10-0.11 mais ne dépasse pas le MVP-formule. **Pas promu en pipeline live**. Plafond structurel : pas de features réseau ni embeddings textuels.
- **À faire** : pipeline Fox « prod » (captions + secours ASR), annotations valence transcripts, **B5 baseline non-recouvrante** (pour neutraliser l'autocorrélation B3 qui domine artificiellement), **test ablatif sans features temporelles** (spec §15.2), validation multi-périodes, **gates §10.9** (DeLong / bootstrap pour décider la promotion d'un modèle), itérer XGB **avec features réseau / lexical / topic** quand le corpus dépasse ~3000 fenêtres ou avec embeddings textuels pour battre B3 réellement.

### Phase 3 — Écosystème (Telegram, RSS, podcasts)

- **Fait** : modules RSS, Telegram, podcasts (`yt-dlp` + `faster-whisper`) au niveau bibliothèque.
- **Fait (RSS écosystème minimal)** : liste figée `ECOSYSTEM_FEEDS` dans `trumporacle.ingestion.rss.feeds` (Breitbart, Gateway Pundit, Federalist), pipeline `ingest_rss_ecosystem_once` qui boucle, persiste sans flag `trump_primary` (donc filtré comme écosystème par `mvp_features` et `backtest_report`), annote au LLM en tronquant à 4000 caractères. CLI `ingest-rss` + chaînage automatique dans `mvp-tick`. Fail-soft par feed (try/except + log + continue ; rollback global évité). **Effet mesuré** : `MvpFeatures.ecosystem_n_6h > 0` → B4 et `evaluate-baseline` sortent du mode dégénéré.
- **À faire** : **fix Gateway Pundit** (échec via httpx UA par défaut → Cloudflare 403 ; injecter UA réaliste suffit probablement), Telegram + podcasts effectivement ingérés en jobs, **annotation paragraphe + global** sur articles longs (spec §9.7), volumétrie cible (~30-50 chaînes Telegram, top 10 podcasts), ablations « gain marginal par source », montées de version `feature_sets` traçables.

### Phase 4 — Production & dashboard

- **Fait** : API FastAPI, vues HTMX, tick planifié (APScheduler **dans le serveur** + **Task Scheduler Windows** en dehors via `scripts/tick.sh` + `scripts/register-task.ps1`), matérialisation outcomes, métriques techniques (Prometheus `/metrics`).
- **Fait (page `/escalation-now`)** : 4 sections — fenêtre courante (P(v≥4) + P(v≥5) en cards visuelles avec barres de progression), évolution 7 jours (SVG line chart c2_4 + c2_5 + dots événements observés), 3 dernières escalades v_max≥3 avec posts Trump réels affichés, 2 plots de calibration (C2.4 et C2.5) avec ECE. Vanilla JS/CSS, dark theme. Modules : `dashboard/queries.py` (mypy strict), `dashboard/templates/escalation_now.html.j2`. Lien depuis `/`.
- **À faire** : alerting drift / technique opérationnel (webhook Discord déjà en config, pas branché), refresh auto via HTMX (`hx-trigger="every 60s"`), runbooks déploiement (Caddy, systemd — exemples sous `deploy/`), contrôle d'accès au dashboard si exposition réseau, **flag `TRUMPORACLE_DISABLE_SCHEDULER`** pour éviter le doublon entre Task Scheduler et APScheduler interne quand on lance le serveur en local.

### Phase 5 — Continu (re-training, qualité, diffusion)

- **Référence procédurale** : [`RETRAINING.md`](RETRAINING.md) (spec §12).
- **À faire** : premier cycle re-training mensuel **documenté de bout en bout**, revue hebdomadaire des erreurs / surprises (§10.8), tenir [`MODEL_CARD.md`](MODEL_CARD.md) et [`DATASHEET.md`](DATASHEET.md) à jour ; réévaluer **Prefect** si la logique de jobs dépasse le seuil décrit dans `stack.md`.

## Priorités suggérées (ordre indicatif)

1. **Laisser tourner 2-4 semaines** pour atteindre ~3000+ fenêtres outcomes ; refaire alors `evaluate-baseline` et `train_xgb.py` avec un dataset plus large.
2. **Fix Gateway Pundit + ajouter Fox News** (transcripts via captions) pour enrichir B4 et tester l'hypothèse §1.2 sur un écosystème plus large.
3. **B5 non-recouvrante** dans `backtest_report.py` pour neutraliser l'artefact B3=0.77.
4. **Annotation humaine 500-950 items** (Phase 1) + `import-human-validation` CLI, pour fermer le critère κ ≥ 0.70 (ou décider que c'est inatteignable et le documenter).
5. **Alerting Discord** + supervision coûts LLM (cron simple sur le compteur Anthropic).
6. **Déploiement long-vécu** (VPS Québec / UE, hors juridiction US §14.4) une fois (1)-(4) stabilisés.

## Rappel « ne pas ajouter »

Voir [`stack.md`](../stack.md) (Kafka, K8s, stack vectorielle dédiée, etc.) — chaque ajout doit passer le test *reprise après 3 semaines d'absence*.

---

*Mise à jour : 3 mai 2026 — session intensive (rubrique v1.0 → v1.2, refactor MAX → latest, recompute outcomes, B4 calibrée, XGB entraîné non-promu, dashboard `/escalation-now`). Prochaine mise à jour : après accumulation de 2-4 semaines de données et fix Gateway Pundit + Fox.*
