from alaric import Document
from bot_base.db import MongoManager

from suggestions.objects import Suggestion, GuildConfig, UserConfig, Error
from suggestions.objects.stats import MemberStats


class SuggestionsMongoManager(MongoManager):
    def __init__(self, connection_url):
        super().__init__(
            connection_url=connection_url, database_name="suggestions-rewrite"
        )

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
