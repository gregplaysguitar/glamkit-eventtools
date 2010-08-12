# −*− coding: UTF−8 −*−
from django.db import models
import datetime
from django.utils.translation import ugettext, ugettext_lazy as _
from utils import MergedObject
from vobject import iCalendar

"""
Occurrences represent an occurrence of an event, which have been lazily generated by one of the event's OccurrenceGenerators.

Occurrences are NOT usually saved to the database, since there is potentially an infinite number of them (for events that repeat with no end date).

However, if a particular occurrence is exceptional in any way (by changing the timing parameters, or by cancelling the occurence, or by linking to an EventVariation), then it should be saved to the database as an exception.

When generating a set of occurrences, the generator checks to see if any exceptions have been saved to the database.
"""

class OccurrenceBase(models.Model):
    
    # injected by EventModelBase:
    # generator = models.ForeignKey(somekindofOccurrenceGenerator)
    # _varied_event = models.ForeignKey(somekindofEventVariation)
    
    #These four work as a key to the Occurrence
    unvaried_start_date = models.DateField(db_index=True)
    unvaried_start_time = models.TimeField(db_index=True)
    unvaried_end_date = models.DateField(_("unvaried end date"), db_index=True, null=True, help_text=_("if omitted, start time is assumed"))
    unvaried_end_time = models.TimeField(_("unvaried end time"), db_index=True, null=True, help_text=_("if omitted, start date is assumed"))
    
    # These are usually the same as the unvaried, but may not always be.
    varied_start_date = models.DateField(_("varied start date"), blank=True, null=True, db_index=True)
    varied_start_time = models.TimeField(_("varied start time"), blank=True, null=True, db_index=True)
    varied_end_date = models.DateField(_("varied end date"), blank=True, null=True, db_index=True, help_text=_("if omitted, start date is assumed"))
    varied_end_time = models.TimeField(_("varied end time"), blank=True, null=True, db_index=True, help_text=_("if omitted, start time is assumed"))
    
    cancelled = models.BooleanField(_("cancelled"), default=False)
    hide_from_lists = models.BooleanField(_("hide_from_lists"), default=False, help_text="Hide this occurrence instead of explicitly cancelling it.")

    
    def __init__(self, *args, **kwargs):
        """by default, create items with varied values the same as unvaried"""
        
        for uv_key, v_key in [
            ('unvaried_start_date', 'varied_start_date'),
            ('unvaried_start_time', 'varied_start_time'),
            ('unvaried_end_date', 'varied_end_date'),
            ('unvaried_end_time', 'varied_end_time'),
        ]:
            if not kwargs.has_key(v_key):
                if kwargs.has_key(uv_key):
                    kwargs[v_key] = kwargs[uv_key]
                else:
                    kwargs[v_key] = None
        
        super(OccurrenceBase, self).__init__(*args, **kwargs)
    
    
    class Meta:
        verbose_name = _("occurrence")
        verbose_name_plural = _("occurrences")
        abstract = True
        unique_together = ('generator', 'unvaried_start_date', 'unvaried_start_time', 'unvaried_end_date', 'unvaried_end_time')

    def _merged_event(self): #bit slow, but friendly
        return MergedObject(self.unvaried_event, self.varied_event)
    merged_event = property(_merged_event)
        
    # for backwards compatibility - and some conciseness elsewhere. TODO: DRY this out 
    def _get_varied_start(self):
        return datetime.datetime.combine(self.varied_start_date, self.varied_start_time)
    def _set_varied_start(self, value):
        self.varied_start_date = value.date
        self.varied_start_time = value.time        
    start = varied_start = property(_get_varied_start, _set_varied_start)
    
    def _get_varied_end(self):
        return datetime.datetime.combine(self.varied_end_date or self.varied_start_date, self.varied_end_time)
    def _set_varied_end(self, value):
        self.varied_end_date = value.date
        self.varied_end_time = value.time  
    end = varied_end = property(_get_varied_end, _set_varied_end)    
        
    def _get_unvaried_start(self):
        return datetime.datetime.combine(self.unvaried_start_date, self.unvaried_start_time)
    def _set_unvaried_start(self, value):
        self.unvaried_start_date = value.date()
        self.unvaried_start_time = value.time()        
    original_start = unvaried_start = property(_get_unvaried_start, _set_unvaried_start)
    
    def _get_unvaried_end(self):
        return datetime.datetime.combine(self.unvaried_end_date or self.unvaried_start_date, self.unvaried_end_time)
    def _set_unvaried_end(self, value):
        self.unvaried_end_date = value.date
        self.unvaried_end_time = value.time   
    original_end = unvaried_end = property(_get_unvaried_end, _set_unvaried_end)    
    
    # end backwards compatibility stuff

    def _get_varied_event(self):
        try:
            return getattr(self, "_varied_event", None)
        except:
            return None
    def _set_varied_event(self, v):
        if "_varied_event" in dir(self): #for a very weird reason, hasattr(self, "_varied_event") fails. Perhaps this is because it is injected by __init__ in the metaclass, not __new__.
            self._varied_event = v
        else:
            raise AttributeError("You can't set an event variation for an event class with no 'varied_by' attribute.")
    varied_event = property(_get_varied_event, _set_varied_event)

    def _get_unvaried_event(self):
        return self.generator.event
    unvaried_event = property(_get_unvaried_event)
               
    def _is_moved(self):
        return self.unvaried_start != self.varied_start or self.unvaried_end != self.varied_end
    is_moved = property(_is_moved)
    
    def _is_varied(self):
        return self.is_moved or self.cancelled
    is_varied = property(_is_varied)
    
    def _start_time(self):
        return self.varied_start_time #being canonical
    start_time = property(_start_time)
    
    def _end_time(self):
        return self.varied_end_time #being canonical
    end_time = property(_end_time)

    def _start_date(self):
        return self.varied_start_date #being canonical
    start_date = property(_start_date)
    
    def _end_date(self):
        return self.varied_end_date #being canonical
    end_date = property(_end_date)


    def cancel(self):
        self.cancelled = True
        self.save()

    def uncancel(self):
        self.cancelled = False
        self.save()

    def __unicode__(self):
        return ugettext("%(event)s: %(day)s") % {
            'event': self.generator.event.title,
            'day': self.varied_start.strftime('%a, %d %b %Y'),
        }

    def __cmp__(self, other): #used for sorting occurrences.
        rank = cmp(self.start, other.start)
        if rank == 0:
            return cmp(self.end, other.end)
        return rank

    def __eq__(self, other):
        return self.generator.event == other.generator.event and self.original_start == other.original_start and self.original_end == other.original_end

    def unvaried_range_string(self):
        return ugettext(u"%(start)s–%(end)s") % {
            'start': self.unvaried_start.strftime('%a, %d %b %Y %H:%M'),
            'end': self.unvaried_end.strftime('%a, %d %b %Y %H:%M'),
        }

    def varied_range_string(self):
        return ugettext(u"%(start)s–%(end)s") % {
            'start': self.varied_start.strftime('%a, %d %b %Y %H:%M'),
            'end': self.varied_end.strftime('%a, %d %b %Y %H:%M'),
        }
    
    @property
    def date_description(self):
        return ugettext("%(day)s, %(time)s") % {
            'day': self.varied_start.strftime('%a, %d %b %Y'),
            'time': self.varied_start.strftime('%H:%M'),
        }
        
    @property
    def as_icalendar(self):
        """
        Returns the occurrence as an iCalendar object
        """
        ical = iCalendar()
        ical.add('vevent').add('summary').value = self.merged_event.title
        ical.vevent.add('dtstart').value = datetime.datetime.combine(self.start_date, self.start_time) 
        ical.vevent.add('dtend').value = datetime.datetime.combine(self.end_date, self.end_time)
        return ical 

    @property
    def reason(self):
        # varied event reason trumps all
        if self.varied_event:
            return self.varied_event.reason
        
        # cancellation trumps date/time changes
        if self.cancelled:
            return "Cancelled"

        """
        if start_date is different:
            "moved to " start_date
        if start_time or end_time are less than the original:
            "starts earlier, at " start_time/end_time
        if start_time or end_time are greater than the original:
            "finishes later, at " start_time/end_time
        """

        messages = []
        if self.varied_start_date != self.unvaried_start_date:
            messages.append("new date")
        
        if self.varied_start_time < self.unvaried_start_time:
            messages.append("starts earlier at %s" % self.varied_start_time.strftime("%H:%M"))
        elif self.varied_start_time > self.unvaried_start_time:
            messages.append("starts later at %s" % self.varied_start_time.strftime("%H:%M"))
            
        if self.varied_end_time < self.unvaried_end_time:
            messages.append("ends earlier at %s" % self.varied_end_time.strftime("%H:%M"))
        elif self.varied_end_time > self.unvaried_end_time:
            messages.append("ends later at %s" % self.varied_end_time.strftime("%H:%M"))
        
        return ", ".join(messages)
        
    @property
    def generated_id(self):
        """
        this occurrence is unique for an EVENT (the un/varied event) and for a particular DAY (start) and a particular place in a list
        """
        daystart = self.start.replace(hour=0, minute=0)
        occurrence_list = self.generator.event.get_occurrences(daystart, daystart + datetime.timedelta(1))
        return occurrence_list.index(self)