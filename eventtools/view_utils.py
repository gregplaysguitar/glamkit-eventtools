from datetime import date, timedelta
from django.conf import settings
from date_range import days_in_month, humanized_date_range
from dateutil.relativedelta import relativedelta
from dateutil import parser as dateparser

DEFAULT_SPAN_DAYS = getattr(settings, "DEFAULT_SPAN_DAYS", 28)

def clamp_to_start(d):
    return date(d.year, d.month, 1)
    
def clamp_to_end(d):
    return date(d.year, d.month, days_in_month(d))

def get_date_range(fr=None, to=None, default_fr=date.today(), default_to=None, min_span=DEFAULT_SPAN_DAYS, clamp_start=True, clamp_end=True):
    """
    If not from and not to, use defaults, optionally clamped to start and end of month
    Elif from and not to, to = from+min_span, optionally clamped to end of month
    Elif to and not from, from = to - min_span, optionally clamped to end of month
    """
    
    if clamp_start:
        _clamp_to_start = clamp_to_start
    else:
        _clamp_to_start = lambda x: x
        
    if clamp_end:
        _clamp_to_end = clamp_to_end
    else:
        _clamp_to_end = lambda x: x
    
    if not default_to:
        default_to = default_fr + timedelta(days=min_span)
        
    if not fr and not to:
        fr = _clamp_to_start(default_fr)
        to = _clamp_to_end(default_to)
    elif fr and not to:
        to = _clamp_to_end(default_to)
    elif to and not fr:
        fr = _clamp_to_start(default_fr)
        
    if to < fr:
        tmp = fr
        fr = to
        to = tmp
    
    return {
        'from': fr,
        'to': to,
        'uses_defaults': ((fr == _clamp_to_start(default_fr)) and (to == _clamp_to_end(default_to))),
    }
    
def get_date_info(fr=None, to=None, default_fr=date.today(), default_to=None, min_span=DEFAULT_SPAN_DAYS, clamp_start=True, clamp_end=True):
    dr = get_date_range(fr, to, default_fr, default_to, min_span, clamp_start, clamp_end)
    
    d1 = clamp_to_start(dr['from'])
    d2 = clamp_to_start(dr['to'])
    
    months = []
    while d1 <= d2:
        months.append(d1)
        d1 = d1 + relativedelta(months=1)
    
    if dr['uses_defaults']:
        description = ""
    else:
        description = humanized_date_range(dr['from'], dr['to'], imply_year=False)
    
    dr.update({
        'months': months,
        'description': description,
        'next_month': months[-1] + relativedelta(months=1),
        'prev_month': months[0] - relativedelta(months=1),
        'next_day': dr['from'] + timedelta(1),
        'prev_day': dr['from'] - timedelta(1),
    })
    
    return dr
    
def get_date_info_from_request(request, default_fr=date.today(), default_to=None, min_span=DEFAULT_SPAN_DAYS, clamp_start=True, clamp_end=True, day=None):
    month = request.GET.get('month', None)
    day = request.GET.get('day', None) or day
    fr = request.GET.get('from', None)
    to = request.GET.get('to', None)
    
    if month:
        month = dateparser.parse(month+"-01").date()
        fr = month
        to = clamp_to_end(month)
    elif day:
        fr = to = dateparser.parse(day).date()
    else:
        fr = request.GET.get('from', None)
        to = request.GET.get('to', None)
        if fr:
            fr = dateparser.parse(fr).date()
        if to:
            to = dateparser.parse(to).date()
    
    return get_date_info(fr, to, default_fr, default_to, min_span, clamp_start, clamp_end)