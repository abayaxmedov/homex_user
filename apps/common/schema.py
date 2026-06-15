from drf_spectacular.extensions import OpenApiAuthenticationExtension


class RoleJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "apps.accounts.authentication.RoleJWTAuthentication"
    name = "RoleJWTAuth"

    def get_security_definition(self, auto_schema):
        return {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
