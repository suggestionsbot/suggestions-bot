from alaric import Document
from mongomock_motor import AsyncMongoMockClient

from suggestions.objects import (
    Suggestion,
    GuildConfig,
    UserConfig,
    Error,
    QueuedSuggestion,
)
from suggestions.objects.stats import MemberStats


class MockedSuggestionsMongoManager:
    def __init__(self):
        self.database_name = "suggestions-rewrite-testing"

        self.__mongo = AsyncMongoMockClient()
        self.db = self.__mongo[self.database_name]

        # Documents
        self.user_blacklist = Document(self.db, "user_blacklist")
        self.guild_blacklist = Document(self.db, "guild_blacklist")

        self.suggestions: Document = Document(
            self.db, "suggestions", converter=Suggestion
        )
        self.guild_configs: Document = Document(
            self.db, "guild_configs", converter=GuildConfig
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
