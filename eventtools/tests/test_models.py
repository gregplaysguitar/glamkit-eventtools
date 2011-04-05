import datetime
import os
from django.core.urlresolvers import reverse
from django.db import models
from django.core.exceptions import ValidationError
from django.db.models import get_model
from django.db.models.fields.related import ReverseSingleRelatedObjectDescriptor
from eventtools.tests.eventtools_testapp.models import *
from eventtools.tests.eventtools_testapp.forms import *
from datetime import date, datetime, time, timedelta
from _inject_app import TestCaseWithApp as TestCase
from eventtools.models import Rule

class TestModelMetaClass(TestCase):

    # def setUp(self):
    #     super(TestModelMetaClass, self).setUp()

    def test_model_metaclass_generation(self):
        """
        Test that when we create a subclass of EventBase, a corresponding subclass of OccurrenceBase is generated automatically
        """
        self.Occ1 = get_model('eventtools_testapp', 'lectureeventoccurrence')
        self.Occ2 = get_model('eventtools_testapp', 'broadcasteventoccurrence')
        self.Occ3 = get_model('eventtools_testapp', 'lessoneventoccurrence')
        self.occs = [self.Occ1, self.Occ2, self.Occ3]
        
        self.Gen1 = get_model('eventtools_testapp', 'lectureeventoccurrencegenerator')
        self.Gen2 = get_model('eventtools_testapp', 'broadcasteventoccurrencegenerator')
        self.Gen3 = get_model('eventtools_testapp', 'lessoneventoccurrencegenerator')
        self.gens = [self.Gen1, self.Gen2, self.Gen3]

        for (occ, gen,) in zip(self.occs, self.gens):
            #Check that for each EventBase model defined, an Occurrence and an OccurrenceGenerator are created.
            self.assertTrue((occ != None))
            self.assertTrue((gen != None))
            
            #...and that the right FKs are specified.
            self.assertTrue(isinstance(occ.generator, ReverseSingleRelatedObjectDescriptor)) #This is what ForeignKey becomes
            self.assertTrue(isinstance(gen.event, ReverseSingleRelatedObjectDescriptor))
            
            #...and that the occurrence model is linked properly to the generator
            self.assertEqual(gen._occurrence_model_name.lower(), occ.__name__.lower())

class TestModel(TestCase):
    def test_event_without_variation(self):
        """
        Events that have no variation class defined still work (and that it is not allowed to try to set a variation)
        """
        
        subject = 'Django testing for n00bs'
        lesson = LessonEvent.objects.create(subject=subject)
        gen = lesson.create_generator(first_start_date=date(2010, 1, 1), first_start_time=time(13, 0), first_end_date=None, first_end_time=time(14, 0))
        occ = lesson.get_one_occurrence()
        self.assertEqual(occ.varied_event, None)
        self.assertRaises(AttributeError, getattr, occ.varied_event, 'subject')
        self.assertRaises(AttributeError, setattr, occ, 'varied_event', 'foo')
        self.assertEqual(occ.unvaried_event.subject, subject)
        self.assertEqual(occ.merged_event.subject, subject)



    def test_event_occurrence_attributes(self):
        """Test that event occurrences can override (any) field of their parent event"""
        
        # Create an event, a generator, and get (the only possible) occurrence from the generator.
        te1 = LectureEvent.objects.create(location='The lecture hall', title='Lecture series on Butterflies')
        self.assertTrue(te1.wheelchair_access) # The original event has wheelchair access
        gen = te1.create_generator(first_start_date=date(2010, 1, 1), first_start_time=time(13, 0), first_end_date=None, first_end_time=time(14, 0))
        self.assertTrue(gen)
        occ = te1.get_one_occurrence()
        self.assertTrue(occ)
        
        #Test that the occurrence is the one we expect
        expected = LectureEventOccurrence(generator=gen, unvaried_start_date=date(2010, 1, 1), unvaried_start_time=time(13, 0), unvaried_end_time=time(14, 0))

        self.assertEqual(occ, expected)

        #and that the occurrence's unvaried event shares properties with te1
        self.assertTrue(isinstance(occ.unvaried_event, LectureEvent))
        self.assertTrue(occ.unvaried_event.wheelchair_access)
        #and that the merged event is what we expect
        self.assertTrue(occ.merged_event.wheelchair_access)
        self.assertEqual(occ.merged_event.location, 'The lecture hall')
        
        #When first generated, there is no varied event for an occurrence.
        self.assertEqual(occ.varied_event, None)
        #So accessing a property raises AttributeError
        self.assertRaises(AttributeError, getattr, occ.varied_event, 'location')
        
        #Now create a variation with a different location
        occ.varied_event = te1.create_variation(location='The foyer')
        
        #Check the properties of the varied event, and that the merged event uses those to override the unvaried event
        self.assertEqual(occ.varied_event.location, 'The foyer')
        self.assertEqual(occ.unvaried_event.location, 'The lecture hall')
        self.assertEqual(occ.varied_event.wheelchair_access, None)

        self.assertEqual(occ.merged_event.location, 'The foyer')
        self.assertEqual(occ.merged_event.title, 'Lecture series on Butterflies')

        #Check that we can't write to merged event.
        self.assertRaises(Exception, setattr, occ.merged_event.location, "shouldn't be writeable")

        #Now update the title, location and wheelchair access of the varied event, and save the result.
        occ.varied_event.title = 'Butterflies I have known'
        occ.varied_event.location = 'The meeting room'
        occ.varied_event.wheelchair_access = False
        occ.varied_event.save()
        occ.save()
        
        #Check that the update merges correctly with the unvaried event
        self.assertTrue((occ.unvaried_event.title == 'Lecture series on Butterflies'))
        self.assertTrue((occ.varied_event.title == 'Butterflies I have known'))
        self.assertTrue((occ.merged_event.title == 'Butterflies I have known'))


        self.assertTrue((occ.unvaried_event.location == 'The lecture hall'))
        self.assertTrue((occ.varied_event.location == 'The meeting room'))
        self.assertTrue((occ.merged_event.location == 'The meeting room'))

        self.assertEqual(occ.unvaried_event.wheelchair_access, True)
        self.assertEqual(occ.varied_event.wheelchair_access, False)
        self.assertEqual(occ.merged_event.wheelchair_access, False)

        #Now update the title of the original event. The changes in the variation should persist in the database.
        te1.title = 'Lecture series on Lepidoptera'
        te1.save()
        
        te1 = LectureEvent.objects.get(pk=te1.pk)
        occ = te1.get_one_occurrence() #from the database
        self.assertEqual(occ.unvaried_event.title, 'Lecture series on Lepidoptera')
        self.assertEqual(occ.merged_event.title, 'Butterflies I have known')
        self.assertEqual(occ.varied_event.title, 'Butterflies I have known')



    def test_saving(self):
        """
        A small check that saving occurrences without variations does not create a blank variation.
        TODO: expand this so to check changing the time of an exceptional occurrence works the same way.
        """
        te1 = LectureEvent.objects.create(location='The lecture hall', title='Lecture series on Butterflies')
        te1.create_generator(first_start_date=date(2010, 1, 1), first_start_time=time(13, 0), first_end_date=None, first_end_time=time(14, 0))
        occ = te1.get_one_occurrence()
        num_variations1 = int(LectureEventVariation.objects.count())
        occ.save()
        num_variations2 = int(LectureEventVariation.objects.count())
        self.assertEqual(num_variations1, num_variations2)
        
    def test_occurrence_and_occurrence_generator_validation(self):
        evt = LectureEvent.objects.create(location='The lecture hall', title='Lecture series on Amphibians')
        form = LectureEventOccurrenceGeneratorForm(dict(
                event=evt.pk,
                first_start_date=str(date(2010, 8, 1)),
                first_start_time=str(time(13, 0)),
                first_end_date=str(date(2010, 7, 1))))
        self.assertFalse(form.is_valid(), "end date cannot be later than start date")

        form = LectureEventOccurrenceGeneratorForm(dict(
                event=evt.pk,
                first_start_date=str(date(2010, 8, 1)),
                first_start_time=str(time(13, 0))))
        self.assertTrue(form.is_valid())

        # same as above, except first_end_date not specified
        form = LectureEventOccurrenceGeneratorForm(dict(
                event=evt.pk,
                first_start_date=str(date(2010, 8, 1)),
                first_start_time=str(time(13, 0)),
                first_end_time=str(time(13, 0))))
        self.assertTrue(form.is_valid())

        # first_end_date not specified
        form = LectureEventOccurrenceGeneratorForm(dict(
                event=evt.pk,
                first_start_date=str(date(2010, 8, 1)),
                first_start_time=str(time(13, 0)),
                first_end_date=str(date(2010, 8, 1))))
        self.assertTrue(form.is_valid())
        
        # Missing start time and date
        form = LectureEventOccurrenceGeneratorForm(dict(
                event=evt.pk,
                first_end_date=str(date(2010, 9, 1)),
                first_end_time=str(time(13, 0))))
        self.assertFalse(form.is_valid())

        # normal case
        form = LectureEventOccurrenceGeneratorForm(dict(
                event=evt.pk,
                first_start_date=str(date(2010, 8, 1)),
                first_start_time=str(time(13, 0)),
                first_end_date=str(date(2010, 9, 1))))
        self.assertTrue(form.is_valid(), "normal case, should have validated")
        form.save()

        occ = evt.get_one_occurrence()
        self.assertFalse(occ.is_varied)
        self.assert_(occ.clean() is None)

        occ.varied_end_date = occ.varied_start_date + timedelta(-1)
        self.assertTrue(occ.is_varied)
        self.assertRaises(ValidationError, occ.clean)

    
    def test_occurrence_generator_weirdness(self):
        evt = BroadcastEvent.objects.create(presenter = "Jimmy McBigmouth", studio=2)
        gen = evt.create_generator(first_start_date=date(2010, 1, 1), first_start_time=time(13, 0), first_end_date=None, first_end_time=time(14, 0))
        
        #This didn't always work. Testing prevents regeressions!
        self.assertTrue(evt)
        self.assertTrue(gen)
        self.assertEqual(evt.generators.count(), 1)
        self.assertEqual(list(evt.generators.all()), [gen])
    
    def test_occurrences(self):
        """
        Are modified occurrences saved and retrieved properly?
        """
        evt = BroadcastEvent.objects.create(presenter = "Jimmy McBigmouth", studio=2)
        #Let's start with 1 occurrence
        gen = evt.create_generator(first_start_date=date(2010, 1, 1), first_start_time=time(13, 0), first_end_date=None, first_end_time=time(14, 0))
        occ = evt.get_one_occurrence()
    
        self.assertEqual(occ.varied_start_time, time(13,0))
        self.assertEqual(occ.unvaried_start_time, time(13,0))
        self.assertEqual(occ.start_time, time(13,0))
        self.assertEqual(occ.generator, gen)
        
        self.assertEqual(occ.id, None)
        self.assertEqual(occ.is_varied, False)
        
        #What happens if we save it? It's persisted, but it's not varied.
        occ.save()
        
        self.assertTrue(occ.id != None)
        
        self.assertEqual(occ.is_varied, False)
        self.assertEqual(occ.cancelled, False)
        
        #and it doesn't have a variation event (but we could assign one if we wanted)
        self.assertEqual(occ.varied_event, None)
        
        #What happens when we change the timing?
        occ.varied_start_time = time(14,0)
        occ.save()
        
        self.assertEqual(occ.is_varied, True)
        self.assertEqual(occ.cancelled, False)
        self.assertEqual(occ.start_time, time(14,0))        
        #and let's check that re-querying returns the varied event
        
        occ = evt.get_one_occurrence()
        self.assertEqual(occ.is_varied, True)
        self.assertEqual(occ.cancelled, False)
        self.assertEqual(occ.start_time, time(14,0))        
        
    def test_cancellation(self):
        evt = BroadcastEvent.objects.create(presenter = "Jimmy McBigmouth", studio=2)
        #Let's start with 1 occurrence
        gen = evt.create_generator(first_start_date=date(2010, 1, 1), first_start_time=time(13, 0), first_end_date=None, first_end_time=time(14, 0))
        occ = evt.get_one_occurrence()

        self.assertEqual(occ.cancelled, False)

        occ.cancel()
        occ = evt.get_one_occurrence()
        self.assertEqual(occ.cancelled, True)
        
        occ.uncancel() 
        occ = evt.get_one_occurrence()
        self.assertEqual(occ.cancelled, False)
        
        
    def test_variation_model(self):
        evt = BroadcastEvent.objects.create(presenter = "Jimmy McBigmouth", studio=2) 
        
        #have we got the FKs in place
        self.assertTrue(hasattr(BroadcastEventVariation, 'unvaried_event'))
        self.assertTrue(hasattr(evt, 'variations'))
     
        # let's try it out
        var_event = evt.create_variation(presenter = "Amy Sub")
        self.assertEqual(list(evt.variations.all()), [var_event])
        
        # we can also do it this way
        
        var_event_2 = BroadcastEventVariation.objects.create(unvaried_event=evt, presenter = "Alan Loco")
        self.assertEqual(set(evt.variations.all()), set([var_event, var_event_2]))
        
        # but not on an event that doesn't have a varied_by
        lesson = LessonEvent.objects.create(subject="canons")
        self.assertRaises(AttributeError, lesson.create_variation, {'subject': 'cannons'})

    def test_between_queries(self):
        weekly = Rule.objects.create(name="weekly", frequency="WEEKLY")
        
        start_date = date(2010, 03, 1) #it's a monday
        end_date = start_date+timedelta(28) # it's a monday (the 29th)
        
        gardeners_question_time = BroadcastEvent.objects.create(presenter = "Jim Appleface", studio=2)
        gardeners_answer_time = BroadcastEvent.objects.create(presenter = "Jim Appleface", studio=1)
        
        #questions on mondays and tuesdays
        gardeners_question_time.create_generator(
            first_start_date=start_date,
            first_start_time=time(10,00),
            first_end_time=time(12,00),
            rule=weekly,
        )
        gardeners_question_time.create_generator(
            first_start_date=start_date+timedelta(1),
            first_start_time=time(10,00),
            first_end_time=time(12,00),
            rule=weekly,
        )

        #answers on thursdays and fridays
        gardeners_answer_time.create_generator(
            first_start_date=start_date+timedelta(3),
            first_start_time=time(10,00),
            first_end_time=time(12,00),
            rule=weekly,
        )
        gardeners_answer_time.create_generator(
            first_start_date=start_date-timedelta(4),
            first_start_time=time(10,00),
            first_end_time=time(12,00),
            rule=weekly,
        )

        
        all_occurrences = BroadcastEvent.objects.occurrences_between(start_date, end_date)
        self.assertEqual(len(all_occurrences), 17)
        
        studio1_occurrences = BroadcastEvent.objects.filter(studio=1).occurrences_between(start_date, end_date)
        self.assertEqual(len(studio1_occurrences), 8)
        
        answer_occurrences = gardeners_answer_time.generators.occurrences_between(start_date, end_date)
        self.assertEqual(studio1_occurrences, answer_occurrences)

        #Now check we get the right events back, in the order of first forthcoming occurrence
        all_events_from_monday = BroadcastEvent.objects.between(start_date, end_date)
        self.assertEqual(list(all_events_from_monday), [gardeners_question_time, gardeners_answer_time])
        
        all_events_from_wednesday = BroadcastEvent.objects.between(start_date+timedelta(2), end_date)
        self.assertEqual(list(all_events_from_wednesday), [gardeners_answer_time, gardeners_question_time])
        
        studio1_events = BroadcastEvent.objects.filter(studio=1).between(start_date+timedelta(2), end_date)
        self.assertEqual(list(studio1_events), [gardeners_answer_time, ])
        
        

    def test_between_ranges(self):
        
        weekly = Rule.objects.create(name="weekly", frequency="WEEKLY")
        
        start_date = date(2010, 03, 1) #it's a monday
        end_date = start_date+timedelta(28) # it's a monday (the 29th)
        
        world_cup_match = BroadcastEvent.objects.create(presenter = "Jimmy McNarrator", studio=1)  
        gardeners_question_time = BroadcastEvent.objects.create(presenter = "Jim Appleface", studio=2)
        
        #starting before, ending within
        world_cup_match.create_generator(
            first_start_date=start_date-timedelta(7),
            first_start_time=time(10,00),
            first_end_time=time(12,00),
            rule=weekly,
            repeat_until=start_date+timedelta(7),
        )
        
        self.assertEqual(len(BroadcastEventOccurrenceGenerator.objects.occurrences_between(start_date, end_date)), 2)
        
        #starting within, ending after
        gardeners_question_time.create_generator(
            first_start_date=start_date+timedelta(7),
            first_start_time=time(10,00),
            first_end_time=time(12,00),
            rule=weekly,
            repeat_until=end_date+timedelta(7),
        )
        
        self.assertEqual(len(BroadcastEventOccurrenceGenerator.objects.occurrences_between(start_date, end_date)), 6)
        self.assertEqual(len(gardeners_question_time.generators.occurrences_between(start_date, end_date)), 4)
        
        #Now continue with the combinations of overlaps. We'll remove all generators inbetween.
        
        def _make_combo(first_start_date, repeat_until=None, rule=None):
            return gardeners_question_time.create_generator(
                first_start_date=first_start_date,
                first_start_time=time(10,00),
                first_end_time=time(12,00),
                rule=rule,
                repeat_until=repeat_until,
            )
        
        def _test_combo(result, first_start_date, repeat_until=None, rule=weekly):
            gardeners_question_time.generators.all().delete()
            _make_combo(first_start_date, repeat_until, rule)
            self.assertEqual(len(gardeners_question_time.generators.occurrences_between(start_date, end_date)), result)


        #both within
        _test_combo(
            first_start_date = start_date+timedelta(7),
            repeat_until= end_date-timedelta(7),
            result=3
        )

        #start before, end after
        _test_combo(
            first_start_date=start_date-timedelta(7),
            repeat_until=end_date+timedelta(7),
            result=5
        )

        #start before, end before
        _test_combo(
            first_start_date=start_date-timedelta(14),
            repeat_until=start_date-timedelta(7),
            result=0
        )

        #start after, end after
        _test_combo(
            first_start_date=end_date+timedelta(7),
            repeat_until=end_date+timedelta(14),
            result=0
        )

        #start before, end on start date
        _test_combo(
            first_start_date=start_date-timedelta(7),
            repeat_until=start_date,
            result=1
        )

        #start on end date, end after
        _test_combo(
            first_start_date=end_date,
            repeat_until=end_date + timedelta(7),
            result=1
        )
 
         #start on start date, end on end date
        _test_combo(
            first_start_date=start_date,
            repeat_until=end_date,
            result=5
        )
        
        #start before start date, no end
        _test_combo(
            first_start_date=start_date - timedelta(7),
            result=5
        )

        #start on start date, no end
        _test_combo(
            first_start_date=start_date,
            result=5
        )

        #start within, no end
        _test_combo(
            first_start_date=start_date + timedelta(7),
            result=4
        )
        #start on end date, no end
        _test_combo(
            first_start_date=end_date,
            result=1
        )

        #start after end date, no end
        _test_combo(
            first_start_date=end_date + timedelta(7),
            result=0
        )

        #start before, no repetition
        _test_combo(
            first_start_date=start_date - timedelta(7),
            rule=None,
            result=0
        )

        #start on start date, no repetition
        _test_combo(
            first_start_date=start_date,
            rule=None,
            result=1
        )

        #start within, no repetition
        _test_combo(
            first_start_date=start_date + timedelta(7),
            rule=None,
            result=1
        )

        #start on end date, no repetition
        _test_combo(
            first_start_date=end_date,
            rule=None,
            result=1
        )

        #start after end date, no repetition
        _test_combo(
            first_start_date=end_date + timedelta(7),
            rule=None,
            result=0
        )
