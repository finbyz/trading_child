from django.urls import include, path

from apps.integration.views import PCRView

urlpatterns = [
    path(
        "pcr/<str:option_instrument>/<str:websocket_id>",
        PCRView.as_view(),
        name="pcr",
    )
]
