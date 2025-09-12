from alaric import Document
from motor.motor_asyncio import AsyncIOMotorClient

from suggestions.objects import (
    Suggestion,
    GuildConfig,
    UserConfig,
    Error,
    QueuedSuggestion,
    PremiumGuildConfig,
)
from suggestions.objects.stats import MemberStats


class SuggestionsMongoManager:
    def __init__(self, connection_url):
        self.database_name = "suggestions_bot"

        self.__mongo = AsyncIOMotorClient(connection_url)
        self.db = self.__mongo[self.database_name]

        self.suggestions: Document = Document(
            self.db, "suggestions", converter=Suggestion
        )
        self.guild_configs: Document = Document(
            self.db, "guild_configs", converter=GuildConfig
        )
        self.premium_guild_configs: Document = Document(
            self.db, "premium_guild_configs", converter=PremiumGuildConfig
        )
        self.user_configs: Document = Document(
            self.db, "user_configs", converter=UserConfig
        )
        self.beta_links: Document = Document(self.db, "beta_links")
        self.cluster_guild_counts: Document = Document(self.db, "cluster_guild_counts")
        self.cluster_shutdown_requests: Document = Document(
            self.db, "cluster_shutdown_requests"
        )
        self.member_stats: Document = Document(
            self.db, "member_stats", converter=MemberStats
        )
        self.locale_tracking: Document = Document(self.db, "locale_tracking")
        self.error_tracking: Document = Document(
            self.db, "error_tracking", converter=Error
        )
        self.queued_suggestions: Document = Document(
            self.db, "queued_suggestions", converter=QueuedSuggestion
        )
        self.interaction_events: Document = Document(
            self.db, "interaction_create_stats"
        )
