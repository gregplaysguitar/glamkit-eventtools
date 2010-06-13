# −*− coding: UTF−8 −*−
from django.db import models
from django.utils.translation import ugettext, ugettext_lazy as _
from django.template.defaultfilters import date as date_filter
from datetime import date, datetime, time
from django.core.exceptions import ObjectDoesNotExist
from eventtools.utils import OccurrenceReplacer
from dateutil import rrule
import sys

from django.db.models.base import ModelBase

class OccurrenceGeneratorModelBase(ModelBase):
    """
    When we create an OccurrenceGenerator, add to it an occurrence_model_name so it knows what to generate.
    """
    
    def __init__(cls, name, bases, attrs):
        if name != 'OccurrenceGeneratorBase': # This should only fire if this is a subclass
            model_name = name[0:-len("Generator")].lower()
            cls.add_to_class('_occurrence_model_name', model_name)
        super(OccurrenceGeneratorModelBase, cls).__init__(name, bases, attrs)
    
class OccurrenceGeneratorBase(models.Model):
    """
    Defines a set of repetition rules for an event
    """
    
    __metaclass__ = OccurrenceGeneratorModelBase
    
    first_start_date = models.DateField(_('first start date'))
    first_start_time = models.TimeField(_('first start time'))
    first_end_date = models.DateField(_('first end date'), null = True, blank = True)
    first_end_time = models.TimeField(_('first end time')) #wasn't originally required, but it turns out you do have to say when an event ends...
    rule = models.ForeignKey('Rule', verbose_name=_("repetition rule"), null = True, blank = True, help_text="Select '----' for a one-off event.")
    repeat_until = models.DateTimeField(null = True, blank = True, help_text=_("This date is ignored for one-off events."))
    
    class Meta:
        ordering = ('first_start_date', 'first_start_time')
        abstract = True
        verbose_name = _('occurrence generator')
        verbose_name_plural = _('occurrence generators')

    def _occurrence_model(self):
        return models.get_model(self._meta.app_label, self._occurrence_model_name)
    OccurrenceModel = property(_occurrence_model)

        
    def _end_recurring_period(self):
        return self.repeat_until
#         if self.end:
#             return datetime.datetime.combine(self.end_day, datetime.time.max)
#         else:
#             return None	
    end_recurring_period = property(_end_recurring_period)

    # for backwards compatibility    
    def _get_start(self):
        return datetime.combine(self.first_start_date, self.first_start_time)

    def _set_start(self, value):
        self.first_start_date = value.date()
        self.first_start_time = value.time()
        
    start = property(_get_start, _set_start)
    
    def _get_end_time(self):
        return self.first_end_time
        
    def _set_end_time(self, value):
        self.first_end_time = value
    
    end_time = property(_get_end_time, _set_end_time)    
        
    def _end(self):
        return datetime.combine(self.first_end_date or self.first_start_date, self.first_end_time)
    end = property(_end)

    def __unicode__(self):
        date_format = u'l, %s' % ugettext("DATE_FORMAT")
        return ugettext('%(title)s: %(start)s-%(end)s') % {
            'title': unicode(self.event),
            'start': date_filter(self.start, date_format),
            'end': date_filter(self.end, date_format),
        }

    def get_occurrences(self, start, end):
        exceptional_occurrences = self.occurrences.all()
        occ_replacer = OccurrenceReplacer(exceptional_occurrences)
        occurrences = self._get_occurrence_list(start, end)
        final_occurrences = []
        for occ in occurrences:
            # replace occurrences with their exceptional counterparts
            if occ_replacer.has_occurrence(occ):
                p_occ = occ_replacer.get_occurrence(occ)
                # ...but only if they are within this period
                if p_occ.start < end and p_occ.end >= start:
                    final_occurrences.append(p_occ)
            else:
              final_occurrences.append(occ)
        # then add exceptional occurrences which originated outside of this period but now
        # fall within it
        final_occurrences += occ_replacer.get_additional_occurrences(start, end)

        # import pdb; pdb.set_trace()
        return final_occurrences
        

    def get_rrule_object(self):
        if self.rule is not None:
            if self.rule.complex_rule:
                try:
                    return rrule.rrulestr(str(self.rule.complex_rule),dtstart=self.start)
                except:
                    pass
            params = self.rule.get_params()
            frequency = 'rrule.%s' % self.rule.frequency
            simple_rule = rrule.rrule(eval(frequency), dtstart=self.start, **params)
            set = rrule.rruleset()
            set.rrule(simple_rule)
#             goodfriday = rrule.rrule(rrule.YEARLY, dtstart=self.start, byeaster=-2)
#             christmas = rrule.rrule(rrule.YEARLY, dtstart=self.start, bymonth=12, bymonthday=25)
#             set.exrule(goodfriday)
#             set.exrule(christmas)
            return set

    def _create_occurrence(self, start, end=None):
        if end is None:
            end = start + (self.end - self.start)
        occ = self.OccurrenceModel(
            generator=self,
            unvaried_start_date=start.date(),
            unvaried_start_time=start.time(),
            unvaried_end_date=end.date(),
            unvaried_end_time=end.time(),
        )
        return occ
    
    def check_for_exceptions(self, occ):
        """
        Pass in an occurrence, pass out the occurrence, or an exceptional occurrence, if one exists in the db.
        """
        try:
            return self.OccurrenceModel.objects.get(
                generator = self,
                unvaried_start_date = occ.unvaried_start_date,
                unvaried_start_time = occ.unvaried_start_time,
                unvaried_end_date = occ.unvaried_end_date,
                unvaried_end_time = occ.unvaried_end_time,
            )
        except self.OccurrenceModel.DoesNotExist:
            return occ
                
    def get_first_occurrence(self):
        occ = self.OccurrenceModel(
                generator=self,
                unvaried_start_date=self.first_start_date,
                unvaried_start_time=self.first_start_time,
                unvaried_end_date=self.first_end_date,
                unvaried_end_time=self.first_end_time,
            )
        occ = self.check_for_exceptions(occ)
        return occ
    
    def get_one_occurrence(self):
        """
        This gets ANY accurrence, it doesn't matter which.
        So the quick thing is to try getting one from the database.
        If that fails, then just create the first occurrence.
        """
        try:
            return self.OccurrenceModel.objects.filter(generator=self)[0]
        except IndexError:
            return self.get_first_occurrence()
        return occ

    def get_occurrence(self, date):
        rule = self.get_rrule_object()
        if rule:
            next_occurrence = rule.after(date, inc=True)
        else:
            next_occurrence = self.start
        if next_occurrence == date:
            try:
                return self.OccurrenceModel.objects.get(generator__event = self, unvaried_start_date = date)
            except self.OccurrenceModel.DoesNotExist:
                return self._create_occurrence(next_occurrence)
        # import pdb; pdb.set_trace()

    def _get_occurrence_list(self, start, end):
        """
        generates a list of unexceptional occurrences for this event from start to end.
        """
        
        difference = (self.end - self.start)
        if self.rule is not None:
            occurrences = []
            if self.end_recurring_period and self.end_recurring_period < end:
                end = self.end_recurring_period
            rule = self.get_rrule_object()
            o_starts = rule.between(start-difference, end, inc=True)
            for o_start in o_starts:
                o_end = o_start + difference
                occurrences.append(self._create_occurrence(o_start, o_end))
            return occurrences
        else:
            # check if event is in the period
            if self.start < end and self.end >= start:
                return [self._create_occurrence(self.start)]
            else:
                return []
                        
    def _occurrences_after_generator(self, after=None):
        """
        returns a generator that produces unexceptional occurrences after the
        datetime ``after``.
        """

        if after is None:
            after = datetime.datetime.now()
        rule = self.get_rrule_object()
        if rule is None:
            if self.end > after:
                yield self._create_occurrence(self.start, self.end)
            raise StopIteration
        date_iter = iter(rule)
        difference = self.end - self.start
        while True:
            o_start = date_iter.next()
            if o_start > self.end_recurring_period:
                raise StopIteration
            o_end = o_start + difference
            if o_end > after:
                yield self._create_occurrence(o_start, o_end)


    def occurrences_after(self, after=None):
        """
        returns a generator that produces occurrences after the datetime
        ``after``.	Includes all of the exceptional Occurrences.
        """
        occ_replacer = OccurrenceReplacer(self.occurrence_set.all())
        generator = self._occurrences_after_generator(after)
        while True:
            next = generator.next()
            yield occ_replacer.get_occurrence(next)


class MergedObject():
    """
    Objects of this class behave as though they are a merge of two other objects (which we'll call General and Special). The attributes of Special override the corresponding attributes of General, *unless* the value of the attribute in Special == None.
    
    All attributes are read-only, to save you from a world of pain.
    
    """

    def __init__(self, general, special):
        self._general = general
        self._special = special
        
    def __getattr__(self, value):
        
        try:
            result = getattr(self._special, value)
            if result == None:
                raise AttributeError
        except AttributeError:
            result = getattr(self._general, value)

        return result
        
    def __setattr__(self, attr, value):
        if attr in ['_general', '_special']:
            self.__dict__[attr] = value
        else:
            raise AttributeError("Set the attribute on one of the objects that are being merged.")
    
        

class OccurrenceBase(models.Model):
    """
    Occurrences represent an occurrence of an event, which have been lazily generated by one of the event's OccurrenceGenerators. The foreign key to the right 'OccurrenceGenerator' is monkeypatched in to the 'OccurrenceBase' subclass. This foreign key is called 'generator'.
    
    Occurrences are not usually saved to the database, since there is potentially an infinite number of them (for events that repeat forever).
    
    However, if a particular occurrence is changed in any way (by changing the timing parameters, or by cancelling the occurence), then it should be saved to the database as an exception.
    
    When generating a set of occurrences, the generator should check to see if any exceptions have been saved to the databes.
    """
    
    #These four work as a key to the Occurrence
    unvaried_start_date = models.DateField(db_index=True)
    unvaried_start_time = models.TimeField(db_index=True)
    unvaried_end_date = models.DateField(_("unvaried end date"), db_index=True, null=True)
    unvaried_end_time = models.TimeField(_("unvaried end time"), db_index=True, null=True, help_text=_("if ommitted, start date is assumed"))
    
    # These are usually the same as the unvaried, but may not always be.
    varied_start_date = models.DateField(_("varied start date"), blank=True, null=True, db_index=True)
    varied_start_time = models.TimeField(_("varied start time"), blank=True, null=True, db_index=True)
    varied_end_date = models.DateField(_("varied end date"), blank=True, null=True, db_index=True, help_text=_("if ommitted, start date is assumed"))
    varied_end_time = models.TimeField(_("varied end time"), blank=True, null=True, db_index=True)
    
    cancelled = models.BooleanField(_("cancelled"), default=False)

    
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
        return datetime.combine(self.varied_start_date, self.varied_start_time)

    def _set_varied_start(self, value):
        self.varied_start_date = value.date
        self.varied_start_time = value.time
        
    start = varied_start = property(_get_varied_start, _set_varied_start)
    
    def _get_varied_end(self):
        return datetime.combine(self.varied_end_date or self.varied_start_date, self.varied_end_time)

    def _set_varied_end(self, value):
        self.varied_end_date = value.date
        self.varied_end_time = value.time
    
    end = varied_end = property(_get_varied_end, _set_varied_end)    
        
    def _get_unvaried_start(self):
        return datetime.combine(self.unvaried_start_date, self.unvaried_start_time)

    def _set_unvaried_start(self, value):
        self.unvaried_start_date = value.date()
        self.unvaried_start_time = value.time()
        
    original_start = unvaried_start = property(_get_unvaried_start, _set_unvaried_start)
    
    def _get_unvaried_end(self):
        return datetime.combine(self.unvaried_end_date or self.unvaried_start_date, self.unvaried_end_time)

    def _set_unvaried_end(self, value):
        self.unvaried_end_date = value.date
        self.unvaried_end_time = value.time
    
    original_end = unvaried_end = property(_get_unvaried_end, _set_unvaried_end)    
    
    # end backwards compatibility stuff
               
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

#     def move(self, new_start, new_end):
#         self.start = new_start
#         self.end = new_end
#         self.save()

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



    def __cmp__(self, other): #used for sorting occurrences.
        rank = cmp(self.start, other.start)
        if rank == 0:
            return cmp(self.end, other.end)
        return rank

    def __eq__(self, other):
        return self.generator.event == other.generator.event and self.original_start == other.original_start and self.original_end == other.original_end
        
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

class EventModelBase(ModelBase):
    def __init__(cls, name, bases, attrs):
        """
        Dynamically build two related classes to handle occurrences.
        
        The two generated classes are ModelNameOccurrence and ModelNameOccurrenceGenerator.
        
        If the EventBase subclass is called e.g. LectureEvent, then the two generated class will be called LectureEventOccurrence and LectureEventOccurrenceGenerator (yeesh, but end-user never sees these.)
        
        """
        if name != 'EventBase': # This should only fire if this is a subclass (maybe we should make devs apply this metaclass to their subclass instead?)
            # Build names for the new classes
            occ_name = "%s%s" % (name, "Occurrence")
            gen_name = "%s%s" % (occ_name, "Generator")
        
            cls.add_to_class('_occurrence_model_name', occ_name)
            cls.add_to_class('_generator_model_name', gen_name)
        
            # Create the generator class
            # globals()[gen_name] # < injecting into globals doesn't work with some of django's import magic. We have to inject the new class directly into the module that contains the EventBase subclass. I am AMAZED that you can do this, and have it still work for future imports.
            setattr(sys.modules[cls.__module__], gen_name, type(gen_name,
                    (OccurrenceGeneratorBase,),
                    dict(__module__ = cls.__module__,),
                )
            )
            generator_class = sys.modules[cls.__module__].__dict__[gen_name]
            
            # add a foreign key back to the event class
            generator_class.add_to_class('event', models.ForeignKey(cls, related_name = 'generators'))

            # Create the occurrence class
            # globals()[occ_name]
            setattr(sys.modules[cls.__module__], occ_name, type(occ_name,
                    (OccurrenceBase,),
                    dict(__module__ = cls.__module__,),
                )
            )
            occurrence_class = sys.modules[cls.__module__].__dict__[occ_name]

            occurrence_class.add_to_class('generator', models.ForeignKey(generator_class, related_name = 'occurrences'))
            if hasattr(cls, 'varied_by'):
               occurrence_class.add_to_class('_varied_event', models.ForeignKey(cls.varied_by, related_name = 'occurrences', null=True))
               # we need to add an unvaried_event FK into the variation class, BUT at this point the variation class hasn't been defined yet. For now, let's insist that this is done by using a base class for variation.

        super(EventModelBase, cls).__init__(name, bases, attrs)
        
class EventBase(models.Model):
    """
    Event information minus the scheduling details.
    
    Event scheduling is handled by one or more OccurrenceGenerators
    """
    __metaclass__ = EventModelBase

    class Meta:
        abstract = True

    def _opts(self):
        return self._meta
    opts = property(_opts) #for use in templates (without underscore necessary)

    def _occurrence_model(self):
        return models.get_model(self._meta.app_label, self._occurrence_model_name)
    OccurrenceModel = property(_occurrence_model)

    def _generator_model(self):
        return models.get_model(self._meta.app_label, self._generator_model_name)
    GeneratorModel = property(_generator_model)

    def first_generator(self):
        return self.generators.order_by('first_start_date', 'first_start_time')[0]
        
    def get_one_occurrence(self):
        try:
            return self.generators.all()[0].get_one_occurrence()
        except IndexError:
            raise IndexError("This Event type has no generators defined")
    
    def get_first_occurrence(self):
        try:
            return self.first_generator().get_first_occurrence()		
        except IndexError:
            raise IndexError("This Event type has no generators defined")
    
    def get_occurrences(self, start, end):
        occs = []
        for gen in self.generators.all():
            occs += gen.get_occurrences(start, end)
        return sorted(occs)


        
    def get_last_day(self):
        lastdays = []
        for generator in self.generators.all():
            if not generator.end_recurring_period:
                return False
            lastdays.append(generator.end_recurring_period)
        lastdays.sort()
        return lastdays[-1]

    def _has_zero_generators(self):
        return self.generators.count() == 0
    has_zero_generators = property(_has_zero_generators)
        
    def _has_multiple_occurrences(self):
        return self.generators.count() > 1 or (self.generators.count() > 0 and self.generators.all()[0].rule != None)
    has_multiple_occurrences = property(_has_multiple_occurrences)

    def edit_occurrences_link(self):
        """ An admin link """
        # if self.has_multiple_occurrences:
        if self.has_zero_generators:
            return _('no occurrences yet (<a href="%s/">add a generator here</a>)' % self.id)
        else:
           return '<a href="%s/occurrences/">%s</a>' % (self.id, unicode(_("view/edit occurrences")))
            
        # return _('(<a href="%s/">edit </a>)')
    edit_occurrences_link.allow_tags = True
    edit_occurrences_link.short_description = _("Occurrences")
    
    def variations_count(self):
        """
        returns the number of variations that this event has
        """
        if self.__class__.varied_by:
            return self.variations.count()
        else:
            return "N/A"
        
    variations_count.short_description = _("# Variations")
    
    def create_generator(self, *args, **kwargs):
        if kwargs.has_key('start'):
            start = kwargs.pop('start')
            kwargs.update({
                'first_start_date': start.date(),
                'first_start_time': start.time()
            })
        if kwargs.has_key('end'):
            end = kwargs.pop('end')
            kwargs.update({
                'first_end_date': end.date(),
                'first_end_time': end.time()
            })
        return self.generators.create(*args, **kwargs)
    
    def create_variation(self, *args, **kwargs):
        kwargs['unvaried_event'] = self
        return self.variations.create(*args, **kwargs)
    
    def get_absolute_url(self):
        return "/event/%s/" % self.id
    
    def next_occurrences(self):
        from eventtools.periods import Period
        first = False
        last = False
        for gen in self.generators.all():
            if not first or gen.start < first:
                first = gen.start
            if gen.rule and not gen.end_day:
                last = False # at least one rule is infinite
                break
            if not gen.end_day:
                genend = gen.start
            else:
                genend = gen.end_recurring_period
            if not last or genend > last:
                last = genend
        if last:
            period = Period(self.generators.all(), first, last)
        else:
            period = Period(self.generators.all(), datetime.datetime.now(), datetime.datetime.now() + datetime.timedelta(days=28))		
        return period.get_occurrences()

class EventVariationModelBase(ModelBase):
    def __init__(cls, name, bases, attrs):
        if name != 'EventVariationBase': # This should only fire if this is a subclass
            #Inject an unvaried_event FK if none is defined.
            #Uses the unDRY cls.varies to name the class to FK to.
            if not attrs.has_key('unvaried_event'):
                cls.add_to_class('unvaried_event', models.ForeignKey(cls.varies, related_name="variations"))
                
        super(EventVariationModelBase, cls).__init__(name, bases, attrs)


class EventVariationBase(models.Model):
    __metaclass__ = EventVariationModelBase
    
    reason = models.CharField(_("Short reason for variation"), max_length = 255, help_text=_("this won't normally be shown to visitors, but is useful for identifying this variation in lists"))

    def __unicode__(self):
        return self.reason
        
    class Meta:
        abstract = True

freqs = (
    ("YEARLY", _("Yearly")),
    ("MONTHLY", _("Monthly")),
    ("WEEKLY", _("Weekly")),
    ("DAILY", _("Daily")),
    ("HOURLY", _("Hourly")),
)

class Rule(models.Model):
    """
    This defines a rule by which an event will repeat.  This is defined by the
    rrule in the dateutil documentation.

    * name - the human friendly name of this kind of repetition.
    * description - a short description describing this type of repetition.
    * frequency - the base repetition period
    * param - extra params required to define this type of repetition. The params
      should follow this format:

        param = [rruleparam:value;]*
        rruleparam = see list below
        value = int[,int]*

      The options are: (documentation for these can be found at
      http://labix.org/python-dateutil#head-470fa22b2db72000d7abe698a5783a46b0731b57)
        ** count
        ** bysetpos
        ** bymonth
        ** bymonthday
        ** byyearday
        ** byweekno
        ** byweekday
        ** byhour
        ** byminute
        ** bysecond
        ** byeaster
    """
    name = models.CharField(_("name"), max_length=100, help_text=_("a short friendly name for this repetition."))
    description = models.TextField(_("description"), blank=True, help_text=_("a longer description of this type of repetition."))
    common = models.BooleanField(help_text=_("common rules appear at the top of the list."))
    frequency = models.CharField(_("frequency"), choices=freqs, max_length=10, blank=True, help_text=_("the base repetition period."))
    params = models.TextField(_("inclusion parameters"), blank=True, help_text=_("extra params required to define this type of repetition."))
    complex_rule = models.TextField(_("complex rules"), help_text=_("over-rides all other settings."), blank=True)

    class Meta:
        verbose_name = _('repetition rule')
        verbose_name_plural = _('repetition rules')
        ordering = ('-common', 'name')

    def get_params(self):
        """
        >>> rule = Rule(params = "count:1;bysecond:1;byminute:1,2,4,5")
        >>> rule.get_params()
        {'count': 1, 'byminute': [1, 2, 4, 5], 'bysecond': 1}
        """
    	params = self.params
        if params is None:
            return {}
        params = params.split(';')
        param_dict = []
        for param in params:
            param = param.split(':')
            if len(param) == 2:
                param = (str(param[0]), [int(p) for p in param[1].split(',')])
                if len(param[1]) == 1:
                    param = (param[0], param[1][0])
                param_dict.append(param)
        return dict(param_dict)
        
    def __unicode__(self):
        """Human readable string for Rule"""
        return self.name

