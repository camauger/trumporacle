# Roadmap TRUMPORACLE

> Feuille de route du **dépôt** : état d’implémentation par rapport à [`trumporacle.mdc`](../trumporacle.mdc) §13 et à [`stack.md`](../stack.md). La spec gelée reste la source de vérité sur le périmètre fonctionnel et les critères de succès.

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
- **Postgres** : **Docker optionnel** (`docker-compose` + image Timescale/pgvector pour le local) ; **Neon / Postgres managé** pris en charge (Alembic sans `CREATE EXTENSION timescaledb` ni hypertable sur `raw_items`, extensions `vector` + `pg_trgm`).
- **Qualité config** : variables optionnelles vides (`TELEGRAM_*`, etc.) normalisées pour ne pas casser le chargement Settings.

**Suite hors gel Phase 0** (facultatif) : activer les tests d’intégration DB sur la CI ; vérifier que chaque machine de dev a les hooks pre-commit installés.

### Phase 1 — Corpus Truth + annotations
Découpage **technique (gel MVP)** vs **données & validation spec §9–10** (toujours ouvert).

**Livré dans le repo (pipeline Truth)**  
- Connecteur **RSS générique** (`TruthSocialRSSConnector` + `TRUTH_SOCIAL_RSS_URL`), persistance **`raw_items` → `items`**, annotation **LLM** si `ANTHROPIC_API_KEY`, CLI **`ingest-truth`**, boucle **`mvp-tick`** / jobs schedulés.
- **Backfill calendaire** : CLI **`backfill-truth --since YYYY-MM --until YYYY-MM [--base-url URL]`** boucle mois par mois sur `?start_date=…&end_date=…`, persiste `raw_items` + `items` (pas d’annotation LLM en backfill — opt-in via `ingest-truth` ensuite). Module : `trumporacle.ingestion.backfill`.
- **Échantillonnage stratifié spec §9.5** branché DB : CLI **`sample-validation --n 950 [--out path.jsonl] [--seed N]`** lit les items annotés LLM sans annotation humaine ni gold, applique les quotas `100×4 (niveaux 0-3) + 150×3 (niveaux 4-6) + 100 low-confidence + 100 boundary` (proxy `boundary` = `confidence ∈ [0.6, 0.75]`, faute de logits stockés par `instructor`), exporte un JSONL avec champs `human_*` à remplir. Module : `trumporacle.ingestion.sampling`.
- **Calcul Cohen’s κ + MAE + biais signé** : CLI **`validation-report [--out path.json]`** apparie la dernière annotation LLM et la dernière annotation humaine par item, applique les seuils spec §9.6 (`κ_global ≥ 0.70`, `κ_niv4-6 ≥ 0.50`, `MAE < 0.6`, `|biais| < 0.3`) et émet une décision `go | partial | no_go` avec liste des échecs. Module : `trumporacle.evaluation.validation_report`.

**Flux RSS recommandé (simple)**  
- **Trump’s Truth** ([Defending Democracy Together](https://defendingdemocracytogether.org/)) : `https://www.trumpstruth.org/feed` (XML). Fenêtre optionnelle : `?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD` (ex. mois calendaire pour backfill). Respecter leurs conditions d’usage ; ce n’est pas un flux officiel Truth Social.

**Reste pour alignement complet spec Phase 1** (données + temps humain, plus de code bloquant)  
- Lancer `backfill-truth` sur la fenêtre cible (~24 mois) puis annoter le corpus historique avec `ingest-truth` (clé Anthropic requise) ; coût/quotas LLM à surveiller.
- Annoter humainement les ~**500–950** items du JSONL produit par `sample-validation`, ré-importer dans `valence_annotations` (annotateur ≠ `llm*`), puis lancer `validation-report` pour la décision Go/No-Go formelle sur la rubrique LLM.

### Phase 2 — Fox & modèle tabulaire
- **Fait** : code captions Fox (segments, lecture fichier), baselines / entraînement côté `evaluation` et `prediction` (dont MVP baseline calibrée).
- **Fait (rapport backtest pragmatique)** : CLI **`evaluate-baseline --since YYYY-MM-DD --until YYYY-MM-DD [--train-until ...] [--out path.json]`** joint `predictions ⨝ outcomes`, recalcule **B1** (marginales train), **B2** (step sur `v_recent` 24 h Trump), **B3** (step sur `v_max` fenêtre précédente), **B4** (step sur moyenne valence écosystème 6 h) sur les mêmes fenêtres test, et émet **AUC-PR (sklearn) + ECE + MAE par cible × modèle**. Pas de stats inférentielles (pas de DeLong / bootstrap). Le rapport surface `ecosystem_posts_test` : si `0`, B4 est dégénéré (cas actuel sans Phase 3 ingérée) et c'est noté explicitement. Module : `trumporacle.evaluation.backtest_report` (mypy strict).
- **À faire** : pipeline Fox « prod » (captions + secours ASR), annotations valence transcripts, **B4 calibré probabiliste** (binning empirique vs step), backtests avec hygiène temporelle stricte (test ablatif sans features temporelles, validation multi-périodes), **gates §10.9** (DeLong / bootstrap pour décider la promotion d'un modèle).

### Phase 3 — Écosystème (Telegram, RSS, podcasts)
- **Fait** : modules RSS, Telegram, podcasts (`yt-dlp` + `faster-whisper`) au niveau bibliothèque.
- **Fait (RSS écosystème minimal)** : liste figée `ECOSYSTEM_FEEDS` dans `trumporacle.ingestion.rss.feeds` (Breitbart, Gateway Pundit, Federalist), pipeline `ingest_rss_ecosystem_once` qui boucle, persiste sans flag `trump_primary` (donc filtré comme écosystème par `mvp_features` et `backtest_report`), annote au LLM en tronquant à 4000 caractères. CLI **`ingest-rss`** + chaînage automatique dans `mvp-tick`. Fail-soft par feed (try/except + log + continue ; rollback global évité). **Effet mesuré** : `MvpFeatures.ecosystem_n_6h > 0` → B4 et `evaluate-baseline` sortent du mode dégénéré.
- **À faire** : Telegram + podcasts effectivement ingérés en jobs, **annotation paragraphe + global** sur articles longs (spec §9.7), volumétrie cible (~30-50 chaînes Telegram, top 10 podcasts), ablations « gain marginal par source », montées de version `feature_sets` traçables, **fix Gateway Pundit** (échec actuel via httpx user-agent par défaut → Cloudflare 403 ; injecter UA + retry/backoff suffit probablement).

### Phase 4 — Production & dashboard
- **Fait** : API FastAPI, vues HTMX, tick planifié (APScheduler), matérialisation outcomes, métriques techniques (ex. Prometheus).
- **À faire** : alerting drift / technique opérationnel (webhook), documentation utilisateur et runbooks déploiement (Caddy, systemd — exemples sous `deploy/`), contrôle d’accès au dashboard si exposition réseau.

### Phase 5 — Continu (re-training, qualité, diffusion)
- **Référence procédurale** : [`RETRAINING.md`](RETRAINING.md) (spec §12).
- **À faire** : premier cycle re-training mensuel **documenté de bout en bout**, revue hebdomadaire des erreurs / surprises (§10.8), tenir [`MODEL_CARD.md`](MODEL_CARD.md) et [`DATASHEET.md`](DATASHEET.md) à jour ; réévaluer **Prefect** si la logique de jobs dépasse le seuil décrit dans `stack.md`.

## Priorités suggérées (ordre indicatif)

1. Fermer les **critères quantitatifs Phase 1** (gold + κ + décision rubrique).
2. Rendre la boucle **Fox + fenêtres 2 h** **mesurable** de façon reproductible (données + outcomes).
3. Prioriser **une ou deux sources Phase 3** en ingestion régulière avant d’élargir tout le périmètre.
4. **Alertes** + supervision des coûts LLM et des échecs d’ingestion.
5. **Déploiement** long-vécu (VPS Québec / UE, hors contraintes US données si tu suis la spec §14.4).

## Rappel « ne pas ajouter »

Voir [`stack.md`](../stack.md) (Kafka, K8s, stack vectorielle dédiée, etc.) — chaque ajout doit passer le test *reprise après 3 semaines d’absence*.

---

*Mise à jour : mai 2026 — Phase 0/1 clarifiées (gel dépôt vs suite données). Ajuster quand une phase change de statut.*
