## Principe directeur

Tu as deux contraintes structurantes qui orientent tout :
1. **Tu travailles seul, en Python, sans framework lourd.** Optimise pour la vélocité d'un développeur unique, pas pour la scalabilité d'une équipe.
2. **Le projet a une longue queue temporelle.** Tu ingères, tu annotes, tu entraînes, tu sers — sur des mois. La stack doit minimiser le coût de **reprise** d'un module après 3 semaines d'absence.

Conséquence : préférer **boring tech**, monolithe modulaire, peu de dépendances, observabilité maximale.

## Stack par couche

### Langage et runtime

**Python 3.12+**, sans débat. Tout l'écosystème ML/NLP y est, tu y es à l'aise.

Gestionnaire de paquets : **`uv`** d'Astral, pas Poetry ni pip-tools. C'est devenu le standard de fait en 2025, 10-100x plus rapide, gère les Python embarqués, et le lock-file est solide. Poetry est en perte de vitesse et a des problèmes récurrents de résolution.

Type checker : **`mypy`** en mode strict sur le code de prédiction et d'évaluation, plus permissif sur l'ingestion (où le typage des sources externes est galère). `pyright` est plus rapide mais `mypy` reste mieux intégré aux outils.

Linter et formatter : **`ruff`** seul, qui remplace black + isort + flake8 + plusieurs autres. Configuration unique, vitesse imbattable.

### Base de données

**PostgreSQL 16** avec trois extensions : `TimescaleDB`, `pgvector`, `pg_trgm`.

Décision importante : **un seul Postgres pour tout**, pas de stack séparée Elasticsearch + Pinecone + Redis. Pourquoi :
- `pgvector` couvre les embeddings (HNSW indexing depuis la v0.5, performance excellente jusqu'à ~10M vecteurs)
- `TimescaleDB` couvre les séries temporelles avec des hypertables et continuous aggregates
- `pg_trgm` couvre la recherche full-text fuzzy
- Tu as **une seule chose à backuper, monitorer, comprendre**

Le piège classique en projet ML solo : empiler 5 datastores parce que chacun excelle dans son domaine, puis passer 30 % du temps à synchroniser leurs états. Postgres est suffisant jusqu'à ce que tu aies un problème prouvé qui justifie d'ajouter quelque chose.

ORM ou pas ? **`SQLAlchemy 2.0` en mode core (pas l'ORM)**, plus `asyncpg` directement pour les chemins critiques (ingestion à haut débit, inférence). L'ORM est un piège pour les requêtes analytiques. Pour la migration de schéma : **`Alembic`**.

### Validation et schémas

**`Pydantic v2`** pour toute donnée qui traverse une frontière (input/output API, config, validation des items ingérés, payloads JSONB). Performance excellente depuis v2 (cœur en Rust). Bonus : intégration native avec FastAPI.

### Ingestion

**`httpx`** pour HTTP (sync et async), pas `requests`. Plus moderne, support HTTP/2, async natif.

**`asyncio`** pour la concurrence I/O. Pas Celery, pas RabbitMQ, **pas Kafka**. Pour ton volume (quelques milliers d'items/jour), un orchestrateur simple suffit largement.

**`tenacity`** pour le retry avec backoff exponentiel — non négociable sur du scraping fragile.

**`feedparser`** pour les RSS, **`selectolax`** plutôt que BeautifulSoup pour le parsing HTML (10x plus rapide, API similaire, bibliothèque Rust dessous).

Pour Telegram : **`telethon`** (client Python officieux mais le plus mature pour l'API MTProto, supérieur à python-telegram-bot pour la lecture de chaînes publiques).

Pour les podcasts : **`yt-dlp`** pour le téléchargement audio, **`faster-whisper`** pour la transcription locale (4x plus rapide que `openai-whisper` standard, basé sur CTranslate2).

### NLP et embeddings

**`spaCy`** pour la NER et le tokenizing. Modèles `en_core_web_lg` ou `en_core_web_trf`. Mature, rapide, prédictible.

**`sentence-transformers`** pour les embeddings, modèle de référence : **`BAAI/bge-large-en-v1.5`** (1024 dim, excellent rapport qualité/vitesse) ou **`BAAI/bge-m3`** si tu veux du multilingue (utile si une partie du corpus Telegram est en russe ou autre).

Topic modeling : **`BERTopic`** pour la découverte initiale de la taxonomie (section 9 de la spec). Une fois la taxonomie figée, tu n'en as plus besoin — un classifieur supervisé prend le relais.

### LLM-labeler

**API Anthropic directement** via le SDK `anthropic`. Modèle : Claude Haiku 4.5 pour le labeling de masse, Claude Sonnet 4.6 pour les cas-limites et la curation. Pas besoin de LangChain ni LlamaIndex — c'est de la sur-ingénierie pour un appel API structuré.

**`instructor`** (de Jason Liu) pour valider les sorties JSON contre un schéma Pydantic. C'est la couche minimale qui apporte une vraie valeur sans verrouiller dans un framework.

**Batching et caching** : implémentation maison simple. Cache disque via `diskcache` pour la résilience aux re-runs (clé = hash du prompt + version du labeler).

### Modélisation ML

Pour la modélisation tabulaire (cibles C1, C2.k, C3) :
- **`XGBoost`** comme cheval de bataille principal
- **`LightGBM`** comme alternative à benchmarker (souvent légèrement meilleur sur tabulaire à features hétérogènes)
- **`scikit-learn`** pour les baselines, le pré/post-traitement, les pipelines de calibration
- **Pas de PyTorch / réseaux de neurones tabulaires** au MVP. TabNet et FT-Transformer sont marginalement meilleurs sur certains benchmarks, mais le coût de déploiement et de maintenance les disqualifie pour un solo dev.

Pour C4 (présence d'un post / timing) :
- **`lifelines`** pour les modèles de survie (Cox, Aalen)
- Si tu trouves les modèles paramétriques limitants : **`scikit-survival`** ajoute des forêts de survie

Calibration : **`sklearn.calibration.IsotonicRegression`**, comme figé en spec.

Tracking d'expériences : **`MLflow`** en mode local (file backend), pas le service cloud. Tu logges runs, paramètres, métriques, artefacts. Léger, standard, te permettra de répondre à « pourquoi ce modèle vs le précédent ? » dans 6 mois.

Pour le versioning des datasets et modèles : **DVC** est l'option « propre », mais **Git LFS + une convention de nommage stricte sur S3-compatible** est plus simple et te servira aussi bien à ton échelle. À reconsidérer si l'équipe grandit.

### Orchestration

C'est le choix le plus piégé. Voici la matrice :

| Outil | Quand l'utiliser | Pour ce projet |
|---|---|---|
| **`APScheduler`** | Cron-like avec persistance, monolithe Python | ✅ MVP |
| **`Prefect`** | Workflows complexes, retry granulaire, observabilité | Envisageable phase 4 |
| **`Dagster`** | Asset-oriented, lineage, équipes ML matures | Sur-ingénierie pour solo |
| **`Airflow`** | Standard d'équipe data, DAGs lourds | À éviter en solo, complexité disproportionnée |
| **`cron + scripts`** | Très simple, peu d'observabilité | Insuffisant ici |

**Recommandation : `APScheduler` au sein du même process Python que ton API**. Tu ajoutes un dashboard d'admin minimal pour voir l'état des jobs. Si tu te retrouves à écrire ta propre logique de retry, dépendances entre tâches, et observabilité au-delà de 200 lignes, c'est le signal pour passer à Prefect — pas avant.

### API et dashboard

**`FastAPI`** pour l'API (cohérent avec ton expérience Python, async natif, OpenAPI auto, intégration Pydantic).

Pour le frontend du dashboard, trois options :
1. **`FastAPI + Jinja2 + HTMX + Alpine.js`** — minimaliste, vanilla, recommandé
2. **`Streamlit`** — rapide pour prototyper mais limité dès que tu veux du custom
3. **`Plotly Dash`** — plus puissant que Streamlit pour la dataviz, mais courbe d'apprentissage

**Recommandation forte : option 1**. C'est aligné avec ta préférence vanilla. HTMX permet des dashboards interactifs sans React/Vue, Alpine.js pour les comportements locaux. La maintenabilité à 6 mois est imbattable.

Pour les graphiques : **`Plotly`** (output HTML standalone) ou **`observable-plot`** via JS pour quelque chose de plus moderne. **`matplotlib` reste valide pour les rapports statiques** (notebooks d'analyse, exports PDF).

### Observabilité

**Logging** : `loguru`, pas le `logging` standard. API plus saine, configuration en une ligne, output JSON natif pour ingestion ultérieure.

**Métriques** : `prometheus-client` Python + Prometheus + Grafana. Standard, gratuit, parfait pour les métriques techniques (latence ingestion, taux d'erreur scraping, coût API LLM).

**Métriques métier** (calibration, AUC-PR, drift) : stockées dans Postgres et affichées dans le dashboard FastAPI. Pas dans Prometheus — granularité différente, audience différente.

**Tracing** : pas nécessaire au MVP. Si tu en veux : OpenTelemetry + Jaeger.

**Alerting** : webhook Discord ou Telegram via un script simple. Pas PagerDuty, pas Opsgenie. Tu es seul.

### Tests

**`pytest`** + **`pytest-asyncio`** + **`pytest-cov`**. Standard.

**`hypothesis`** pour les tests basés sur des propriétés — très utile pour les fonctions de feature engineering où l'invariant (« cette feature à H ne dépend que de données antérieures à H ») est plus expressif comme propriété que comme cas de test.

**`testcontainers-python`** pour faire tourner Postgres dans Docker pour les tests d'intégration. Beaucoup mieux que des mocks.

### Containerisation et déploiement

**Docker** + **docker-compose** pour le développement local et le déploiement initial.

Image Python : **`python:3.12-slim`** comme base, **pas Alpine** (problèmes connus avec `manylinux` wheels et performance numpy/torch).

Pour la prod : **VPS auto-hébergé** (cohérent avec D12 de la spec). Hébergeurs sérieux hors juridiction US : **OVHcloud (Beauharnois, Québec)**, **Hetzner (Allemagne)**, **Scaleway (France)**. Beauharnois te donne ping ~5ms et facture en CAD — souvent le bon choix pour un projet québécois.

Reverse proxy : **Caddy**, pas Nginx. Auto-TLS via Let's Encrypt en une ligne de config, syntaxe lisible, performance équivalente.

Process manager : **`systemd`** sur le VPS, pas supervisord ni PM2. Standard Linux, intégration logs/restarts impeccable.

### Outils de développement

**Cursor** ou **VS Code** — tu utilises déjà Cursor avec ton skill ecosystem, continue.

**`pre-commit`** avec hooks ruff, mypy, et un check anti-secrets. Non-négociable.

**`just`** comme command runner (alternative moderne à Make). Lisible, simple, multi-OS.

## Stack récapitulative

| Couche | Choix | Alternatives écartées |
|---|---|---|
| Langage | Python 3.12+ | — |
| Paquets | `uv` | Poetry, pip-tools |
| BD | Postgres 16 + Timescale + pgvector | Stack Elasticsearch+Pinecone+Redis |
| ORM | SQLAlchemy 2.0 core + Alembic | ORM full, Tortoise, SQLModel |
| Validation | Pydantic v2 | dataclasses, attrs, marshmallow |
| HTTP | httpx | requests |
| Async | asyncio + APScheduler | Celery, Airflow, Prefect (pour MVP) |
| Scraping | selectolax + tenacity | BeautifulSoup |
| Telegram | telethon | python-telegram-bot |
| Audio | yt-dlp + faster-whisper | openai-whisper |
| NLP | spaCy + sentence-transformers (BGE) | NLTK, gensim |
| LLM | SDK Anthropic + instructor | LangChain, LlamaIndex |
| ML | XGBoost + scikit-learn + lifelines | PyTorch, TabNet |
| Tracking ML | MLflow local | W&B, Neptune |
| API | FastAPI | Flask, Django |
| Frontend | Jinja2 + HTMX + Alpine | React, Vue, Streamlit |
| Charts | Plotly + matplotlib | D3, ggplot |
| Logging | loguru | logging stdlib |
| Métriques | Prometheus + Grafana | Datadog, ELK |
| Tests | pytest + hypothesis + testcontainers | unittest |
| Containers | Docker + compose | Podman |
| Hébergement | OVH Beauharnois | Neon (Postgres managé), Netlify (statique / edge), clouds généralistes |
| Proxy | Caddy | Nginx, Traefik |
| Process | systemd | supervisord, PM2 |
| Lint/format | ruff | black + isort + flake8 |
| Type check | mypy strict | pyright |

**Variante cloud documentée (README).** Neon pour Postgres (`DATABASE_URL`, TLS) ; Netlify pour une partie statique ou du serverless court si tu sépares le front. FastAPI + APScheduler au quotidien reste plus naturel sur une VM ou un PaaS avec process long‑vécu qu’en bundle Netlify « full stack ».

## Ce que je n'ajouterais surtout pas

Liste des tentations à résister :

- **Kafka / RabbitMQ** : ton volume ne le justifie pas, complexité opérationnelle énorme.
- **Kubernetes** : pour un solo dev sur 1-2 machines, c'est un piège à dette opérationnelle.
- **LangChain / LlamaIndex** : couches d'abstraction qui changent tous les 3 mois et ajoutent peu de valeur sur des appels LLM structurés.
- **Vector database dédiée** (Pinecone, Weaviate, Qdrant) : pgvector suffit largement à ton échelle et te coûte 0.
- **Spark / Dask** : pas de big data ici.
- **dbt** : utile dans une stack analytics-first, sur-engineering pour ton cas.
- **Service mesh / Istio** : sans commentaire.

## La question à se poser avant chaque ajout

Avant d'ajouter une dépendance ou un service, demande-toi : *« si je reviens sur ce projet dans 3 mois après une pause, est-ce que je vais devoir ré-apprendre cet outil ou est-ce qu'il sera transparent ? »* Tout ce qui demande de la ré-apprentissage est une dette à venir.

---
