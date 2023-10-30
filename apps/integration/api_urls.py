from django.urls import path

from apps.integration.api_views import SaveHolidayDataView, SaveSpotDataView

urlpatterns = [
    path(
        "save_spot_data",
        SaveSpotDataView.as_view(),
        name="save_spot_data",
    ),
    path("save_holiday_data", SaveHolidayDataView.as_view(), name="save_holiday_data"),
]
