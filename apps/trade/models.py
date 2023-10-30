from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse

from apps.integration.models import BROKER_CHOICES, BrokerApi, Spot

User = get_user_model()


class DummyOrder(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="dummy_orders"
    )
    tradingsymbol = models.CharField(max_length=100)
    order_id = models.CharField(max_length=100)
    order_timestamp = models.DateTimeField(null=True, blank=True)
    exchange = models.CharField(max_length=10, default="NFO")
    transaction_type = models.CharField(max_length=10)
    quantity = models.IntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    trigger_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=10, default="COMPLETE")
    tag = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self) -> str:
        return self.order_id


class OptionStrategy(models.Model):
    STRATEGY_TYPE_CHOICES = (
        ("delta_management", "Delta Management"),
        ("single_straddle_strangle", "Single Straddle or Strangle"),
    )
    name = models.CharField(max_length=100, unique=True)
    file_name = models.CharField(max_length=100, unique=True)
    strategy_type = models.CharField(
        max_length=100, choices=STRATEGY_TYPE_CHOICES, default="delta_management"
    )

    def __str__(self) -> str:
        return self.name


class DeployedOptionStrategy(models.Model):
    strategy_name = models.CharField(max_length=100, unique=True)
    strategy = models.ForeignKey(
        OptionStrategy,
        on_delete=models.CASCADE,
        related_name="deployed_option_strategies",
    )
    instrument = models.ForeignKey(
        Spot,
        on_delete=models.RESTRICT,
        related_name="deployed_option_strategies",
    )
    lot_size = models.IntegerField()
    options = models.JSONField(default=dict, null=True, blank=True)
    broker = models.CharField(
        max_length=30,
        choices=BROKER_CHOICES,
        blank=True,
        null=True,
    )
    strategy_type = models.CharField(
        max_length=5,
        default="SELL",
        choices=(
            ("SELL", "SELL"),
            ("BUY", "BUY"),
        ),
    )
    hedge_strategy = models.ForeignKey(
        "DeployedOptionStrategy",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    websocket_ids = models.CharField(max_length=25)
    slippage = models.DecimalField(max_digits=10, decimal_places=2, default=5)
    is_active = models.BooleanField(default=True)
    is_hedge = models.BooleanField(default=False)

    def get_absolute_url(self):
        return reverse(
            "trade:deployed_option_strategy_detail_view",
            kwargs={"pk": self.pk},
        )

    def __str__(self) -> str:
        return self.strategy_name

    class Meta:
        ordering = ["pk"]


class DeployedOptionStrategyUser(models.Model):
    is_cleaned = False

    parent = models.ForeignKey(
        DeployedOptionStrategy,
        on_delete=models.RESTRICT,
        related_name="users",
    )
    broker_api = models.ForeignKey(
        BrokerApi,
        on_delete=models.RESTRICT,
        related_name="deployed_option_strategy_broker_api",
    )
    alternate_broker_api = models.ForeignKey(
        BrokerApi,
        on_delete=models.RESTRICT,
        related_name="deployed_option_strategy_alternate_broker_api",
        null=True,
        blank=True,
    )
    lots = models.IntegerField()
    is_active = models.BooleanField(default=True)
    order_seq = models.PositiveIntegerField(
        default=0,
        blank=False,
        null=False,
    )

    def clean(self):
        if self.alternate_broker_api and (
            self.broker_api == self.alternate_broker_api
            or self.broker_api.broker == self.alternate_broker_api.broker
        ):
            raise ValidationError("Broker Api can not be Same as Alternate Broker Api.")

        if self.broker_api.broker not in ["dummy", self.parent.broker]:
            raise ValidationError(
                "Broker Api and Deployed Strategy Broker should be same."
            )

    def __str__(self) -> str:
        return f"{self.broker_api} - {self.lots}"

    class Meta:
        ordering = ["order_seq"]

        unique_together = (
            (
                "parent",
                "broker_api",
            ),
        )


class DeployedOptionStrategyParameters(models.Model):
    parent = models.ForeignKey(
        DeployedOptionStrategy,
        on_delete=models.CASCADE,
        related_name="parameters",
    )
    name = models.CharField(max_length=100)
    parameters = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return f"{self.parent} - {self.name}"

    class Meta:
        unique_together = (
            (
                "parent",
                "name",
            ),
        )


class Order(models.Model):
    broker_api = models.ForeignKey(
        BrokerApi,
        on_delete=models.CASCADE,
        related_name="orders",
    )
    order_id = models.CharField(max_length=25)
    tradingsymbol = models.CharField(max_length=25)
    product = models.CharField(max_length=10, default="NRML")
    status = models.CharField(max_length=100, blank=True, null=True)
    transaction_type = models.CharField(max_length=10)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    average_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    quantity = models.IntegerField()
    filled_quantity = models.IntegerField(default=0)
    pending_quantity = models.IntegerField(default=0)
    cancelled_quantity = models.IntegerField(default=0)
    order_timestamp = models.DateTimeField(null=True, blank=True)
    price_type = models.CharField(max_length=10, null=True, blank=True)
    tag = models.CharField(max_length=100, blank=True, null=True)
    trade_report = models.JSONField(default=list, null=True, blank=True)
    is_order_updated = models.BooleanField(default=False)
    trade_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self) -> str:
        return f"{self.broker_api} - {self.order_id}"

    def save(self, *args, **kwargs):
        self.trade_value = sum(
            row["average_price"] * row["filled_quantity"] for row in self.trade_report
        )
        if self.filled_quantity:
            self.average_price = self.trade_value / self.filled_quantity
        super().save(*args, **kwargs)


class DailyPnl(models.Model):
    broker_api = models.ForeignKey(
        BrokerApi, on_delete=models.RESTRICT, related_name="daily_pnl"
    )
    date = models.DateField()
    initial_margin = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    gross_pnl = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    charges = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_pnl = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_percentage = models.FloatField(default=0)

    def save(self, *args, **kwargs) -> None:
        self.net_pnl = float(self.gross_pnl) - float(self.charges)

        if float(self.initial_margin):
            self.net_percentage = float(self.net_pnl) / float(self.initial_margin)

        super(DailyPnl, self).save(*args, **kwargs)

    def __str__(self):
        return f"{self.broker_api} - {self.date}"
