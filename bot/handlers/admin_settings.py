"""Admin settings: what mechanics see (switches) and each mechanic's pay scheme (a short wizard)."""
import math

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot import actions, nav, wizard
from bot.api_client import ApiClient, ApiForbidden
from bot.callback_ids import decode_id, encode_id
from bot.formatting import format_number
from bot.states import PayStates

router = Router()

# short callback key, setting key, label
TOGGLES = [
    ("prices", "mechanic_sees_prices", "Цены и заработок"),
    ("name", "mechanic_sees_client_name", "Имя клиента"),
    ("phone", "mechanic_sees_client_phone", "Телефон клиента"),
    ("vin", "mechanic_sees_vin", "VIN / номер кузова"),
]
SCHEMES = [("percent", "Процент от работы"), ("per_hour", "Фикс за нормо-час"), ("full", "Вся стоимость"), ("none", "Не задана")]
FORBIDDEN = "Недостаточно прав"


def _num(value: float) -> str:
    return format_number(value) if float(value).is_integer() else f"{value:g}".replace(".", ",")


def pay_label(m: dict) -> str:
    scheme, value = m["pay_scheme"], m["pay_value"]
    if scheme == "percent":
        return f"{_num(value)}% от работы"
    if scheme == "per_hour":
        return f"{_num(value)} ₽ за н/ч"
    if scheme == "full":
        return "вся стоимость"
    return "схема не задана"


@nav.screen("settings")
async def render_settings(api: ApiClient, user: dict, args: dict) -> nav.Rendered:
    if user["role"] != "admin":
        raise ApiForbidden(FORBIDDEN)
    current = await api.get_settings()
    builder = InlineKeyboardBuilder()
    for short, key, label in TOGGLES:
        builder.button(text=f"{'✅' if current[key] else '⬜'} {label}", callback_data=f"{actions.SETTING}:{short}")
    builder.button(text="💰 Оплата механиков", callback_data=nav.go_data("pay"))
    builder.adjust(1)
    return "⚙️ Настройки\nЧто видят механики — нажмите, чтобы переключить.", builder.as_markup()


@router.callback_query(F.data.startswith(f"{actions.SETTING}:"))
async def toggle_setting(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if user["role"] != "admin":
        await callback.answer(FORBIDDEN)
        return
    if await nav.top_args(callback, state, "settings") is None:
        return
    key = {short: key for short, key, _ in TOGGLES}.get(callback.data.rsplit(":", 1)[1])
    if key is None:
        await callback.answer()
        return
    current = await api.get_settings()
    await api.update_settings(**{key: not current[key]})
    await nav.refresh(callback, state, api, user)


@nav.screen("pay")
async def render_pay(api: ApiClient, user: dict, args: dict) -> nav.Rendered:
    if user["role"] != "admin":
        raise ApiForbidden(FORBIDDEN)
    mechanics = await api.list_mechanic_pay()
    builder = InlineKeyboardBuilder()
    for m in mechanics:
        builder.button(text=f"{m['full_name']} · {pay_label(m)}", callback_data=f"{actions.PAY}:{encode_id(m['user_id'])}")
    builder.adjust(1)
    text = "💰 Оплата механиков\nВыберите механика, чтобы изменить схему." if mechanics else "💰 Оплата механиков\nМехаников нет."
    return text, builder.as_markup()


@wizard.step(PayStates.choosing_scheme)
async def scheme_prompt(state: FSMContext, api: ApiClient, user: dict):
    builder = InlineKeyboardBuilder()
    for scheme, label in SCHEMES:
        builder.button(text=label, callback_data=f"pay_scheme:{scheme}")
    builder.adjust(1)
    return f"Схема оплаты: {(await state.get_data())['pay_name']}", builder.as_markup()


@wizard.step(PayStates.waiting_for_value)
async def value_prompt(state: FSMContext, api: ApiClient, user: dict):
    if (await state.get_data())["pay_scheme"] == "percent":
        return "Введите процент от стоимости работы (например, 40):", None
    return "Введите ставку в рублях за нормо-час (например, 700):", None


@router.callback_query(F.data.startswith(f"{actions.PAY}:"))
async def start_pay(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if user["role"] != "admin":
        await callback.answer(FORBIDDEN)
        return
    if await nav.top_args(callback, state, "pay") is None:
        return
    user_id = decode_id(callback.data.rsplit(":", 1)[1])
    mechanic = next((m for m in await api.list_mechanic_pay() if str(m["user_id"]) == user_id), None)
    if mechanic is None:
        await callback.answer("Механик не найден")
        return
    await wizard.start(callback, state, api, user, "pay", PayStates.choosing_scheme,
                       pay_user_id=user_id, pay_name=mechanic["full_name"])


async def _save(event: nav.Event, state: FSMContext, api: ApiClient, user: dict, scheme: str | None, value: float | None):
    await api.set_mechanic_pay((await state.get_data())["pay_user_id"], scheme, value)
    await wizard.finish(state)
    await nav.refresh(event, state, api, user, notice="Сохранено")


@router.callback_query(PayStates.choosing_scheme, F.data.startswith("pay_scheme:"))
async def choose_scheme(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    scheme = callback.data.split(":", 1)[1]
    if scheme in ("percent", "per_hour"):
        await state.update_data(pay_scheme=scheme)
        await wizard.goto(callback, state, api, user, PayStates.waiting_for_value)
        return
    await _save(callback, state, api, user, None if scheme == "none" else scheme, None)


@router.message(PayStates.waiting_for_value)
async def receive_value(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    scheme = (await state.get_data())["pay_scheme"]
    try:
        value = float((message.text or "").strip().replace(",", "."))
    except ValueError:
        value = None
    if value is not None and not math.isfinite(value):
        value = None
    if scheme == "percent" and (value is None or not 0 < value <= 100):
        await wizard.reprompt(message, state, api, user, "Процент — число больше 0 и не больше 100, например 40.")
        return
    if scheme == "per_hour" and (value is None or value <= 0):
        await wizard.reprompt(message, state, api, user, "Ставка — число больше нуля, например 700.")
        return
    await _save(message, state, api, user, scheme, value)
