from celery.result import AsyncResult
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView


class GetKiteApiCred(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, format=None)

    def post(self, request, format=None):
        row = request.data
        AsyncResult(row["id"]).revoke(terminate=True, signal="SIGKILL")
        return Response({"message": "success"})
