from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView

from apps.trade.views import NavView


# Create your views here.
@method_decorator(login_required, name="dispatch")
class PCRView(NavView, TemplateView):
    template_name: str = "pcr.html"

    def get_context_data(self, *args, **kwargs):
        context = super(PCRView, self).get_context_data(*args, **kwargs)
        context["option_instrument"] = kwargs["option_instrument"].upper()
        context["websocket_id"] = kwargs["websocket_id"]
        context[
            "title"
        ] = f"{context['websocket_id']} - {context['option_instrument']} - PCR"
        return context
