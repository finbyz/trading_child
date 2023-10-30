import traceback

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.core.validators import MinLengthValidator
from django.db import models

from apps.integration.utils.broker_login import KiteLoginApi, KotakNeoLoginApi
from apps.master.tasks import send_telegram_message_task
from apps.master.utils import decrypt_message, encrypt_message

EXCHANGE_CHOICES = (
    ("NSE", "NSE"),
    ("BSE", "BSE"),
    ("MCX", "MCX"),
)

BROKER_CHOICES = (
    ("dummy", "Dummy"),
    ("kotak_neo", "Kotak Neo"),
    ("kite", "Kite Zerodha Bypass"),
)

User = get_user_model()


class Spot(models.Model):
    symbol = models.CharField(max_length=20)
    kite_token = models.IntegerField(null=True, blank=True)
    exchange = models.CharField(
        max_length=5,
        choices=EXCHANGE_CHOICES,
        default=EXCHANGE_CHOICES[0][0],
    )
    is_active = models.BooleanField(default=True)
    is_tradable = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["symbol", "exchange"],
                name="symbol_exchange",
            ),
        ]

    def __str__(self) -> str:
        return self.symbol


class Holiday(models.Model):
    date = models.DateField()
    exchange = models.CharField(
        max_length=5,
        choices=EXCHANGE_CHOICES,
        default=EXCHANGE_CHOICES[0][0],
    )
    is_half_day = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["date", "exchange"],
                name="date_exchange",
            ),
        ]
        verbose_name_plural = "Holidays"

    def __str__(self):
        return self.date.strftime("%Y-%m-%d")


class BrokerApi(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="broker_apis")
    broker = models.CharField(
        max_length=30,
        choices=BROKER_CHOICES,
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "broker"],
                name="user_broker",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user} - {self.get_broker_display()}"


class KotakNeoApi(models.Model):
    broker_api = models.OneToOneField(
        BrokerApi,
        related_name="kotak_neo_api",
        on_delete=models.CASCADE,
    )
    mobile_number = models.CharField(max_length=13, validators=[MinLengthValidator(13)])
    pan_number = models.CharField(
        max_length=10, null=True, blank=True, validators=[MinLengthValidator(10)]
    )
    password = models.CharField(max_length=255)
    mpin = models.CharField(max_length=255)
    neo_fin_key = models.CharField(max_length=255)
    consumer_key = models.CharField(max_length=255)
    consumer_secret = models.CharField(max_length=255)
    access_token = models.TextField(blank=True, null=True)
    auth = models.TextField(blank=True, null=True)
    sid = models.CharField(max_length=100, blank=True, null=True)
    rid = models.CharField(max_length=100, blank=True, null=True)
    hs_server_id = models.CharField(max_length=100, blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    error_traceback = models.TextField(blank=True, null=True)
    generate_access_token = models.BooleanField(default=False)
    update_auth_token = models.BooleanField(default=False)
    login_error = models.BooleanField(default=False)
    update_error = models.BooleanField(default=False)
    update_token_error = models.BooleanField(default=False)

    def __str__(self) -> str:
        return f"{self.broker_api.user}"

    # Password Encryption And Decryption
    def encrypt_password(self):
        try:
            decrypt_message(self.password)
        except Exception:
            self.password = encrypt_message(self.password)

    def decrypt_password(self):
        return decrypt_message(str(self.password))

    # Mpin Encryption And Decryption
    def encrypt_mpin(self):
        try:
            decrypt_message(str(self.mpin))
        except Exception:
            self.mpin = encrypt_message(self.mpin)

    def decrypt_mpin(self):
        return decrypt_message(str(self.mpin))

    # Consumer Key Encryption And Decryption
    def encrypt_consumer_key(self):
        try:
            decrypt_message(str(self.consumer_key))
        except Exception:
            self.consumer_key = encrypt_message(self.consumer_key)

    def decrypt_consumer_key(self):
        return decrypt_message(str(self.consumer_key))

    # Consumer Secret Encryption And Decryption
    def encrypt_consumer_secret(self):
        try:
            decrypt_message(str(self.consumer_secret))
        except Exception:
            self.consumer_secret = encrypt_message(self.consumer_secret)

    def decrypt_consumer_secret(self):
        return decrypt_message(str(self.consumer_secret))

    def kotak_neo_login(self):
        knapi = KotakNeoLoginApi(
            neo_fin_key=self.neo_fin_key,
            consumer_key=self.decrypt_consumer_key(),
            consumer_secret=self.decrypt_consumer_secret(),
            access_token=self.access_token,
        )
        async_to_sync(knapi.login)(
            mobile_number=self.mobile_number,
            pan_number=self.pan_number,
            password=self.decrypt_password(),
            mpin=self.decrypt_mpin(),
            generate_access_token=self.generate_access_token,
        )

        self.generate_access_token = False
        self.access_token = knapi.access_token
        self.sid = knapi.sid
        self.rid = knapi.rid
        self.auth = knapi.auth
        self.hs_server_id = knapi.hs_server_id

        self.set_success_params()

    def login(self):
        try:
            self.kotak_neo_login()
        except Exception as e:
            self.login_error = self.set_error_message(e)

    def kotak_neo_update_auth_token(self):
        knapi = KotakNeoLoginApi(
            neo_fin_key=self.neo_fin_key,
            consumer_key=self.decrypt_consumer_key(),
            consumer_secret=self.decrypt_consumer_secret(),
            access_token=self.access_token,
        )
        async_to_sync(knapi.update_auth_token)(
            auth=self.auth,
            sid=self.sid,
            rid=self.rid,
            hs_server_id=self.hs_server_id,
        )

        self.auth = knapi.auth

        self.set_success_params()

    def set_success_params(self):
        self.update_auth_token = False
        self.login_error = False
        self.update_token_error = False
        self.update_error = False

    def auth_token_update(self):
        try:
            self.kotak_neo_update_auth_token()
        except Exception as e:
            self.update_token_error = self.set_error_message(e)

    def set_error_message(self, e):
        self.error_message = str(e)
        self.error_traceback = str(traceback.format_exc())
        send_telegram_message_task.delay(
            f"{self.broker_api.user.username}\n\n{self.error_message}\n\n{self.error_traceback}"
        )
        return True

    def save(self, *args, **kwargs) -> None:
        self.error_message = None
        self.error_traceback = None
        self.encrypt_password()
        self.encrypt_mpin()
        self.encrypt_consumer_key()
        self.encrypt_consumer_secret()
        if self.generate_access_token or not self.update_auth_token:
            self.login()
        else:
            self.auth_token_update()
        super(KotakNeoApi, self).save(*args, **kwargs)


class KiteApi(models.Model):
    broker_api = models.OneToOneField(
        BrokerApi,
        related_name="kite_api",
        on_delete=models.CASCADE,
    )
    user_id = models.CharField(max_length=20)
    password = models.CharField(max_length=255, blank=True, null=True)
    twofa = models.CharField(max_length=255, blank=True, null=True)
    enctoken = models.CharField(max_length=255, blank=True, null=True)
    login_error = models.BooleanField(default=False)
    error_message = models.TextField(blank=True, null=True)
    error_traceback = models.TextField(blank=True, null=True)

    def __str__(self) -> str:
        return f"{self.broker_api.user}"

    def encrypt_password(self):
        try:
            decrypt_message(self.password)
        except Exception:
            self.password = encrypt_message(self.password)

    def decrypt_password(self):
        return decrypt_message(str(self.password))

    def encrypt_twofa(self):
        try:
            decrypt_message(self.twofa)
        except Exception:
            self.twofa = encrypt_message(self.twofa)

    def decrypt_twofa(self):
        return decrypt_message(str(self.twofa))

    def login(self):
        try:
            kite_login_api = KiteLoginApi(user_id=self.user_id)
            async_to_sync(kite_login_api.login)(
                password=self.decrypt_password(),
                twofa=self.decrypt_twofa(),
            )
            self.enctoken = kite_login_api.enctoken
            self.error_message = None
            self.error_traceback = None
            self.login_error = False
        except Exception as e:
            self.login_error = self.set_error_message(e)

    def set_error_message(self, e):
        self.error_message = str(e)
        self.error_traceback = str(traceback.format_exc())
        send_telegram_message_task.delay(
            f"{self.broker_api.user.username}\n\n{self.error_message}\n\n{self.error_traceback}"
        )
        return True

    def save(self, *args, **kwargs) -> None:
        self.encrypt_password()
        self.encrypt_twofa()
        self.login()
        super(KiteApi, self).save(*args, **kwargs)


class InitialMargin(models.Model):
    broker_api = models.ForeignKey(BrokerApi, on_delete=models.CASCADE)
    date = models.DateField()
    margin = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.broker_api} - {self.date}"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["broker_api", "date"],
                name="broker_api_date",
            ),
        ]
