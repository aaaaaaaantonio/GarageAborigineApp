import uuid
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.enums import PayScheme

MAX_PAY_VALUE = Decimal("99999999.99")  # Numeric(10, 2)


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
    pay_value: float | None = Field(default=None, allow_inf_nan=False)

    @model_validator(mode="after")
    def _check_value(self) -> "PayPatch":
        if self.pay_scheme in (None, PayScheme.FULL):
            self.pay_value = None
            return self
        if self.pay_value is None:
            raise ValueError("Укажите значение схемы оплаты")
        # Check what the DB column (Numeric(10, 2)) will actually store.
        kopecks = Decimal(str(self.pay_value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if kopecks > MAX_PAY_VALUE:
            raise ValueError("Значение слишком большое")
        if self.pay_scheme == PayScheme.PERCENT and not Decimal("0.01") <= kopecks <= Decimal(100):
            raise ValueError("Процент должен быть больше 0 и не больше 100")
        if self.pay_scheme == PayScheme.PER_HOUR and kopecks <= 0:
            raise ValueError("Ставка за нормо-час должна быть больше нуля")
        self.pay_value = float(kopecks)
        return self
