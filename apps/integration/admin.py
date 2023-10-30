from typing import Any

from django.contrib import admin
from django.http.request import HttpRequest
from import_export.admin import ImportExportModelAdmin

from apps.integration.models import BrokerApi as BrokerApiModel
from apps.integration.models import Holiday as HolidayModel
from apps.integration.models import InitialMargin as InitialMarginModel
from apps.integration.models import KiteApi as KiteApiModel
from apps.integration.models import KotakNeoApi as KotakNeoApiModel
from apps.integration.models import Spot as SpotModel


class SpotAdmin(admin.ModelAdmin):
    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(
        self,
        request: HttpRequest,
        obj: SpotModel = None,
    ) -> bool:
        return False

    def has_change_permission(
        self,
        request: HttpRequest,
        obj: SpotModel = None,
    ) -> bool:
        return False


class HolidayAdmin(admin.ModelAdmin):
    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(
        self,
        request: HttpRequest,
        obj: HolidayModel = None,
    ) -> bool:
        return False

    def has_change_permission(
        self,
        request: HttpRequest,
        obj: HolidayModel = None,
    ) -> bool:
        return False


class BrokerApiAdmin(admin.ModelAdmin):
    pass


class KotakNeoApiAdmin(admin.ModelAdmin):
    list_display: tuple = (
        "get_user",
        "mobile_number",
        "pan_number",
        "login_error",
        "update_token_error",
    )

    fieldsets: tuple = (
        (
            "Details",
            {
                "fields": (
                    "broker_api",
                    (
                        "mobile_number",
                        "pan_number",
                        "password",
                        "mpin",
                    ),
                    (
                        "neo_fin_key",
                        "consumer_secret",
                        "consumer_key",
                    ),
                ),
            },
        ),
        (
            "Generated Details",
            {
                "fields": (
                    (
                        "access_token",
                        "auth",
                    ),
                    (
                        "hs_server_id",
                        "sid",
                        "rid",
                    ),
                )
            },
        ),
        (
            "Action",
            {
                "fields": (
                    (
                        "generate_access_token",
                        "update_auth_token",
                    ),
                ),
            },
        ),
        (
            "Errors",
            {
                "fields": (
                    (
                        "login_error",
                        "update_token_error",
                    ),
                    (
                        "error_message",
                        "error_traceback",
                    ),
                ),
            },
        ),
    )

    readonly_fields: tuple = (
        "access_token",
        "auth",
        "hs_server_id",
        "sid",
        "rid",
        "login_error",
        "update_token_error",
        "error_message",
        "error_traceback",
    )

    @admin.display(ordering="broker_api__user", description="User")
    def get_user(self, obj: KotakNeoApiModel):
        return obj.broker_api.user

    def get_form(self, request, obj=None, **kwargs) -> Any:
        form = super(KotakNeoApiAdmin, self).get_form(request, obj, **kwargs)
        form.base_fields["broker_api"].queryset = BrokerApiModel.objects.filter(
            broker__iexact="kotak_neo"
        )
        return form


class KiteApiAdmin(admin.ModelAdmin):
    list_display: tuple = (
        "get_user",
        "user_id",
    )

    readonly_fields: tuple = (
        "enctoken",
        "login_error",
        "error_message",
        "error_traceback",
    )

    @admin.display(ordering="broker_api__user", description="User")
    def get_user(self, obj: KiteApiModel):
        return obj.broker_api.user

    def get_form(self, request, obj=None, **kwargs) -> Any:
        form: Any = super(KiteApiAdmin, self).get_form(request, obj, **kwargs)
        form.base_fields["broker_api"].queryset = BrokerApiModel.objects.filter(
            broker__iexact="kite"
        )
        return form


class InitialMarginAdmin(admin.ModelAdmin):
    pass


admin.site.register(BrokerApiModel, BrokerApiAdmin)
admin.site.register(KotakNeoApiModel, KotakNeoApiAdmin)
admin.site.register(KiteApiModel, KiteApiAdmin)
admin.site.register(HolidayModel, HolidayAdmin)
admin.site.register(SpotModel, SpotAdmin)
admin.site.register(InitialMarginModel, InitialMarginAdmin)
