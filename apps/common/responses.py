from rest_framework.response import Response


def success_response(data=None, message="OK", status=200):
    payload = {"success": True, "message": message}
    if data is not None:
        payload["data"] = data
    return Response(payload, status=status)


def error_response(error, message, details=None, status=400):
    return Response(
        {
            "success": False,
            "error": error,
            "message": message,
            "details": details or {},
        },
        status=status,
    )
