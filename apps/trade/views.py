import json

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView
from django.views.generic.base import ContextMixin
from django.views.generic.detail import DetailView

from apps.integration.models import BrokerApi as BrokerApiModel
from apps.trade.models import DeployedOptionStrategy as DeployedOptionStrategyModel
from trading.settings import UNDERLYINGS, WEBSOCKET_IDS

User = get_user_model()


class NavView(ContextMixin):
    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context["dynamic_backtest_link"] = DeployedOptionStrategyModel.objects.filter(
            is_active=True
        )
        context["pcr_view_navbar"] = [
            (websocket_id, underlying)
            for websocket_id in WEBSOCKET_IDS
            for underlying in UNDERLYINGS
        ]
        context["user"] = self.request.user
        return context


@method_decorator(login_required, name="dispatch")
class DeployeOptionStrategyDetailView(NavView, DetailView):
    model = DeployedOptionStrategyModel

    def get_context_data(self, *args, **kwargs):
        context = super(DeployeOptionStrategyDetailView, self).get_context_data(
            *args, **kwargs
        )
        deployed_option_strategy: DeployedOptionStrategyModel = context["object"]
        strategy_type = deployed_option_strategy.strategy.strategy_type
        context["title"] = context["object"].strategy_name
        context["broker"] = deployed_option_strategy.broker

        if strategy_type == "delta_management":
            self.template_name: str = "deployed_strategy_detail_view.html"
        elif strategy_type == "single_straddle_strangle":
            self.template_name: str = "single_straddle_strangle.html"
        return context


@method_decorator(login_required, name="dispatch")
class DailyPnl(NavView, TemplateView):
    template_name: str = "daily_pnl.html"

    def get_context_data(self, *args, **kwargs):
        context = super(DailyPnl, self).get_context_data(*args, **kwargs)
        context["title"] = "User PNL"
        context["user_list"] = sorted(
            [
                broker_api.user.username
                for broker_api in BrokerApiModel.objects.filter(
                    is_active=True, broker__in=["kotak_neo"]
                ).distinct("user")
            ]
        )
        return context
