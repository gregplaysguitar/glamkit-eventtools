import calendar
from datetime import date, timedelta
from dateutil.relativedelta import *
from django import template

register = template.Library()

def week_calendar(events_pool=[], selected_start=None):
    """
    Creates a configurable html calendar displaying one week, starting today
    
    It takes one optional argument:
    selected_start:
    """
    
    today = date.today()
    if not selected_start:
        selected_start = today
    
    selected_end = selected_start + timedelta(6) # so, today, plus 6 more days is a week
    
    events_by_date = {}
    
    # get all of the occurrences for this week and add to the events_by_date
    for event in events_pool:
        occs = event.get_occurrences(selected_start, selected_end)
        for occ in occs:
            if events_by_date.has_key(occ.start_date):
                events_by_date[occ.start_date].append(occ.merged_event)
            else:
                events_by_date[occ.start_date] = [occ.merged_event]
    
    week_calendar = []
    # go through all the days of the week, name it, and give it occurrences
    for i in range(7):
        the_day = today + timedelta(i)
        
        occs = []
        if the_day in events_by_date:
            occs = events_by_date[the_day]
            
        week_calendar.append({"day": the_day.strftime("%A"), "occurrences": occs})
    
    return {'week_calendar': week_calendar}

register.inclusion_tag('eventtools/week_calendar.html')(week_calendar)