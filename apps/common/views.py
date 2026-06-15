from apps.common.responses import success_response


class EnvelopeMixin:
    success_message = "OK"

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        if getattr(response, "exception", False):
            return response
        if not isinstance(getattr(response, "data", None), (dict, list)):
            return response
        if isinstance(response.data, dict) and "success" in response.data:
            return response
        if isinstance(response.data, dict) and {"count", "next", "previous", "results"}.issubset(response.data):
            response.data = {"success": True, **response.data}
        else:
            response.data = {"success": True, "message": self.success_message, "data": response.data}
        return response


class SuccessResponseMixin:
    def ok(self, data=None, message="OK", status=200):
        return success_response(data=data, message=message, status=status)
