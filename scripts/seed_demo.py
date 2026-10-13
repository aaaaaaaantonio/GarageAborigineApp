"""Демо-данные для ручного тестирования: сотрудники всех ролей, клиенты, авто,
каталог работ и заезды во всех статусах за последние полгода.

Всё создаётся через API от имени нужных сотрудников (работают FSM, пересчёт
сумм, аудит), затем даты переносятся в прошлое прямым SQL.

Запуск (стек поднят, в .env есть INTERNAL_API_KEY и DATABASE_URL):
    .venv/bin/python scripts/seed_demo.py

Повторный запуск отказывается работать, если демо-данные уже есть.
Никому ничего не отправляется в Telegram: у новых сотрудников нет telegram_id.
"""
import asyncio
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import asyncpg
import httpx

ROOT = Path(__file__).resolve().parent.parent
API = "http://localhost:8000"
MARKER_PHONE = "79165550101"  # телефон первого демо-клиента — признак, что сид уже был

NOW = datetime.now(timezone.utc)
RNG = random.Random(20261013)


def read_env() -> dict[str, str]:
    env = {}
    for line in (ROOT / ".env").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


ENV = read_env()
SERVICE_KEY = ENV["INTERNAL_API_KEY"]
DSN = ENV["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")

http = httpx.Client(base_url=API, timeout=60)


def api(method: str, path: str, user_id: str, **kw):
    headers = {"X-User-Id": str(user_id), "X-Service-Key": SERVICE_KEY}
    r = http.request(method, path, headers=headers, **kw)
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text}")
    return r.json() if r.content else None


# --- справочники -------------------------------------------------------------

VIN_CHARS = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"


def vin(prefix: str) -> str:
    return prefix + "".join(RNG.choice(VIN_CHARS) for _ in range(17 - len(prefix)))


STAFF = {
    # ключ: (роль, ФИО, телефон)
    "orlova": ("admin", "Марина Орлова", "+7 916 220-10-01"),
    "kuznetsov": ("master", "Сергей Кузнецов", "+7 916 220-10-11"),
    "belova": ("master", "Ольга Белова", "+7 916 220-10-12"),
    "morozov": ("mechanic", "Алексей Морозов", "+7 916 220-10-21"),  # электрика
    "sokolov": ("mechanic", "Дмитрий Соколов", "+7 916 220-10-22"),  # ходовая
    "garipov": ("mechanic", "Руслан Гарипов", "+7 916 220-10-23"),  # кузов
    "fedorov": ("mechanic", "Николай Фёдоров", "+7 916 220-10-24"),  # ТО
    "lebedev": ("mechanic", "Игорь Лебедев", "+7 916 220-10-25"),  # уволится
}
DISMISSED = {"lebedev": 60}  # уволен N дней назад

CATALOG = [
    ("Компьютерная диагностика", "diagnostics", 0.5),
    ("Диагностика подвески", "diagnostics", 0.5),
    ("Диагностика тормозной системы", "diagnostics", 0.4),
    ("Эндоскопия цилиндров", "diagnostics", 0.7),
    ("Замена масла ДВС и масляного фильтра", "maintenance", 0.6),
    ("Замена воздушного фильтра", "maintenance", 0.2),
    ("Замена салонного фильтра", "maintenance", 0.3),
    ("Замена свечей зажигания", "maintenance", 0.8),
    ("Замена ремня ГРМ с роликами", "maintenance", 3.5),
    ("Замена тормозной жидкости", "maintenance", 0.8),
    ("Замена антифриза", "maintenance", 1.0),
    ("Замена масла в АКПП/вариаторе", "maintenance", 1.0),
    ("Замена передних тормозных колодок", "chassis", 0.8),
    ("Замена тормозных дисков (ось)", "chassis", 1.2),
    ("Замена стоек стабилизатора (пара)", "chassis", 0.8),
    ("Замена переднего амортизатора", "chassis", 1.5),
    ("Замена шаровой опоры", "chassis", 1.0),
    ("Развал-схождение", "chassis", 1.0),
    ("Замена сайлентблоков рычага", "chassis", 2.0),
    ("Замена аккумулятора", "electrical", 0.3),
    ("Замена генератора", "electrical", 2.0),
    ("Ремонт электропроводки", "electrical", 1.5),
    ("Замена ламп фар", "electrical", 0.3),
    ("Рихтовка элемента кузова", "body", 3.0),
    ("Покраска элемента кузова", "body", 4.0),
    ("Полировка кузова", "body", 5.0),
    ("Антикоррозийная обработка", "body", 3.0),
    ("Сезонный шиномонтаж (4 колеса)", "other", 1.0),
]

# Клиенты. consent: paper | qr | legal (юрлицо, без согласия на ПДн).
CLIENTS = {
    "smirnov": ("Смирнов Андрей Петрович", "+7 916 555-01-01", "paper"),
    "kuzmina": ("Кузьмина Екатерина Сергеевна", "+7 925 555-01-02", "qr"),
    "petrov": ("Петров Михаил Олегович", "+7 903 555-01-03", "qr"),
    "volkova": ("Волкова Анна Дмитриевна", "+7 915 555-01-04", "paper"),
    "guseinov": ("Гусейнов Тимур Рашидович", "+7 926 555-01-05", "qr"),
    "novikova": ("Новикова Светлана Игоревна", "+7 977 555-01-06", "paper"),
    "zakharov": ("Захаров Павел Викторович", "+7 905 555-01-07", "qr"),
    "li": ("Ли Виктор Сергеевич", "+7 914 555-01-08", "paper"),
    "orlov": ("Орлов Денис Андреевич", "+7 999 555-01-09", "qr"),
    "tarasov": ("Тарасов Кирилл Андреевич", "+7 968 555-01-10", "qr"),
    "frolova": ("Фролова Мария Александровна", "+7 916 555-01-11", "paper"),
    "abramov": ("Абрамов Евгений Николаевич", "+7 985 555-01-12", "qr"),
    "yakovleva": ("Яковлева Ирина Валерьевна", "+7 917 555-01-13", "paper"),
    "logistic": ("ООО «Логистик-Транс»", "+7 495 555-02-01", "legal"),
    "safonov": ("ИП Сафонов Роман Игоревич", "+7 916 555-02-02", "legal"),
    "stroymontazh": ("ООО «СтройМонтаж»", "+7 495 555-02-03", "legal"),
}
LEGAL_DETAILS = {
    "logistic": {"inn": "7714123450", "kpp": "771401001", "ogrn": "1157746123456",
                 "contact_person": "Гришин Олег, начальник автоколонны", "contract": "Договор ТО-17/2024"},
    "safonov": {"inn": "502712345678", "ogrnip": "318502700012345",
                "contact_person": "Сафонов Роман", "note": "такси"},
    "stroymontazh": {"inn": "5003098765", "kpp": "500301001", "ogrn": "1185003012345",
                     "contact_person": "Карпова Наталья, бухгалтерия"},
}
FLEET_RATE = 2200  # ставка по договору для юрлиц
STD_RATE = 2500
BODY_RATE = 3000

# Авто: ключ: (владелец, VIN/кузов, госномер, марка, модель, модификация, год, цвет, владеет с)
VEHICLES = {
    "rio": ("smirnov", vin("Z94CB41AB"), "О245КР777", "Kia", "Rio", "1.6 AT", 2017, "белый", "2017-06-10"),
    "largus": ("smirnov", vin("XTAKS0Y5L"), "Т318ХА750", "Lada", "Largus", "1.6 MT универсал", 2019, "серый", "2019-09-02"),
    "solaris": ("kuzmina", vin("Z94K241CB"), "Е771МН799", "Hyundai", "Solaris", "1.6 AT", 2019, "красный", "2020-03-15"),
    "camry": ("petrov", vin("XW7BF4FK"), "В505ОР197", "Toyota", "Camry", "2.5 AT", 2021, "чёрный", "2021-11-20"),
    "logan": ("volkova", vin("X7L4SRAV"), "Н640ТЕ190", "Renault", "Logan", "1.6 MT", 2014, "бежевый", "2014-08-01"),
    "x5": ("guseinov", vin("WBAKS4106"), "М777КМ777", "BMW", "X5", "xDrive30d F15", 2015, "чёрный", "2018-05-12"),
    "haval": ("novikova", vin("XZGFF06A"), "А902ВУ799", "Haval", "Jolion", "1.5T DCT", 2023, "синий", "2023-07-28"),
    "prado": ("zakharov", vin("JTEBU3FJ"), "К150АС77", "Toyota", "Land Cruiser Prado", "4.0 AT 150", 2012, "серебристый", "2015-02-14"),
    "prius": ("li", "NHW20-3187452", "Р327ОО125", "Toyota", "Prius", "1.5 гибрид, правый руль", 2008, "зелёный", "2016-10-05"),
    "tiggo": ("tarasov", vin("LVVDB21B"), "С088МВ750", "Chery", "Tiggo 7 Pro", "1.5T CVT", 2022, "серый", "2022-12-01"),
    "qashqai": ("frolova", vin("SJNFAAJ11"), "У414ЕК777", "Nissan", "Qashqai", "2.0 CVT", 2015, "белый", "2015-04-18"),
    "outlander": ("abramov", vin("Z8TXTGF3W"), "Х696НТ50", "Mitsubishi", "Outlander", "2.4 CVT", 2014, "коричневый", "2014-09-09"),
    "mercedes": ("yakovleva", vin("WDD2130421"), "Е213АА199", "Mercedes-Benz", "E 200", "W213", 2017, "белый", "2019-01-25"),
    "transit": ("logistic", vin("WF0XXXTTG"), "Н112КС799", "Ford", "Transit", "2.2 TDCi фургон", 2019, "белый", "2019-04-01"),
    "gazelle1": ("logistic", vin("X96A21R32"), "В431ХО750", "ГАЗ", "ГАЗель Next", "A21R32 2.7", 2020, "белый", "2020-02-20"),
    "gazelle2": ("logistic", vin("X96A21R33"), "В432ХО750", "ГАЗ", "ГАЗель Next", "A21R32 2.7", 2020, "белый", "2020-02-20"),
    "vesta": ("safonov", vin("XTAGFL110"), "Т776РК799", "Lada", "Vesta", "1.6 MT", 2020, "белый", "2020-06-30"),
    "hilux": ("stroymontazh", vin("AHTKB8CD"), "М090СТ190", "Toyota", "Hilux", "2.8D AT", 2018, "серый", "2018-08-08"),
}
# Перепродажа: Logan ушёл от Волковой к Орлову 70 дней назад, старую историю новый владелец не видит.
RESALE = ("logan", "orlov", 70, False)


def P(name, art, price, qty=1, avail="in_stock"):
    return {"name": name, "article_number": art, "unit_price": price, "quantity": qty,
            "availability_status": avail}


def W(work, mech=None, status="ready", *, extra=False, approved=True, wait=False, parts=(),
      cat=None, hours=None, comment=None):
    """Работа: work — название из каталога, либо свободный текст (тогда нужны cat и hours)."""
    return dict(work=work, mech=mech, status=status, extra=extra, approved=approved,
                wait=wait, parts=list(parts), cat=cat, hours=hours, comment=comment)


OIL = P("Масло моторное 5W-40, 4 л", "SHELL-550051529", 3900)
OIL_FILTER = P("Фильтр масляный", "MANN W 811/80", 690)
AIR_FILTER = P("Фильтр воздушный", "MANN C 26 017", 980)
CABIN_FILTER = P("Фильтр салонный угольный", "MANN CUK 2939", 1250)
BRAKE_FLUID = P("Тормозная жидкость DOT 4, 1 л", "ATE 03.9901-6402.2", 890)

# Заезды в хронологическом порядке. master "p" и mechanic "v" — уже существующие
# в БД тестовые сотрудники (под ними пользователь заходит через dev-вход).
# days — сколько дней назад принят; hours — сколько длился (для истории);
# status — целевой статус; via_wait — по дороге ждали запчасти;
# cancel_from — с какого статуса отменён.
VISITS = [
    dict(v="logan", c="volkova", m="kuznetsov", days=175, hours=5, km=98000, status="issued",
         complaint="Плановое ТО",
         works=[W("Замена масла ДВС и масляного фильтра", "fedorov", parts=[OIL, OIL_FILTER]),
                W("Замена воздушного фильтра", "fedorov", parts=[AIR_FILTER])]),
    dict(v="prado", c="zakharov", m="belova", days=168, hours=30, km=231000, status="issued", doc=True,
         complaint="Стук спереди справа на неровностях",
         works=[W("Диагностика подвески", "sokolov"),
                W("Замена стоек стабилизатора (пара)", "sokolov",
                  parts=[P("Стойка стабилизатора передняя", "CTR CLT-49", 1850, 2)]),
                W("Замена шаровой опоры", "sokolov", extra=True,
                  parts=[P("Опора шаровая нижняя", "555 SB-3882", 3400)],
                  comment="Люфт выявлен при диагностике, согласовано по телефону")]),
    dict(v="transit", c="logistic", m="kuznetsov", days=160, hours=8, km=142000, status="issued",
         complaint="ТО по договору, скрип тормозов",
         works=[W("Замена масла ДВС и масляного фильтра", "lebedev",
                  parts=[P("Масло моторное 5W-30 Ford, 7 л", "FORD-15D633", 6900), OIL_FILTER]),
                W("Замена передних тормозных колодок", "lebedev",
                  parts=[P("Колодки тормозные передние", "TRW GDB1724", 4200)])]),
    dict(v="rio", c="smirnov", m="p", days=152, hours=6, km=87000, status="issued",
         complaint="Вибрация руля при торможении",
         works=[W("Диагностика тормозной системы", "sokolov"),
                W("Замена тормозных дисков (ось)", "sokolov",
                  parts=[P("Диск тормозной передний", "BREMBO 09.B312.10", 3600, 2)]),
                W("Замена передних тормозных колодок", "sokolov",
                  parts=[P("Колодки тормозные передние", "HI-Q SP1240", 2300)])]),
    dict(v="x5", c="guseinov", m="kuznetsov", days=145, hours=96, km=156000, status="issued", via_wait=True, doc=True,
         complaint="Горит Check Engine, троит на холодную",
         works=[W("Компьютерная диагностика", "morozov"),
                W("Замена свечей накаливания", "morozov", cat="electrical", hours=1.5,
                  parts=[P("Свеча накаливания", "BOSCH 0 250 403 009", 1650, 6)]),
                W("Замена блока управления свечами накаливания", "morozov", cat="electrical", hours=0.8,
                  extra=True, wait=True,
                  parts=[P("Блок управления свечами накаливания", "BERU GSE102", 14900, 1, "ordered")])]),
    dict(v="gazelle1", c="logistic", m="belova", days=138, hours=10, km=210000, status="issued",
         complaint="Уводит вправо, неравномерный износ шин",
         works=[W("Замена сайлентблоков рычага", "lebedev",
                  parts=[P("Сайлентблок рычага", "ГАЗ А21R22-2904040", 780, 4)]),
                W("Развал-схождение", "lebedev")]),
    dict(v="outlander", c="abramov", m="p", days=130, hours=5, km=187400, status="issued",
         complaint="Плановая замена жидкостей",
         works=[W("Замена антифриза", "fedorov", parts=[P("Антифриз Mitsubishi Super Long Life, 5 л", "MZ320292", 4100)]),
                W("Замена масла в АКПП/вариаторе", "fedorov", parts=[P("Масло CVTF J4, 4 л", "MZ320185", 7600)])]),
    dict(v="logan", c="volkova", m="kuznetsov", days=121, hours=26, km=104500, status="cancelled",
         cancel_from="approval", reason="Клиент решил продать автомобиль, от ремонта отказался",
         complaint="Стук в подвеске, течь амортизатора",
         works=[W("Диагностика подвески", "sokolov"),
                W("Замена переднего амортизатора", "sokolov", status="not_ready", approved=False,
                  parts=[P("Амортизатор передний", "KYB 333747", 5400, 2, "pending")])]),
    dict(v="camry", c="petrov", m="v_master", days=112, hours=4, km=45000, status="issued",
         complaint="ТО-45",
         works=[W("Замена масла ДВС и масляного фильтра", "v", parts=[P("Масло Toyota 0W-20, 5 л", "08880-83264", 5200), OIL_FILTER]),
                W("Замена салонного фильтра", "v", parts=[CABIN_FILTER]),
                W("Замена воздушного фильтра", "v", parts=[AIR_FILTER]),
                W("Замена тормозной жидкости", "v", parts=[BRAKE_FLUID])]),
    dict(v="vesta", c="safonov", m="belova", days=104, hours=72, km=168000, status="issued", via_wait=True,
         complaint="Пробуксовывает сцепление",
         works=[W("Замена комплекта сцепления", "sokolov", cat="chassis", hours=4.0, wait=True,
                  parts=[P("Комплект сцепления", "VALEO 826861", 9800, 1, "ordered")])]),
    dict(v="mercedes", c="yakovleva", m="kuznetsov", days=96, hours=50, km=98000, status="issued", doc=True,
         complaint="Вмятина и царапины на заднем бампере после парковки",
         works=[W("Рихтовка элемента кузова", "garipov", comment="задний бампер"),
                W("Покраска элемента кузова", "garipov", comment="задний бампер",
                  parts=[P("Краска + лак, подбор по коду 149", "ЛКМ-149", 6500)]),
                W("Полировка кузова", "garipov", extra=True)]),
    dict(v="prius", c="li", m="belova", days=88, hours=30, km=263000, status="issued",
         complaint="Горит красный треугольник, ошибка гибридной системы",
         works=[W("Компьютерная диагностика", "morozov"),
                W("Восстановление высоковольтной батареи", "morozov", cat="electrical", hours=6.0,
                  parts=[P("Модуль ВВБ (восстановленный)", "G9280-47070-R", 2100, 4)])]),
    dict(v="hilux", c="stroymontazh", m="belova", days=80, hours=6, km=120000, status="issued",
         complaint="ТО-120",
         works=[W("Замена масла ДВС и масляного фильтра", "lebedev",
                  parts=[P("Масло Toyota 5W-30, 7 л", "08880-83388", 7400), OIL_FILTER]),
                W("Замена салонного фильтра", "lebedev", parts=[CABIN_FILTER]),
                W("Замена передних тормозных колодок", "lebedev",
                  parts=[P("Колодки тормозные передние", "TOYOTA 04465-0K290", 7900)])]),
    dict(v="qashqai", c="frolova", m="kuznetsov", days=72, hours=3, km=132000, status="issued",
         complaint="Не заводится утром, медленно крутит стартер",
         works=[W("Компьютерная диагностика", "morozov", comment="Генератор в норме, АКБ 2015 г."),
                W("Замена аккумулятора", "morozov", parts=[P("Аккумулятор 70 А·ч", "VARTA E39", 9900)])]),
    dict(v="logan", c="orlov", m="kuznetsov", days=65, hours=8, km=108000, status="issued", doc=True,
         complaint="Купил машину, нужно полное ТО и ГРМ",
         works=[W("Замена ремня ГРМ с роликами", "fedorov",
                  parts=[P("Комплект ГРМ", "GATES K015603XS", 6400), P("Помпа", "SKF VKPC 86416", 2900)]),
                W("Замена масла ДВС и масляного фильтра", "fedorov", parts=[OIL, OIL_FILTER]),
                W("Замена свечей зажигания", "fedorov", parts=[P("Свеча зажигания", "NGK BKR6E", 420, 4)])]),
    dict(v="haval", c="novikova", m="v_master", days=58, hours=3, km=15000, status="issued",
         complaint="ТО-15",
         works=[W("Замена масла ДВС и масляного фильтра", "v",
                  parts=[P("Масло 5W-30, 5 л", "HAVAL-5W30", 4500), P("Фильтр масляный", "1017100XEG01", 850)]),
                W("Замена салонного фильтра", "v", parts=[P("Фильтр салонный", "8104400XGW02A", 1100)])]),
    dict(v="solaris", c="kuzmina", m="p", days=50, hours=2, km=74000, status="cancelled",
         cancel_from="received", reason="Клиентка не дождалась очереди, забрала машину",
         complaint="Плановое ТО", works=[]),
    dict(v="gazelle2", c="logistic", m="belova", days=45, hours=9, km=189000, status="issued",
         complaint="Скрежет при торможении",
         works=[W("Замена тормозных дисков (ось)", "sokolov",
                  parts=[P("Диск тормозной передний", "ГАЗ A21R23-3501070", 3100, 2)]),
                W("Замена передних тормозных колодок", "v",
                  parts=[P("Колодки тормозные передние", "ГАЗ A21R23-3501800", 1900)]),
                W("Замена тормозной жидкости", "v", parts=[BRAKE_FLUID])]),
    dict(v="largus", c="smirnov", m="p", days=38, hours=2, km=143000, status="issued",
         complaint="Переобуть на зимнюю резину",
         works=[W("Сезонный шиномонтаж (4 колеса)", "v"), W("Развал-схождение", "v")]),
    dict(v="tiggo", c="tarasov", m="belova", days=30, hours=5, km=32000, status="issued",
         complaint="Не горит ближний свет справа",
         works=[W("Замена ламп фар", "morozov", parts=[P("Лампа H7", "PHILIPS 12972PRC1", 650)]),
                W("Ремонт электропроводки", "morozov", extra=True, comment="Окислен разъём фары")]),
    dict(v="outlander", c="abramov", m="kuznetsov", days=24, hours=6, km=64200, status="issued",
         mileage_confirmed=True,
         complaint="Стук спереди. Панель приборов меняли по гарантии — пробег на ней 64 тыс., реальный ~205 тыс.",
         works=[W("Замена переднего амортизатора", "sokolov",
                  parts=[P("Амортизатор передний", "KYB 339358", 6200, 2)])]),
    dict(v="vesta", c="safonov", m="belova", days=18, hours=120, km=189000, status="cancelled",
         cancel_from="waiting_parts", reason="Поставщик отменил заказ генератора, клиент забрал авто",
         complaint="Горит лампа зарядки АКБ",
         works=[W("Компьютерная диагностика", "morozov"),
                W("Замена генератора", "morozov", status="waiting_parts",
                  parts=[P("Генератор 115 А", "LADA 21900-3701010", 13500, 1, "ordered")])]),
    # --- активные --------------------------------------------------------------
    dict(v="prius", c="li", m="belova", days=6, km=271000, status="waiting_parts",
         complaint="Гул спереди слева, усиливается в повороте",
         works=[W("Компьютерная диагностика", "morozov"),
                W("Замена ступичного подшипника", "sokolov", cat="chassis", hours=1.8, status="waiting_parts",
                  parts=[P("Подшипник ступицы передний", "TOYOTA 90369-T0003", 5200, 1, "pending")],
                  comment="Заказ из Японии, ориентир 10 дней")]),
    dict(v="largus", c="smirnov", m="p", days=5, km=151000, status="waiting_parts",
         complaint="Бьёт педаль тормоза",
         works=[W("Замена передних тормозных колодок", "v", parts=[P("Колодки тормозные передние", "TRW GDB3332", 2500)]),
                W("Замена тормозных дисков (ось)", "v", status="waiting_parts",
                  parts=[P("Диск тормозной передний", "TRW DF4276", 3300, 2, "ordered")])]),
    dict(v="gazelle1", c="logistic", m="kuznetsov", days=4, km=236000, status="waiting_parts",
         complaint="Не заряжается АКБ, мигает приборка",
         works=[W("Ремонт электропроводки", "morozov"),
                W("Замена генератора", "morozov", status="waiting_parts",
                  parts=[P("Генератор 120 А", "ГАЗ 5432.3771", 16800, 1, "ordered")])]),
    dict(v="hilux", c="stroymontazh", m="belova", days=3, km=138000, status="in_progress",
         complaint="ТО-140, стук в передней подвеске",
         works=[W("Замена масла ДВС и масляного фильтра", "fedorov",
                  parts=[P("Масло Toyota 5W-30, 7 л", "08880-83388", 7400), OIL_FILTER]),
                W("Замена сайлентблоков рычага", "v", status="in_progress",
                  parts=[P("Сайлентблок рычага", "TOYOTA 48655-0K040", 2600, 4)]),
                W("Развал-схождение", "sokolov", status="not_ready")]),
    dict(v="x5", c="guseinov", m="kuznetsov", days=2, km=171000, status="approval",
         complaint="ТО + свист ремня на холодную",
         works=[W("Замена масла ДВС и масляного фильтра", "fedorov", status="not_ready",
                  parts=[P("Масло BMW LL-04 5W-30, 7 л", "83212365946", 9800), P("Фильтр масляный", "MANN HU 721/5 X", 1300)]),
                W("Замена приводного ремня и натяжителя", "v", cat="maintenance", hours=1.2, status="not_ready",
                  extra=True, approved=False,
                  parts=[P("Ремень поликлиновой", "CONTI 6PK1873", 2700), P("Натяжитель ремня", "INA 534 0335 10", 8900, 1, "pending")]),
                W("Замена тормозной жидкости", None, status="not_ready", approved=False, parts=[BRAKE_FLUID])]),
    dict(v="qashqai", c="frolova", m="kuznetsov", days=2, km=139500, status="in_progress",
         complaint="Помято переднее левое крыло",
         works=[W("Рихтовка элемента кузова", "garipov", comment="переднее левое крыло"),
                W("Покраска элемента кузова", "garipov", status="in_progress", comment="переднее левое крыло",
                  parts=[P("Краска + лак, код QAB", "ЛКМ-QAB", 5800)]),
                W("Антикоррозийная обработка", "garipov", status="not_ready", extra=True,
                  comment="Ржавчина на арке, клиент согласился")]),
    dict(v="camry", c="petrov", m="p", days=1, km=61000, status="in_progress",
         complaint="ТО-60, заменить щётки",
         works=[W("Замена масла ДВС и масляного фильтра", "v", status="in_progress",
                  parts=[P("Масло Toyota 0W-20, 5 л", "08880-83264", 5200), OIL_FILTER]),
                W("Замена салонного фильтра", "v", parts=[CABIN_FILTER]),
                W("Замена щёток стеклоочистителя", None, cat="other", hours=0.2, status="not_ready",
                  parts=[P("Щётки стеклоочистителя, комплект", "BOSCH 3 397 014 213", 2900)])]),
    dict(v="prado", c="zakharov", m="kuznetsov", days=1, km=258000, status="diagnostics",
         complaint="Пинки при переключении АКПП, масляное пятно под двигателем",
         works=[W("Компьютерная диагностика", "morozov", status="in_progress"),
                W("Поиск течи масла", "fedorov", cat="diagnostics", hours=0.8, status="not_ready")]),
    dict(v="rio", c="smirnov", m="p", days=1, km=101000, status="approval",
         complaint="Стук спереди на кочках",
         works=[W("Диагностика подвески", "sokolov", comment="Течь обоих передних амортизаторов, люфт стоек"),
                W("Замена переднего амортизатора", "sokolov", status="not_ready", approved=False,
                  parts=[P("Амортизатор передний", "KYB 339240", 5100, 2, "in_stock")]),
                W("Замена стоек стабилизатора (пара)", "v", status="not_ready", approved=False,
                  parts=[P("Стойка стабилизатора", "CTR CLKK-27", 1200, 2)])]),
    dict(v="tiggo", c="tarasov", m="belova", days=1, km=41000, status="ready", doc=True,
         complaint="ТО-40, увело руль после ямы",
         works=[W("Замена масла ДВС и масляного фильтра", "fedorov",
                  parts=[P("Масло 5W-30, 4.5 л", "CHERY-5W30", 3900), P("Фильтр масляный", "F01-1012010", 750)]),
                W("Развал-схождение", "sokolov")]),
    dict(v="logan", c="orlov", m="kuznetsov", days=0.8, km=121000, status="in_progress",
         complaint="Щёлкает и не крутит стартер",
         works=[W("Замена аккумулятора", "morozov", parts=[P("Аккумулятор 60 А·ч", "TYUMEN 6CT-60", 6900)]),
                W("Замена втягивающего реле стартера", "morozov", cat="electrical", hours=1.0,
                  status="in_progress", extra=True, parts=[P("Реле втягивающее", "CARGO 131806", 2400)])]),
    dict(v="mercedes", c="yakovleva", m="p", days=0.5, km=112000, status="diagnostics",
         complaint="Стук в подвеске слева",
         works=[W("Диагностика подвески", "v", status="in_progress")]),
    dict(v="haval", c="novikova", m="p", days=0.3, km=22500, status="ready",
         complaint="Переобуть на зимнюю резину",
         works=[W("Сезонный шиномонтаж (4 колеса)", "v")]),
    dict(v="transit", c="logistic", m="belova", days=0.2, km=171000, status="received",
         complaint="Плановое ТО по договору", works=[]),
    dict(v="solaris", c="kuzmina", m="p", days=0.1, km=81000, status="received",
         complaint="Скрип при торможении, вибрация руля", works=[]),
]

FLOW = ["received", "diagnostics", "approval", "in_progress", "ready", "issued"]
ITEM_STEPS = {
    "not_ready": [],
    "in_progress": ["in_progress"],
    "waiting_parts": ["in_progress", "waiting_parts"],
    "ready": ["in_progress", "ready"],
}


def visit_path(spec) -> list[str]:
    target = spec["status"]
    stop = spec.get("cancel_from", target)
    flow = FLOW[:]
    if spec.get("via_wait") or stop == "waiting_parts":
        i = flow.index("in_progress")
        flow[i + 1:i + 1] = ["waiting_parts", "in_progress"]
    if stop == "waiting_parts":
        path = flow[1:flow.index("waiting_parts") + 1]
    else:
        path = flow[1:flow.index(stop) + 1]
    if target == "cancelled":
        path.append("cancelled")
    return path


def visit_start(days: float) -> datetime:
    t = NOW - timedelta(days=days)
    if days >= 1:  # исторические заезды — утром в рабочее время (МСК = UTC+3)
        t = t.replace(hour=RNG.randint(6, 9), minute=RNG.choice([0, 10, 20, 30, 40, 50]), second=0, microsecond=0)
    return t


async def main() -> None:
    db = await asyncpg.connect(DSN)
    if await db.fetchval("select 1 from clients where phone_normalized = $1", MARKER_PHONE):
        print("Демо-данные уже загружены — выходим.")
        return

    admin = await db.fetchval("select id from users where role='ADMIN' and deleted_at is null order by full_name limit 1")
    if admin is None:
        raise SystemExit("Нет ни одного администратора в БД")

    staff: dict[str, str] = {}
    for key, (role, name, phone) in STAFF.items():
        staff[key] = api("POST", "/users", admin, json={"role": role, "full_name": name, "phone": phone})["id"]

    # Существующие тестовые сотрудники (под ними пользователь заходит в веб).
    for key, role in (("p", "MASTER"), ("v", "MECHANIC")):
        uid = await db.fetchval(
            "select id from users where role=$1 and deleted_at is null and not (id = any($2::uuid[])) "
            "order by full_name limit 1", role, list(staff.values()))
        staff[key] = str(uid) if uid else staff["belova" if key == "p" else "fedorov"]
    staff["v_master"] = staff["p"]

    catalog = {}
    for name, cat, hours in CATALOG:
        catalog[name] = (api("POST", "/catalog", staff["kuznetsov"],
                             json={"name": name, "category": cat, "default_norm_hours": hours})["id"], cat, hours)

    clients = {}
    for key, (name, phone, how) in CLIENTS.items():
        if how == "legal":
            clients[key] = api("POST", "/clients", staff["kuznetsov"], json={
                "full_name": name, "phone": phone, "client_type": "legal", "legal_details": LEGAL_DETAILS[key]})["id"]
        elif how == "paper":
            clients[key] = api("POST", "/consent/paper", staff["belova"], json={
                "full_name": name, "phone": phone, "verification_ref": f"Бланк №{RNG.randint(100, 999)}"})["client_id"]
        else:
            token = api("POST", "/consent/draft", staff["kuznetsov"])["token"]
            r = http.post("/consent/confirm", params={"token": token}, json={"full_name": name, "phone": phone})
            r.raise_for_status()
            clients[key] = r.json()["client_id"]

    vehicles = {}
    for key, (owner, vin_, plate, make, model, mod, year, color, since) in VEHICLES.items():
        vid = api("POST", "/vehicles", staff["kuznetsov"], json={
            "vin": vin_, "plate_number": plate, "make": make, "model": model,
            "modification": mod, "year": year, "color": color})["id"]
        api("POST", f"/vehicles/{vid}/owners", staff["kuznetsov"],
            json={"client_id": clients[owner], "date_from": since})
        vehicles[key] = vid

    resale_vehicle, new_owner, resale_days, show_history = RESALE
    resale_date = (NOW - timedelta(days=resale_days)).date()
    api("POST", f"/vehicles/{vehicles[resale_vehicle]}/owners", staff["kuznetsov"], json={
        "client_id": clients[new_owner], "date_from": resale_date.isoformat(),
        "show_history_before_ownership": show_history})

    created = []  # (visit_id, start, end, [work_item_ids])
    for spec in VISITS:
        master = staff[spec["m"]]
        client_key = spec["c"]
        visit = api("POST", "/visits", master, json={
            "client_id": clients[client_key], "vehicle_id": vehicles[spec["v"]],
            "assigned_master_id": master, "mileage_at_intake": spec["km"],
            "mileage_manually_confirmed": spec.get("mileage_confirmed", False),
            "complaint_text": spec["complaint"]})
        vid = visit["id"]

        items = []
        for w in spec["works"]:
            if w["work"] in catalog:
                cat_id, cat, hours = catalog[w["work"]]
            else:
                cat_id, cat, hours = None, w["cat"], w["hours"]
            rate = FLEET_RATE if CLIENTS[client_key][2] == "legal" else BODY_RATE if cat == "body" else STD_RATE
            body = {"category": cat, "norm_hours": hours, "hourly_rate": rate,
                    "assigned_mechanic_id": staff[w["mech"]] if w["mech"] else None,
                    "is_extra_work": w["extra"], "comment": w["comment"]}
            if cat_id:
                body["catalog_item_id"] = cat_id
            else:
                body["free_text_name"] = w["work"]
            item = api("POST", f"/visits/{vid}/work-items", master, json=body)
            for part in w["parts"]:
                api("POST", f"/visits/{vid}/part-items", master, json={"work_item_id": item["id"], **part})
            if w["approved"]:
                api("POST", f"/visits/{vid}/work-items/{item['id']}/approve", master)
            items.append((item["id"], w))

        path = visit_path(spec)
        # Работы двигаются, когда заезд дошёл до диагностики (для ранних стадий)
        # или впервые ушёл в работу; к «Готов» все работы уже готовы.
        work_point = "in_progress" if "in_progress" in path else "diagnostics"
        for status in path:
            reason = spec.get("reason") if status == "cancelled" else None
            api("PATCH", f"/visits/{vid}/status", master, json={"new_status": status, "reason": reason})
            if status == work_point:
                work_point = None
                for item_id, w in items:
                    actor = staff[w["mech"]] if w["mech"] else master
                    steps = ITEM_STEPS[w["status"]]
                    if w["wait"] and w["status"] == "ready":
                        steps = ["in_progress", "waiting_parts", "ready"]
                    for st in steps:
                        api("PATCH", f"/visits/{vid}/work-items/{item_id}/status", actor, json={"new_status": st})

        if spec.get("doc"):
            api("POST", f"/visits/{vid}/document", master)

        start = visit_start(spec["days"])
        if "hours" in spec:
            end = start + timedelta(hours=spec["hours"])
        else:
            end = start + (NOW - start) * 0.85
        created.append((vid, start, end, [i for i, _ in items]))
        print(f"  {spec['v']:<10} {spec['status']:<14} {start:%Y-%m-%d}")

    # --- перенос дат в прошлое ------------------------------------------------
    async with db.transaction():
        for vid, start, end, item_ids in created:
            await db.execute("update visits set created_at=$2 where id=$1", vid, start)
            logs = await db.fetch("select id from visit_status_log where visit_id=$1 order by changed_at", vid)
            for n, row in enumerate(logs, 1):
                await db.execute("update visit_status_log set changed_at=$2 where id=$1",
                                 row["id"], start + (end - start) * n / len(logs))
            await db.execute(
                "update visit_work_items set created_at=$2, "
                "approved_at = case when approved_at is null then null else $3::timestamptz end "
                "where visit_id=$1", vid, start + (end - start) * 0.05, start + (end - start) * 0.15)
            parts = await db.fetch("select id from visit_part_items where visit_id=$1", vid)
            ids = [vid, *item_ids, *[str(p["id"]) for p in parts]]
            audit = await db.fetch("select id from audit_log where entity_id = any($1::uuid[]) order by at", ids)
            for n, row in enumerate(audit, 1):
                await db.execute("update audit_log set at=$2 where id=$1",
                                 row["id"], start + (end - start) * n / (len(audit) + 1))

        # Клиенты, согласия и авто — заведены в день первого заезда.
        first_seen: dict[str, datetime] = {}
        for spec, (_, start, _, _) in zip(VISITS, created):
            for k in (spec["c"], spec["v"]):
                first_seen.setdefault(k, start - timedelta(minutes=15))
        for key, cid in clients.items():
            t = first_seen.get(key, NOW - timedelta(days=180))
            await db.execute("update clients set created_at=$2 where id=$1", cid, t)
            await db.execute("update consents set created_at=$2, consent_date=$2 where client_id=$1", cid, t)
        for key, vid in vehicles.items():
            await db.execute("update vehicles set created_at=$2 where id=$1", vid, first_seen.get(key, NOW))
        await db.execute("update work_catalog set created_at=$2 where id = any($1::uuid[])",
                         [c[0] for c in catalog.values()], NOW - timedelta(days=200))
        await db.execute(
            "update vehicle_ownership set date_to=$3 where vehicle_id=$1 and client_id=$2 and date_to is null",
            vehicles[resale_vehicle], clients[VEHICLES[resale_vehicle][0]], resale_date)
        for key, days in DISMISSED.items():
            await db.execute("update users set deleted_at=$2 where id=$1", staff[key], NOW - timedelta(days=days))

    await db.close()
    print(f"Готово: {len(STAFF)} сотрудников, {len(clients)} клиентов, {len(vehicles)} авто, "
          f"{len(CATALOG)} работ в каталоге, {len(created)} заездов.")


if __name__ == "__main__":
    asyncio.run(main())
