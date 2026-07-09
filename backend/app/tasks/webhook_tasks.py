"""Webhook HTTP delivery + usage meter rollup + retention purge + pgvector backfill."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

import httpx
from sqlalchemy import select, text

from app.tasks.celery_app import celery_app


def _run(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            return asyncio.run(coro)
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


@celery_app.task(name="app.tasks.webhook_tasks.deliver_pending_webhooks")
def deliver_pending_webhooks(limit: int = 50) -> dict:
    return _run(_deliver_pending(limit))


async def _deliver_pending(limit: int) -> dict:
    from app.core.config import get_settings
    from app.db.session import AsyncSessionLocal
    from app.models.domain import WebhookDelivery, WebhookDeliveryStatus, WebhookEndpoint
    from app.services.enterprise.service import schedule_retry, sign_payload, webhook_signing_secret

    settings = get_settings()
    now = datetime.now(timezone.utc)
    sent = 0
    failed = 0
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(WebhookDelivery)
            .where(WebhookDelivery.status == WebhookDeliveryStatus.PENDING)
            .where(
                (WebhookDelivery.next_retry_at.is_(None))
                | (WebhookDelivery.next_retry_at <= now)
            )
            .order_by(WebhookDelivery.created_at.asc())
            .limit(limit)
        )
        deliveries = list(result.scalars().all())
        for d in deliveries:
            ep = await session.get(WebhookEndpoint, d.endpoint_id)
            if not ep or not ep.is_active or ep.deleted_at is not None:
                d.status = WebhookDeliveryStatus.FAILED
                d.response_body = "endpoint inactive"
                d.attempt_count = (d.attempt_count or 0) + 1
                failed += 1
                continue
            body = json.dumps(
                {"event": d.event_type, "payload": d.payload, "delivery_id": str(d.id)}
            ).encode()
            try:
                secret = webhook_signing_secret(ep)
                signature = sign_payload(secret, body)
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        ep.url,
                        content=body,
                        headers={
                            "Content-Type": "application/json",
                            "X-Veritas-Event": d.event_type,
                            "X-Veritas-Delivery": str(d.id),
                            "X-Veritas-Signature": f"sha256={signature}",
                        },
                    )
                d.http_status = resp.status_code
                d.response_body = (resp.text or "")[:2000]
                d.attempt_count = (d.attempt_count or 0) + 1
                if 200 <= resp.status_code < 300:
                    d.status = WebhookDeliveryStatus.SUCCESS
                    d.delivered_at = datetime.now(timezone.utc)
                    d.next_retry_at = None
                    sent += 1
                else:
                    schedule_retry(d)
                    if d.status == WebhookDeliveryStatus.FAILED:
                        failed += 1
            except Exception as exc:  # noqa: BLE001
                d.attempt_count = (d.attempt_count or 0) + 1
                d.response_body = str(exc)[:2000]
                schedule_retry(d)
                if d.status == WebhookDeliveryStatus.FAILED:
                    failed += 1
        await session.commit()
    return {
        "sent": sent,
        "failed": failed,
        "processed": len(deliveries),
        "max_attempts": settings.webhook_max_attempts,
    }


@celery_app.task(name="app.tasks.webhook_tasks.rollup_usage_meters")
def rollup_usage_meters() -> dict:
    return _run(_rollup_meters())


async def _rollup_meters() -> dict:
    from app.db.session import AsyncSessionLocal
    from app.models.domain import UsageEvent, UsageMeter

    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    async with AsyncSessionLocal() as session:
        events = (
            await session.execute(
                select(UsageEvent).where(
                    UsageEvent.created_at >= start,
                    UsageEvent.workspace_id.is_not(None),
                )
            )
        ).scalars().all()
        totals: dict[tuple, int] = {}
        for e in events:
            key = (e.workspace_id, e.event_type if e.event_type != "query" else "query")
            totals[key] = totals.get(key, 0) + (e.quantity or 1)
        updated = 0
        for (ws_id, meter_key), qty in totals.items():
            meter = (
                await session.execute(
                    select(UsageMeter).where(
                        UsageMeter.workspace_id == ws_id,
                        UsageMeter.meter_key == meter_key,
                        UsageMeter.period_start == start,
                    )
                )
            ).scalar_one_or_none()
            if meter:
                meter.quantity = qty
            else:
                session.add(
                    UsageMeter(
                        workspace_id=ws_id,
                        meter_key=meter_key,
                        period_start=start,
                        period_end=start + timedelta(days=1),
                        quantity=qty,
                    )
                )
            updated += 1
        await session.commit()
    return {"meters_updated": updated}


@celery_app.task(name="app.tasks.webhook_tasks.run_retention_purge_all")
def run_retention_purge_all() -> dict:
    return _run(_purge_all())


async def _purge_all() -> dict:
    from app.db.session import AsyncSessionLocal
    from app.models.domain import DataRetentionPolicy
    from app.services.compliance.service import apply_retention_purge

    async with AsyncSessionLocal() as session:
        ws_ids = (
            await session.execute(
                select(DataRetentionPolicy.workspace_id)
                .where(DataRetentionPolicy.is_active.is_(True))
                .distinct()
            )
        ).scalars().all()
        results = []
        for ws_id in ws_ids:
            results.append(await apply_retention_purge(session, ws_id))
        await session.commit()
    return {"workspaces": len(ws_ids), "results": results}


@celery_app.task(name="app.tasks.webhook_tasks.run_export_job")
def run_export_job_task(job_id: str) -> dict:
    return _run(_run_export(UUID(job_id)))


async def _run_export(job_id: UUID) -> dict:
    from app.db.session import AsyncSessionLocal
    from app.services.compliance.service import run_export_job

    async with AsyncSessionLocal() as session:
        job = await run_export_job(session, job_id)
        await session.commit()
        return {"job_id": str(job.id), "status": job.status.value}


@celery_app.task(name="app.tasks.webhook_tasks.backfill_pgvector")
def backfill_pgvector(limit: int = 500) -> dict:
    return _run(_backfill(limit))


async def _backfill(limit: int) -> dict:
    from app.db.session import AsyncSessionLocal
    from app.services.retrieval.pgvector import backfill_embedding_vecs

    async with AsyncSessionLocal() as session:
        n = await backfill_embedding_vecs(session, limit=limit)
        await session.commit()
    return {"backfilled": n}
