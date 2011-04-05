from django.forms import ModelForm
from .models import LectureEvent, LectureEventOccurrence, LectureEventOccurrenceGenerator


class LectureEventForm(ModelForm):
    class Meta:
        model = LectureEvent

class LectureEventOccurrenceForm(ModelForm):
    class Meta:
        model = LectureEventOccurrence

class LectureEventOccurrenceGeneratorForm(ModelForm):
    class Meta:
        model = LectureEventOccurrenceGenerator
