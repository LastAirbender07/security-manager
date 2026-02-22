from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "repoconfig" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "url" VARCHAR(255) NOT NULL UNIQUE,
    "provider" VARCHAR(50) NOT NULL  DEFAULT 'github',
    "is_active" BOOL NOT NULL  DEFAULT True,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "access_token" VARCHAR(255)
);
CREATE TABLE IF NOT EXISTS "scanresult" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "pr_number" INT NOT NULL,
    "commit_sha" VARCHAR(40) NOT NULL,
    "status" VARCHAR(20) NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "trivy_scan" JSONB NOT NULL,
    "semgrep_scan" JSONB NOT NULL,
    "report_data" JSONB,
    "repo_config_id" INT NOT NULL REFERENCES "repoconfig" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "scanlog" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "step" VARCHAR(50) NOT NULL,
    "tokens_input" INT NOT NULL  DEFAULT 0,
    "tokens_output" INT NOT NULL  DEFAULT 0,
    "model_name" VARCHAR(50),
    "message" TEXT,
    "timestamp" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "scan_result_id" INT NOT NULL REFERENCES "scanresult" ("id") ON DELETE CASCADE
);
COMMENT ON TABLE "scanlog" IS 'Observability: Tracks token usage and agent actions';
CREATE TABLE IF NOT EXISTS "systemconfig" (
    "key" VARCHAR(100) NOT NULL  PRIMARY KEY,
    "value" TEXT NOT NULL,
    "is_secret" BOOL NOT NULL  DEFAULT False,
    "updated_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE "systemconfig" IS 'Stores global system configuration and secrets.';
CREATE TABLE IF NOT EXISTS "aerich" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "version" VARCHAR(255) NOT NULL,
    "app" VARCHAR(100) NOT NULL,
    "content" JSONB NOT NULL
);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        """
