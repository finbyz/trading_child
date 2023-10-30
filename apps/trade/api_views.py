from asgiref.sync import async_to_sync
from django_pandas.io import read_frame
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.trade.deploy_strategy import (
    entry_straddle_strangle,
    exit_one_side_delta_management_strategy,
    exit_straddle_strangle,
    one_side_exit_hold_delta_management_strategy,
    rebalance_delta_management_strategy,
    reentry_one_side_delta_management_strategy,
    release_one_side_exit_hold_delta_management_strategy,
    shift_single_strike_delta_management_strategy,
    update_strategy_quantity,
    update_strategy_quantity_percentage,
    users_entry_delta_management_strategy,
    users_entry_single_straddle_strangle,
    users_exit_delta_management_strategy,
    users_exit_single_straddle_strangle,
)
from apps.trade.models import DailyPnl as DailyPnlModel
from apps.trade.models import DeployedOptionStrategy as DeployedOptionStrategyModel
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


class StartAlgo(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, format=None):
        row = request.data

        strategy = row["strategy"]
        opt_strategy = DeployedOptionStrategyModel.objects.filter(pk=strategy).first()

        if opt_strategy.strategy.strategy_type == "single_straddle_strangle":
            async_to_sync(entry_straddle_strangle)(opt_strategy.strategy_name)

        return Response({"message": "success"})


class ExitAlgo(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, format=None):
        row = request.data

        strategy = row["strategy"]
        opt_strategy = DeployedOptionStrategyModel.objects.filter(pk=strategy).first()

        if opt_strategy.strategy.strategy_type == "single_straddle_strangle":
            async_to_sync(exit_straddle_strangle)(opt_strategy.strategy_name)

        return Response({"message": "success"})


class RebalanceView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, format=None):
        row = request.data

        strategy = row["strategy"]
        opt_strategy = DeployedOptionStrategyModel.objects.filter(pk=strategy).first()

        if opt_strategy.strategy.strategy_type == "delta_management":
            idx = int(row["index"])

            async_to_sync(rebalance_delta_management_strategy)(
                opt_strategy.strategy_name, idx
            )

        return Response({"message": "success"})


class ExitOneSide(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, format=None):
        row = request.data

        strategy = row["strategy"]
        opt_strategy = DeployedOptionStrategyModel.objects.filter(pk=strategy).first()

        if opt_strategy.strategy.strategy_type == "delta_management":
            idx = int(row["index"])
            option_type = row["option_type"]

            async_to_sync(exit_one_side_delta_management_strategy)(
                opt_strategy.strategy_name, idx, option_type
            )

        return Response({"message": "success"})


class ReentryOneSide(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, format=None):
        row = request.data

        strategy = row["strategy"]
        opt_strategy = DeployedOptionStrategyModel.objects.filter(pk=strategy).first()

        if opt_strategy.strategy.strategy_type == "delta_management":
            idx = int(row["index"])

            async_to_sync(reentry_one_side_delta_management_strategy)(
                opt_strategy.strategy_name, idx
            )

        return Response({"message": "success"})


class ShiftSingleStrike(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, format=None):
        row = request.data

        strategy = row["strategy"]
        opt_strategy = DeployedOptionStrategyModel.objects.filter(pk=strategy).first()

        if opt_strategy.strategy.strategy_type == "delta_management":
            idx = int(row["index"])
            option_type = row["option_type"]
            points = row["points"]

            async_to_sync(shift_single_strike_delta_management_strategy)(
                opt_strategy.strategy_name, idx, option_type, points
            )

        return Response({"message": "success"})


class OneSideExitHold(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, format=None):
        row = request.data

        strategy = row["strategy"]
        opt_strategy = DeployedOptionStrategyModel.objects.filter(pk=strategy).first()

        if opt_strategy.strategy.strategy_type == "delta_management":
            idx = int(row["index"])

            async_to_sync(one_side_exit_hold_delta_management_strategy)(
                opt_strategy.strategy_name, idx
            )

        return Response({"message": "success"})


class ReleaseOneSideExitHold(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, format=None):
        row = request.data

        strategy = row["strategy"]
        opt_strategy = DeployedOptionStrategyModel.objects.filter(pk=strategy).first()

        if opt_strategy.strategy.strategy_type == "delta_management":
            idx = int(row["index"])

            async_to_sync(release_one_side_exit_hold_delta_management_strategy)(
                opt_strategy.strategy_name, idx
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
