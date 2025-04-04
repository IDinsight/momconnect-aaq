"""This module contains configuration settings for the dashboard package."""

import os

DISABLE_DASHBOARD_LLM = (
    os.environ.get("DISABLE_DASHBOARD_LLM", "true").lower() == "true"
)
MAX_FEEDBACK_RECORDS_FOR_AI_SUMMARY = os.environ.get(
    "MAX_FEEDBACK_RECORDS_FOR_AI_SUMMARY", 100
)
MAX_FEEDBACK_RECORDS_FOR_TOP_CONTENT = os.environ.get(
    "MAX_FEEDBACK_RECORDS_FOR_TOP_CONTENT", 7
)
TOPIC_MODELING_CONTEXT = os.environ.get("TOPIC_MODELING_CONTEXT", "maternal health")
