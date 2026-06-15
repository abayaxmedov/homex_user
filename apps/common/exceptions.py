from rest_framework.views import exception_handler


def homex_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None

    detail = response.data
    message = "Validation error" if isinstance(detail, dict) else str(detail)
    if isinstance(detail, dict) and "detail" in detail:
        message = str(detail["detail"])

    response.data = {
        "success": False,
        "error": exc.__class__.__name__.upper(),
        "message": message,
        "details": detail if isinstance(detail, dict) else {},
    }
    return response
