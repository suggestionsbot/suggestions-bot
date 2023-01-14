import os
from typing import NamedTuple

from alaric import Document, AQ
from alaric.comparison import IN, EQ, Exists
from alaric.logical import AND, OR
from alaric.meta import All, Negate
from motor.motor_asyncio import AsyncIOMotorClient

from suggestions.objects import Error


class ErrorTelemetry(NamedTuple):
    total_errors: int
    total_handled_errors: int
    reraised_errors: int
    total_unhandled_errors: int


async def error_telemetry() -> ErrorTelemetry:
    client = AsyncIOMotorClient(os.environ["PROD_MONGO_URL"])
    database = client["suggestions-rewrite"]
    document = Document(database, "error_tracking")
    total_errors = await document.count(All())
    total_handled_errors = await document.count(
        AQ(
            IN(
                "error",
                [
                    "ErrorHandled",
                    "BetaOnly",
                    "MissingSuggestionsChannel",
                    "MissingLogsChannel",
                    "MissingPermissions",
                    "SuggestionNotFound",
                    "SuggestionTooLong",
                    "InvalidGuildConfigOption",
                    "CallableOnCooldown",
                    "ConfiguredChannelNoLongerExists",
                    "LocalizationKeyError",
                ],
            )
        )
    )
    reraised_errors = await document.count(AQ(IN("error", ["Forbidden", "NotFound"])))
    total_unhandled_errors = total_errors - total_handled_errors - reraised_errors
    return ErrorTelemetry(
        total_errors, total_handled_errors, reraised_errors, total_unhandled_errors
    )


async def unique_unhandled_errors() -> set[Error]:
    client = AsyncIOMotorClient(os.environ["PROD_MONGO_URL"])
    database = client["suggestions-rewrite"]
    document = Document(database, "error_tracking", converter=Error)
    unhandled_errors: list[Error] = await document.find_many(
        AQ(
            AND(
                Negate(
                    IN(
                        "error",
                        [
                            "ErrorHandled",
                            "BetaOnly",
                            "MissingSuggestionsChannel",
                            "MissingLogsChannel",
                            "MissingPermissions",
                            "SuggestionNotFound",
                            "SuggestionTooLong",
                            "InvalidGuildConfigOption",
                            "CallableOnCooldown",
                            "ConfiguredChannelNoLongerExists",
                            "LocalizationKeyError",
                            "Forbidden",
                            "NotFound",
                        ],
                    )
                ),
                OR(EQ("has_been_fixed", False), Negate(Exists("has_been_fixed"))),
            )
        )
    )
    return set(unhandled_errors)
