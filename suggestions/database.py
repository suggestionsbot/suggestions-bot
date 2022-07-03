from alaric import Document
from bot_base.db import MongoManager

from suggestions.objects import Suggestion, GuildConfig


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
