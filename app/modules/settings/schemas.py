import uuid

from pydantic import BaseModel, ConfigDict, model_validator

from app.core.enums import PayScheme


class VisibilityOut(BaseModel):
    mechanic_sees_prices: bool
    mechanic_sees_client_name: bool
    mechanic_sees_client_phone: bool
    mechanic_sees_vin: bool


class VisibilityPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mechanic_sees_prices: bool | None = None
    mechanic_sees_client_name: bool | None = None
    mechanic_sees_client_phone: bool | None = None
    mechanic_sees_vin: bool | None = None


class MechanicPayOut(BaseModel):
    user_id: uuid.UUID
    full_name: str
    pay_scheme: PayScheme | None
    pay_value: float | None


class PayPatch(BaseModel):
    pay_scheme: PayScheme | None
    pay_value: float | None = None

    @model_validator(mode="after")
    def _check_value(self) -> "PayPatch":
        if self.pay_scheme in (None, PayScheme.FULL):
            self.pay_value = None
        elif self.pay_scheme == PayScheme.PERCENT and (self.pay_value is None or not 0 < self.pay_value <= 100):
            raise ValueError("Процент должен быть больше 0 и не больше 100")
        elif self.pay_scheme == PayScheme.PER_HOUR and (self.pay_value is None or self.pay_value <= 0):
            raise ValueError("Ставка за нормо-час должна быть больше нуля")
        return self
