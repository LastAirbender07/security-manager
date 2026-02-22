from tortoise import fields, models
from tortoise.contrib.pydantic import pydantic_model_creator

class RepoConfig(models.Model):
    id = fields.IntField(pk=True)
    url = fields.CharField(max_length=255, unique=True)
    provider = fields.CharField(max_length=50, default="github") # github, bitbucket
    is_active = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    
    # Store encrypted/masked credentials if needed (simplified for now)
    access_token = fields.CharField(max_length=255, null=True)

class ScanResult(models.Model):
    id = fields.IntField(pk=True)
    repo_config = fields.ForeignKeyField("models.RepoConfig", related_name="scans")
    pr_number = fields.IntField()
    commit_sha = fields.CharField(max_length=40)
    status = fields.CharField(max_length=20) # pending, clean, vulnerable, fixed, failed
    celery_task_id = fields.CharField(max_length=255, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    
    # Findings stored as JSON
    trivy_scan = fields.JSONField(default=list)
    semgrep_scan = fields.JSONField(default=list)
    
    # Full pipeline report
    report_data = fields.JSONField(default=dict, null=True)
    
class ScanLog(models.Model):
    """Observability: Tracks token usage and agent actions"""
    id = fields.IntField(pk=True)
    scan_result = fields.ForeignKeyField("models.ScanResult", related_name="logs")
    step = fields.CharField(max_length=50) # Scanner, Analysis, Remediation, Verification
    tokens_input = fields.IntField(default=0)
    tokens_output = fields.IntField(default=0)
    model_name = fields.CharField(max_length=50, null=True)
    message = fields.TextField(null=True)
    timestamp = fields.DatetimeField(auto_now_add=True)

class SystemConfig(models.Model):
    """Stores global system configuration and secrets."""
    key = fields.CharField(max_length=100, pk=True)
    value = fields.TextField()
    is_secret = fields.BooleanField(default=False)  # If true, mask in API responses
    updated_at = fields.DatetimeField(auto_now=True)

# Pydantic creators - Removed due to Pydantic v2 incompatibility
# RepoConfig_Pydantic = pydantic_model_creator(RepoConfig, name="RepoConfig")
# RepoConfigIn_Pydantic = pydantic_model_creator(RepoConfig, name="RepoConfigIn", exclude_readonly=True)
