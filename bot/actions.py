"""callback_data shared by the screen that draws a button and the handler that runs it.

`act:` buttons carry no entity ids: the handler takes them from the top
screen's args (`nav.top_args`). `wiz:` buttons start a wizard from the menu.
"""
NEW_VISIT = "wiz:new_visit"
PAPER_CONSENT = "wiz:paper_consent"
NEW_STAFF = "wiz:new_staff"

ADD_WORK = "act:add_work"
ADD_PART = "act:add_part"
APPROVE = "act:approve"
PDF = "act:pdf"
NEW_VISIT_FOR = "act:new_visit_for"
ADD_VEHICLE = "act:add_vehicle"
VISIT_STATUS = "act:vstatus"  # + ":<visit status>"
WORK_STATUS = "act:wstatus"  # + ":<work item status>"
REASSIGN = "act:reassign"  # + ":<encoded mechanic id>" or ":none"
SEARCH_PAGE = "act:spage"  # + ":<page>"
