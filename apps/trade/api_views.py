from asgiref.sync import async_to_sync
from django.core.cache import cache
from django_pandas.io import read_frame
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.integration.models import Spot as SpotModel
from apps.trade.deploy_strategy import (
    place_entry_order,
    place_exit_order,
    update_strategy_quantity,
    update_strategy_quantity_percentage,
    users_entry_delta_management_strategy,
    users_entry_single_straddle_strangle,
    users_exit_delta_management_strategy,
    users_exit_single_straddle_strangle,
)
from apps.trade.models import DailyPnl as DailyPnlModel
from apps.trade.models import DeployedOptionStrategy as DeployedOptionStrategyModel
from apps.trade.models import (
    DeployedOptionStrategyParameters as DeployedOptionStrategyParametersModel,
)
from apps.trade.models import OptionStrategy as OptionStrategyModel
from apps.trade.tasks import adjust_positions_task, update_positions_task


class UpdatePosition(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, format=None):
        row = request.data
        broker = row["broker"]
        update_positions_task(broker=broker)
        return Response({"message": "success"})


class AdjustPosition(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, format=None):
        row = request.data
        strategy = row["strategy"]

        opt_strategy = DeployedOptionStrategyModel.objects.filter(pk=strategy).first()

        adjust_positions_task(
            symbol=opt_strategy.instrument.symbol,
            broker=opt_strategy.broker,
            websocket_ids=opt_strategy.websocket_ids.split(","),
        )

        return Response({"message": "success"})


class EnterUsersAlgo(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, format=None):
        row = request.data

        strategy = row["strategy"]
        opt_strategy = DeployedOptionStrategyModel.objects.filter(pk=strategy).first()

        if opt_strategy.strategy.strategy_type == "delta_management":
            data = row["data"]

            async_to_sync(users_entry_delta_management_strategy)(
                opt_strategy.strategy_name, data
            )
        elif opt_strategy.strategy.strategy_type == "single_straddle_strangle":
            data = row["data"]

            async_to_sync(users_entry_single_straddle_strangle)(
                opt_strategy.strategy_name, data
            )

        return Response({"message": "success"})


class ExitUsersAlgo(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, format=None):
        row = request.data

        strategy = row["strategy"]
        opt_strategy = DeployedOptionStrategyModel.objects.filter(pk=strategy).first()

        if opt_strategy.strategy.strategy_type == "delta_management":
            data = row["data"]

            async_to_sync(users_exit_delta_management_strategy)(
                opt_strategy.strategy_name, data
            )
        elif opt_strategy.strategy.strategy_type == "single_straddle_strangle":
            data = row["data"]

            async_to_sync(users_exit_single_straddle_strangle)(
                opt_strategy.strategy_name, data
            )

        return Response({"message": "success"})


class UpdateStrategyQuantityPercentage(APIView):
    def post(self, request, format=None):
        row = request.data

        strategy = row["strategy"]
        opt_strategy = DeployedOptionStrategyModel.objects.filter(pk=strategy).first()

        if opt_strategy.strategy.strategy_type in [
            "delta_management",
            "single_straddle_strangle",
        ]:
            qty_percentage = row["qty_percentage"]

            async_to_sync(update_strategy_quantity_percentage)(
                opt_strategy.strategy_name, qty_percentage
            )

        return Response({"message": "success"})


class UpdateStrategyQuantity(APIView):
    def post(self, request, format=None):
        row = request.data

        strategy = row["strategy"]
        opt_strategy = DeployedOptionStrategyModel.objects.filter(pk=strategy).first()

        if opt_strategy.strategy.strategy_type in [
            "delta_management",
            "single_straddle_strangle",
        ]:
            username = row["username"]
            broker = row["broker"]
            qty = row["qty"]

            async_to_sync(update_strategy_quantity)(
                opt_strategy.strategy_name, username, broker, qty
            )

        return Response({"message": "success"})


class DailyPnlApi(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, format=None):
        row = request.data
        df = read_frame(
            DailyPnlModel.objects.filter(
                broker_api__user__username=row["username"],
                date__gte=row["from_date"],
                date__lte=row["to_date"],
            ).order_by("date"),
            fieldnames=[
                "broker_api__user__username",
                "broker_api__broker",
                "date",
                "gross_pnl",
                "charges",
                "net_pnl",
                "initial_margin",
                "net_percentage",
            ],
        )
        df = df.rename(
            columns={
                "broker_api__user__username": "username",
                "broker_api__broker": "broker",
            }
        )
        df["date"] = df["date"].astype(str)
        df = df.fillna(0)
        return Response({"message": "success", "data": df.to_dict("records")})


class SaveOptionStrategiesView(APIView):
    authentication_classes = [SessionAuthentication, TokenAuthentication]
    permission_classes = [IsAdminUser]

    def save_option_strategies(self, data):
        option_strategy = OptionStrategyModel.objects.filter(id=data["pk"]).first()

        if not option_strategy:
            option_strategy = OptionStrategyModel()
            option_strategy.id = data["pk"]

        option_strategy.name = data["name"]
        option_strategy.file_name = data["file_name"]
        option_strategy.strategy_type = data["strategy_type"]
        option_strategy.save()

        return Response({"message": "success"})

    def post(self, request, format=None):
        return self.save_option_strategies(request.data)

    def put(self, request, format=None):
        return self.save_option_strategies(request.data)


class SaveDeployedOptionStrategyView(APIView):
    authentication_classes = [SessionAuthentication, TokenAuthentication]
    permission_classes = [IsAdminUser]

    def save_deployed_option_strategy(self, data):
        deployed_option_strategy = DeployedOptionStrategyModel.objects.filter(
            id=data["pk"]
        ).first()

        if not deployed_option_strategy:
            deployed_option_strategy = DeployedOptionStrategyModel()
            deployed_option_strategy.id = data["pk"]

        deployed_option_strategy.strategy_name = data["strategy_name"]
        deployed_option_strategy.strategy = OptionStrategyModel.objects.get(
            pk=data["strategy_id"]
        )
        deployed_option_strategy.instrument = SpotModel.objects.get(
            pk=data["instrument_id"]
        )
        deployed_option_strategy.lot_size = data["lot_size"]
        deployed_option_strategy.options = data["options"]
        deployed_option_strategy.broker = data["broker"]
        deployed_option_strategy.strategy_type = data["strategy_type"]
        if data["hedge_strategy_id"]:
            deployed_option_strategy.hedge_strategy = (
                DeployedOptionStrategyModel.objects.get(pk=data["hedge_strategy_id"])
            )
        else:
            deployed_option_strategy.hedge_strategy = None
        deployed_option_strategy.websocket_ids = data["websocket_ids"]
        deployed_option_strategy.slippage = data["slippage"]
        deployed_option_strategy.is_active = data["is_active"]
        deployed_option_strategy.is_hedge = data["is_hedge"]
        deployed_option_strategy.save()

        deployed_option_strategy.parameters.all().delete()

        for parameter in data["parameters"]:
            deployed_option_strategy_parameter = DeployedOptionStrategyParametersModel()
            deployed_option_strategy_parameter.parent = deployed_option_strategy
            deployed_option_strategy_parameter.pk = parameter["pk"]
            deployed_option_strategy_parameter.name = parameter["name"]
            deployed_option_strategy_parameter.parameters = parameter["parameters"]
            deployed_option_strategy_parameter.is_active = parameter["is_active"]
            deployed_option_strategy_parameter.save()

        return Response({"message": "success"})

    def post(self, request, format=None):
        return self.save_deployed_option_strategy(request.data)

    def put(self, request, format=None):
        return self.save_deployed_option_strategy(request.data)


class StartAlgoView(APIView):
    authentication_classes = [SessionAuthentication, TokenAuthentication]
    permission_classes = [IsAdminUser]

    def post(self, request, format=None):
        row = request.data

        opt_strategy = DeployedOptionStrategyModel.objects.filter(pk=row["pk"]).first()

        if opt_strategy.strategy.strategy_type in [
            "single_straddle_strangle",
            "delta_management",
        ]:
            async_to_sync(place_entry_order)(
                opt_strategy.strategy_name, row["tradingsymbols"]
            )

        return Response({"message": "success"})


class ExitAlgoView(APIView):
    authentication_classes = [SessionAuthentication, TokenAuthentication]
    permission_classes = [IsAdminUser]

    def post(self, request, format=None):
        row = request.data

        opt_strategy = DeployedOptionStrategyModel.objects.filter(pk=row["pk"]).first()

        if opt_strategy.strategy.strategy_type in [
            "single_straddle_strangle",
            "delta_management",
        ]:
            async_to_sync(place_exit_order)(opt_strategy.strategy_name)

        return Response({"message": "success"})


class UpdateTradingSymbolsView(APIView):
    authentication_classes = [SessionAuthentication, TokenAuthentication]
    permission_classes = [IsAdminUser]

    def post(self, request, format=None):
        row = request.data
        opt_strategy = DeployedOptionStrategyModel.objects.filter(pk=row["pk"]).first()
        cache.set(f"TRADINGSYMBOLS_{row['pk']}", row["tradingsymbols"])

        adjust_positions_task(
            symbol=opt_strategy.instrument.symbol,
            broker=opt_strategy.broker,
            websocket_ids=opt_strategy.websocket_ids.split(","),
        )
