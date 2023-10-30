from celery.result import AsyncResult
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


class RevokeTask(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, format=None):
        row = request.data
        AsyncResult(row["id"]).revoke(terminate=True, signal="SIGKILL")
        return Response({"message": "success"})
