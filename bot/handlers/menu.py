"""Main-menu entry points.

This router is included right after start.router (before any router with
FSM-state handlers), so a menu button always wins over an in-progress
wizard. Every entry handler clears the FSM state before starting its flow.
"""
from aiogram import F, Router

from bot import keyboards
from bot.handlers import admin, consent, mechanic, navigation, search, visits

router = Router()

_ENTRY_POINTS = {
    keyboards.NEW_VISIT: visits.start_new_visit,
    keyboards.ACTIVE_VISITS: navigation.show_active_visits,
    keyboards.SEARCH: search.start_search,
    keyboards.PAPER_CONSENT: consent.start_paper_consent,
    keyboards.ADD_STAFF: admin.start_new_staff,
    keyboards.MY_WORK_ITEMS: mechanic.show_my_work_items,
}

for _text, _handler in _ENTRY_POINTS.items():
    router.message.register(_handler, F.text == _text)
