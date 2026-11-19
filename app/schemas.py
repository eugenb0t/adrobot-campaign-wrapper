from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CampaignCreate(BaseModel):
    name: str = Field(min_length=3, max_length=180)
    country_code: str = Field(min_length=2, max_length=2)
    offer_id: int = Field(gt=0)
    domain_id: int | None = None
    group_id: int | None = None
    traffic_source_id: int | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Название не может быть пустым")
        if not value.lower().startswith("test_"):
            raise ValueError("Для тестового задания название должно начинаться с test_фамилия_")
        return value

    @field_validator("country_code")
    @classmethod
    def normalize_country(cls, value: str) -> str:
        value = value.strip().upper()
        if not value.isascii() or not value.isalpha():
            raise ValueError("Используйте двухбуквенный ISO-код страны")
        return value


class CampaignUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=180)
    status: str | None = None
    notes: str | None = None


class OfferUpdate(BaseModel):
    offer_ids: list[int] = Field(min_length=1)


class CampaignRead(BaseModel):
    id: int
    name: str
    country_code: str | None
    offer_id: int | None
    domain_id: int | None
    group_id: int | None
    traffic_source_id: int | None
    keitaro_id: int | None
    offers: list
    status: str
    visits: int
    conversions: int
    revenue: float
    cost: float
    profit: float
    roi: float
    notes: str | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ResourceRead(BaseModel):
    id: int
    name: str
    model_config = ConfigDict(extra="allow")
