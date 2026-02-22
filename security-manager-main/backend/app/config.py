import os
DATABASE_URL = os.getenv("DATABASE_URL", "postgres://guardian:password@db:5432/security_guardian")

TORTOISE_ORM = {
    "connections": {"default": DATABASE_URL},
    "apps": {
        "models": {
            "models": ["app.models", "aerich.models"],
            "default_connection": "default",
        },
    },
}
