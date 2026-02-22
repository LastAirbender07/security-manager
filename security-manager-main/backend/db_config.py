TORTOISE_ORM = {
    "connections": {"default": "postgres://guardian:password@security-management-db-1:5432/security_guardian"},
    "apps": {
        "models": {
            "models": ["app.models", "aerich.models"],
            "default_connection": "default",
        },
    },
}
