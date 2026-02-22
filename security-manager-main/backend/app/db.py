from tortoise import Tortoise
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgres://guardian:password@db:5432/security_guardian")

async def init_db():
    await Tortoise.init(
        db_url=DATABASE_URL,
        modules={"models": ["app.models"]},
    )
    await Tortoise.generate_schemas()

async def close_db():
    await Tortoise.close_connections()
