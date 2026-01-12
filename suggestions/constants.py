import logging
import os
from typing import Literal, cast

from dotenv import load_dotenv
from infisical_sdk import InfisicalSDKClient
from opentelemetry import trace, metrics
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics._internal.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import (
    SERVICE_NAME,
    Resource,
    DEPLOYMENT_ENVIRONMENT,
    HOST_NAME,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from redis import asyncio as aioredis

load_dotenv()
infisical_client = InfisicalSDKClient(host="https://secrets.skelmis.co.nz")
infisical_client.auth.universal_auth.login(
    client_id=os.environ["INFISICAL_ID"],
    client_secret=os.environ["INFISICAL_SECRET"],
)


def configure_otel():
    host = get_secret("OTEL_HOST", infisical_client)
    endpoint = get_secret("OTEL_ENDPOINT", infisical_client)
    bearer_token = get_secret("OTEL_BEARER", infisical_client)
    deployment_environment: Literal["Production", "Development", "Staging"] = cast(
        Literal["Production", "Development", "Staging"],
        get_secret("OTEL_DEPLOYMENT_ENVIRONMENT", infisical_client),
    )
    service_name = (
        "suggestions-bot-v3"
        if deployment_environment == "Production"
        else "dev-suggestions-bot-v3"
    )
    headers = {"Authorization": f"Bearer {bearer_token}"}
    attributes = {
        SERVICE_NAME: service_name,
        DEPLOYMENT_ENVIRONMENT: deployment_environment,
        HOST_NAME: host,
    }
    resource = Resource.create(attributes=attributes)

    # Setup TracerProvider for trace correlation
    trace_provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(trace_provider)
    trace_provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces", headers=headers)
        )
    )

    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=f"{endpoint}/v1/metrics", headers=headers)
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(meter_provider)

    # Configure logger provider
    logger_provider = LoggerProvider(resource=resource)
    set_logger_provider(logger_provider)

    # Add OTLP exporter (reads endpoint/headers from environment variables)
    exporter = OTLPLogExporter(endpoint=f"{endpoint}/v1/logs", headers=headers)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(exporter))

    # Attach OTel handler to Python's root logger
    handler = LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)


def get_secret(secret_name: str, infisical_client: InfisicalSDKClient) -> str:
    return infisical_client.secrets.get_secret_by_name(
        secret_name=secret_name,
        project_id=os.environ["INFISICAL_PROJECT_ID"],
        environment_slug=os.environ["INFISICAL_SLUG"],
        secret_path="/",
        view_secret_value=True,
    ).secretValue


TRACER = trace.get_tracer(__name__)
CF_R2_ACCESS_KEY = get_secret("CF_R2_ACCESS_KEY", infisical_client)
CF_R2_SECRET_ACCESS_KEY = get_secret("CF_R2_SECRET_ACCESS_KEY", infisical_client)
CF_R2_BUCKET = get_secret("CF_R2_BUCKET", infisical_client)
CF_R2_URL = get_secret("CF_R2_URL", infisical_client)
BOT_TOKEN = get_secret("BOT_TOKEN", infisical_client)
MONGO_URL = get_secret("MONGO_URL", infisical_client)
REDIS_CLIENT = aioredis.from_url(get_secret("REDIS_URL", infisical_client))

# Lists
LISTS_TOP_GG_API_KEY = get_secret("LISTS_TOP_GG_API_KEY", infisical_client)
LISTS_DISCORDBOTLIST_API_KEY = get_secret(
    "LISTS_DISCORDBOTLIST_API_KEY", infisical_client
)
LISTS_DISCORD_BOTS_GG_API_KEY = get_secret(
    "LISTS_DISCORD_BOTS_GG_API_KEY", infisical_client
)
