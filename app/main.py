from contextlib import asynccontextmanager
from pathlib import Path
import logging

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.keitaro import keitaro
from app.models import Campaign
from app.schemas import CampaignCreate, CampaignRead, CampaignUpdate, OfferUpdate

BASE_DIR = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await keitaro.open()
    yield
    await keitaro.close()


app = FastAPI(title="Adrobot · Campaign desk", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/api/health")
def health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "keitaro_configured": keitaro.configured,
        "statistics_available": keitaro.statistics_available is not False,
    }


@app.get("/api/campaigns", response_model=list[CampaignRead])
async def list_campaigns(db: Session = Depends(get_db), q: str | None = Query(default=None, max_length=100)):
    if keitaro.configured:
        remote_campaigns = await keitaro.list_campaigns()
        for remote in remote_campaigns:
            remote_id = remote.get("id") or remote.get("campaign_id")
            if not remote_id:
                continue
            streams = remote.get("streams") or await keitaro.campaign_streams(int(remote_id))
            offer_ids = list(dict.fromkeys(
                int(offer.get("offer_id") or offer.get("id"))
                for stream in streams
                for offer in stream.get("offers", [])
                if offer.get("offer_id") or offer.get("id")
            ))
            country = "--"
            for stream in streams:
                for filter_item in stream.get("filters") or []:
                    if filter_item.get("name") == "country":
                        raw_country = filter_item.get("payload", "--")
                        if isinstance(raw_country, list):
                            raw_country = raw_country[0] if raw_country else "--"
                        country = str(raw_country or "--")[:2].upper()
                        break
            record = db.scalar(select(Campaign).where(Campaign.keitaro_id == int(remote_id)))
            if record is None:
                record = Campaign(
                    name=remote.get("name", f"Кампания {remote_id}"),
                    country_code=country,
                    offer_id=offer_ids[0] if offer_ids else 1,
                    offers=offer_ids,
                    keitaro_id=int(remote_id),
                    status="paused" if remote.get("state") in ("disabled", "paused") else "active",
                )
                db.add(record)
            else:
                record.name = remote.get("name", record.name)
                record.country_code = country
                if offer_ids:
                    record.offer_id = offer_ids[0]
                    record.offers = offer_ids
                record.status = "paused" if remote.get("state") in ("disabled", "paused") else "active"
        db.flush()
        try:
            report = await keitaro.campaign_report()
            keitaro.statistics_available = True
            for row in report.get("rows", []):
                remote_id = row.get("campaign_id")
                if not remote_id:
                    continue
                record = db.scalar(select(Campaign).where(Campaign.keitaro_id == int(remote_id)))
                if record:
                    record.visits = int(float(row.get("clicks") or 0))
                    record.conversions = int(float(row.get("conversions") or 0))
                    record.revenue = float(row.get("revenue") or 0)
                    record.cost = float(row.get("cost") or 0)
        except HTTPException as exc:
            keitaro.statistics_available = False
            logger.warning("Keitaro report unavailable: %s", exc.detail)
        db.commit()
    statement = select(Campaign).order_by(Campaign.created_at.desc())
    if q:
        statement = statement.where(Campaign.name.ilike(f"%{q}%"))
    return db.scalars(statement).all()


@app.post("/api/campaigns", response_model=CampaignRead, status_code=status.HTTP_201_CREATED)
async def create_campaign(payload: CampaignCreate, db: Session = Depends(get_db)):
    record = payload.model_dump()
    remote_id = None
    if keitaro.configured:
        remote = await keitaro.create_campaign(record)
        remote_id = remote.get("id") or remote.get("campaign_id")
        if not remote_id:
            raise HTTPException(status_code=502, detail="Keitaro создал кампанию, но не вернул её ID")
    campaign = Campaign(**record, keitaro_id=remote_id, offers=[payload.offer_id])
    db.add(campaign)
    try:
        db.commit()
    except Exception:
        db.rollback()
        if remote_id:
            try:
                await keitaro.delete_campaign(remote_id)
            except HTTPException:
                logger.exception("Could not roll back remote campaign %s after database failure", remote_id)
        raise
    db.refresh(campaign)
    return campaign


@app.get("/api/campaigns/{campaign_id}", response_model=CampaignRead)
def get_campaign(campaign_id: int, db: Session = Depends(get_db)):
    campaign = db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Кампания не найдена")
    return campaign


@app.patch("/api/campaigns/{campaign_id}", response_model=CampaignRead)
async def update_campaign(campaign_id: int, payload: CampaignUpdate, db: Session = Depends(get_db)):
    campaign = db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Кампания не найдена")
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("status") not in (None, "active", "paused"):
        raise HTTPException(status_code=422, detail="Статус должен быть active или paused")
    if campaign.keitaro_id and changes.get("status"):
        await keitaro.update_campaign_state(campaign.keitaro_id, "active" if changes["status"] == "active" else "disabled")
    for key, value in changes.items():
        setattr(campaign, key, value)
    db.commit()
    db.refresh(campaign)
    return campaign


@app.put("/api/campaigns/{campaign_id}/offers", response_model=CampaignRead)
async def update_offers(campaign_id: int, payload: OfferUpdate, db: Session = Depends(get_db)):
    campaign = db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Кампания не найдена")
    offer_ids = list(dict.fromkeys(payload.offer_ids))
    if any(offer_id <= 0 for offer_id in offer_ids):
        raise HTTPException(status_code=422, detail="ID оффера должен быть положительным числом")
    if campaign.keitaro_id:
        await keitaro.update_campaign_offers(campaign.keitaro_id, offer_ids)
    campaign.offers = offer_ids
    campaign.offer_id = offer_ids[0]
    db.commit()
    db.refresh(campaign)
    return campaign


@app.delete("/api/campaigns/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(campaign_id: int, db: Session = Depends(get_db)):
    campaign = db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Кампания не найдена")
    if campaign.keitaro_id:
        await keitaro.delete_campaign(campaign.keitaro_id)
    db.delete(campaign)
    db.commit()


@app.get("/api/offers")
async def list_offers():
    if keitaro.configured:
        return await keitaro.resources("offers")
    return [
        {"id": 184, "name": "Nordic Balance · SE", "country": "SE", "payout": 42.0},
        {"id": 219, "name": "Velora Skin · DE", "country": "DE", "payout": 38.5},
        {"id": 307, "name": "Peak Sleep · GB", "country": "GB", "payout": 51.0},
        {"id": 412, "name": "Lumière Care · FR", "country": "FR", "payout": 44.0},
    ]


@app.get("/api/resources/{resource_name}")
async def list_resources(resource_name: str):
    paths = {"domains": "domains", "groups": "groups", "sources": "traffic_sources"}
    if resource_name not in paths:
        raise HTTPException(status_code=404, detail="Неизвестный справочник")
    if not keitaro.configured:
        return []
    return await keitaro.resources(paths[resource_name])
