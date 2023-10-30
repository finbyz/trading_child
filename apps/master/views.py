from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView
from django.views.generic.base import ContextMixin
from django.views.generic.list import ListView

from apps.trade.views import NavView

User = get_user_model()


def login_page(request):
    if request.user.is_authenticated:
        return redirect("master:home")

    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect("master:home")
        else:
            messages.info(request, "Try again! username or password is incorrect")

    context = {"title": "Login"}

    return render(request, "login.html", context)


@login_required()
def logout_page(request):
    if request.user.is_authenticated:
        logout(request)
    return redirect("master:home")


@method_decorator(login_required, name="dispatch")
class HomeView(NavView, TemplateView):
    template_name: str = "home.html"

    def get_context_data(self, *args, **kwargs):
        context = super(HomeView, self).get_context_data(*args, **kwargs)
        context[
            "title"
        ] = f"Home | {context['user'].first_name} {context['user'].last_name}"
        return context


@method_decorator(login_required, name="dispatch")
class CeleryTaskView(NavView, TemplateView):
    template_name: str = "celery_task.html"

    def get_context_data(self, *args, **kwargs):
        context = super(CeleryTaskView, self).get_context_data(*args, **kwargs)
        context["title"] = "Celery Tasks"
        return context
