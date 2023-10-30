import datetime as dt

from django.utils import timezone

from apps.integration.models import Holiday as HolidayModel


def get_weekends(year):
    d = dt.date(year, 1, 1)  # January 1st
    d += dt.timedelta(days=6 - d.weekday())  # First Sunday
    while d.year == year:
        yield d
        d += dt.timedelta(days=7)


def update_weekend_of_year(self):
    for d in get_weekends(timezone.localdate().year):
        saturday = d - dt.timedelta(days=1)
        sunday = d

        if not HolidayModel.objects.filter(date=saturday).exists():
            HolidayModel.objects.create(date=saturday)

        if not HolidayModel.objects.filter(date=sunday).exists():
            HolidayModel.objects.create(date=sunday)
