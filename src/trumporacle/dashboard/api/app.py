"""FastAPI application with APScheduler and Prometheus metrics."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from loguru import logger
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest
from sqlalchemy import text
from starlette.templating import Jinja2Templates

from trumporacle import __version__
from trumporacle.orchestration import jobs
from trumporacle.storage.db import async_session_scope

REQUESTS = Counter("trumporacle_http_requests_total", "HTTP requests", ["path"])

_templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))
_scheduler: AsyncIOScheduler | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start/stop background scheduler."""

    global _scheduler
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(jobs.job_ingest_truth_social, "interval", minutes=15, id="ingest")
    _scheduler.add_job(jobs.job_ingest_rss_ecosystem, "interval", minutes=15, id="ingest_rss")
    _scheduler.add_job(jobs.job_predict_windows, "interval", minutes=15, id="predict")
    _scheduler.add_job(jobs.job_materialize_outcomes, "interval", minutes=5, id="outcomes")
    _scheduler.start()
    logger.info("APScheduler started (15m ingest+rss+predict, 5m outcomes)")
    yield
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None


app = FastAPI(title="TRUMPORACLE", version=__version__, lifespan=lifespan)


@app.get("/health", response_class=PlainTextResponse)
async def health() -> str:
    REQUESTS.labels(path="/health").inc()
    return "ok"


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics() -> PlainTextResponse:
    REQUESTS.labels(path="/metrics").inc()
    data = generate_latest()
    return PlainTextResponse(content=data.decode("utf-8"), media_type=CONTENT_TYPE_LATEST)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    REQUESTS.labels(path="/").inc()
    return _templates.TemplateResponse(
        request,
        "index.html.j2",
        {"title": "TRUMPORACLE", "version": __version__},
    )


@app.get("/predictions", response_class=HTMLResponse)
async def predictions_page(request: Request) -> HTMLResponse:
    REQUESTS.labels(path="/predictions").inc()
    rows: list[dict[str, object]] = []
    async with async_session_scope() as session:
        result = await session.execute(
            text(
                """
                SELECT prediction_made_at, window_start, window_end, model_version,
                       c2_4_prob, c2_5_prob, c4_prob, feature_hash
                FROM predictions
                ORDER BY prediction_made_at DESC
                LIMIT 40
                """
            )
        )
        for m in result.mappings():
            rows.append(dict(m))
    return _templates.TemplateResponse(
        request,
        "predictions.html.j2",
        {"title": "Predictions", "version": __version__, "rows": rows},
    )
