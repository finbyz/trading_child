from typing import Any

from adminsortable2.admin import SortableAdminMixin, SortableTabularInline
from django.contrib import admin
from django.http.request import HttpRequest
from django.utils import timezone
from import_export.admin import ImportExportModelAdmin
from rangefilter.filters import DateRangeFilterBuilder

from apps.trade.models import (
    DailyPnl,
    DeployedOptionStrategy,
    DeployedOptionStrategyParameters,
    DeployedOptionStrategyUser,
    DummyOrder,
    OptionStrategy,
    Order,
)


class DeployedOptionStrategyUserAdmin(SortableTabularInline):
    model = DeployedOptionStrategyUser
    extra = 0


class DeployedOptionStrategyParametersAdmin(admin.TabularInline):
    model = DeployedOptionStrategyParameters
    extra = 0
    can_delete = False

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class OptionStrategyAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "file_name",
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(
        self,
        request: HttpRequest,
        obj: OptionStrategy = None,
    ) -> bool:
        return False

    def has_change_permission(
        self,
        request: HttpRequest,
        obj: OptionStrategy = None,
    ) -> bool:
        return False


class DeployedOptionStrategyAdmin(SortableAdminMixin, admin.ModelAdmin):
    save_as = True
    list_display = (
        "strategy_name",
        "strategy",
        "is_active",
    )

    readonly_fields = (
        "strategy_name",
        "strategy",
        "instrument",
        "lot_size",
        "options",
        "broker",
        "strategy_type",
        "hedge_strategy",
        "websocket_ids",
        "slippage",
        "is_active",
        "is_hedge",
    )

    inlines = (
        DeployedOptionStrategyParametersAdmin,
        DeployedOptionStrategyUserAdmin,
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(
        self, request: HttpRequest, obj: Any | None = ...
    ) -> bool:
        return False


class DummyOrderAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = (
        "__str__",
        "tradingsymbol",
        "order_timestamp",
        "transaction_type",
        "quantity",
        "price",
    )
    list_filter = ("user",)


class OrderAdmin(ImportExportModelAdmin):
    list_display = (
        "order_id",
        "broker_api",
        "tradingsymbol",
        "order_timestamp",
        "transaction_type",
        "quantity",
        "price",
        "average_price",
    )
    list_filter = (
        "broker_api__user__username",
        "status",
        (
            "order_timestamp",
            DateRangeFilterBuilder(
                title="Order Timestamp",
                default_start=timezone.localdate(),
                default_end=timezone.localdate(),
            ),
        ),
    )


class DailyPnlAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    save_as = True
    list_display = (
        "__str__",
        "date",
        "initial_margin",
        "gross_pnl",
        "charges",
        "net_pnl",
    )

    list_filter = (
        "broker_api__user",
        (
            "date",
            DateRangeFilterBuilder(
                title="Date",
                default_start=timezone.localdate(),
                default_end=timezone.localdate(),
            ),
        ),
    )


admin.site.register(DummyOrder, DummyOrderAdmin)
admin.site.register(OptionStrategy, OptionStrategyAdmin)
admin.site.register(DeployedOptionStrategy, DeployedOptionStrategyAdmin)
admin.site.register(Order, OrderAdmin)
admin.site.register(DailyPnl, DailyPnlAdmin)
