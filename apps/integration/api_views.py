from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.integration.models import Holiday as HolidayModel
from apps.integration.models import Spot as SpotModel


class SaveSpotDataView(APIView):
    authentication_classes = [SessionAuthentication, TokenAuthentication]
    permission_classes = [IsAdminUser]

    def save_spot_data(self, data):
        spot = SpotModel.objects.filter(id=data["pk"]).first()
        if not spot:
            spot = SpotModel()
            spot.id = data["pk"]

        spot.symbol = data["symbol"]
        spot.kite_token = data["kite_token"]
        spot.exchange = data["exchange"]
        spot.is_active = data["is_active"]
        spot.is_tradable = data["is_tradable"]
        spot.save()
        return Response({"response": "success"})

    def post(self, request, format=None):
        return self.save_spot_data(request.data)

    def put(self, request, format=None):
        return self.save_spot_data(request.data)


class SaveHolidayDataView(APIView):
    authentication_classes = [SessionAuthentication, TokenAuthentication]
    permission_classes = [IsAdminUser]

    def save_holiday_data(self, data):
        spot = HolidayModel.objects.filter(id=data["pk"]).first()
        if not spot:
            spot = HolidayModel()
            spot.id = data["pk"]

        spot.date = data["date"]
        spot.exchange = data["exchange"]
        spot.save()

        return Response({"response": "success"})

    def post(self, request, format=None):
        return self.save_holiday_data(request.data)

    def put(self, request, format=None):
        return self.save_holiday_data(request.data)
