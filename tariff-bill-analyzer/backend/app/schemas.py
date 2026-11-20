from datetime import date
from pydantic import BaseModel, EmailStr, Field


class RegisterIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    household_size: int = Field(3, ge=1, le=20)
    sanctioned_kw: float = Field(1.0, gt=0, le=50)
    tariff_id: str = "karnataka_sample_v1"
    consumer_no: str | None = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class ProfileIn(BaseModel):
    household_size: int | None = Field(None, ge=1, le=20)
    sanctioned_kw: float | None = Field(None, gt=0, le=50)
    tariff_id: str | None = None


class BillIn(BaseModel):
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    units: float = Field(ge=0, le=20000)
    amount_actual: float | None = Field(None, ge=0)
    days: int = Field(30, ge=20, le=40)


class ApplianceIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    watts: float = Field(gt=0, le=20000)
    hours_per_day: float = Field(ge=0, le=24)
    qty: int = Field(1, ge=1, le=50)
    duty: float = Field(1.0, gt=0, le=1)
    days_per_month: int = Field(30, ge=1, le=31)


class CalcIn(BaseModel):
    units: float = Field(ge=0)
    tariff_id: str = "karnataka_sample_v1"
    sanctioned_kw: float = 1.0
    entitled_units: int = 0


class ReadingIn(BaseModel):
    day: date
    units: float = Field(ge=0, le=500)


class WhatIfChange(BaseModel):
    name: str
    delta_hours_per_day: float


class WhatIfIn(BaseModel):
    changes: list[WhatIfChange]
    base_units: float | None = None


class SolarIn(BaseModel):
    roof_area_m2: float = Field(30, gt=0)
    sun_hours: float = Field(5.0, gt=1, le=8)
    cost_per_kw: float = Field(55000, gt=0)
    units_per_month: float | None = None
    mode: str = Field("net_metering", pattern="^(net_metering|net_billing)$")
    export_rate: float = Field(3.0, ge=0)
    battery_kwh: float = Field(0.0, ge=0, le=50)
    state_subsidy: float = Field(0.0, ge=0)
    loan_pct: float = Field(0.0, ge=0, le=1)
    loan_rate: float = Field(0.09, ge=0, le=0.4)
    loan_years: int = Field(5, ge=1, le=15)
    tariff_escalation: float = Field(0.03, ge=0, le=0.2)
    system_kw: float | None = Field(None, gt=0, le=50)


class TariffCompareIn(BaseModel):
    old_id: str
    new_id: str

class ForgotIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    new_password: str = Field(min_length=8, max_length=128)