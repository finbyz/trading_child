from django.urls import path

from apps.master.api_views import RevokeTask
from apps.master.views import CeleryTaskView, HomeView, login_page, logout_page

urlpatterns = [
    path("login/", login_page, name="login"),
    path("logout/", logout_page, name="logout"),
    path("", HomeView.as_view(), name="home"),
    path("celery_task/", CeleryTaskView.as_view(), name="celery_task"),
    path("api/revoke_task/", RevokeTask.as_view(), name="revoke_task"),
]
