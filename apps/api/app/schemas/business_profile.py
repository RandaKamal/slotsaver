from datetime import datetime

from pydantic import BaseModel


class BusinessProfileSummary(BaseModel):
    """Row shown in the profile picker - enough to choose one, not edit it."""

    id: int
    slug: str
    name: str
    business_type: str
    active: bool

    model_config = {"from_attributes": True}


class BusinessProfileDetail(BaseModel):
    """Full profile config - what the settings page reads and writes."""

    id: int
    slug: str
    name: str
    business_type: str
    active: bool
    timezone: str
    location: str
    worker_label: str
    customer_label: str
    service_label: str
    working_days: list
    open_time: str
    close_time: str
    workers: list
    services: list
    booking_rules: dict
    recovery_rules: dict
    incentive_policy: dict
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BusinessProfileUpdate(BaseModel):
    """Every field optional - the settings page saves one section at a time."""

    name: str | None = None
    business_type: str | None = None
    timezone: str | None = None
    location: str | None = None
    worker_label: str | None = None
    customer_label: str | None = None
    service_label: str | None = None
    working_days: list | None = None
    open_time: str | None = None
    close_time: str | None = None
    workers: list | None = None
    services: list | None = None
    booking_rules: dict | None = None
    recovery_rules: dict | None = None
    incentive_policy: dict | None = None


class BusinessProfileCreate(BaseModel):
    slug: str
    name: str
    business_type: str
    timezone: str = "America/New_York"
    location: str = ""
    worker_label: str = "Provider"
    customer_label: str = "Customer"
    service_label: str = "Service"
    working_days: list = []
    open_time: str = "09:00"
    close_time: str = "17:00"
    workers: list = []
    services: list = []
    booking_rules: dict = {}
    recovery_rules: dict = {}
    incentive_policy: dict = {}
