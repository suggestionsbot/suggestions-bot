from alaric import Document
from bot_base.db import MongoManager

from suggestions.objects import Suggestion


class SuggestionsMongoManager(MongoManager):
    def __init__(self, connection_url):
        super().__init__(
            connection_url=connection_url, database_name="suggestions-rewrite"
        )

        self.suggestions: Document = Document(
            self.db, "suggestions", converter=Suggestion
        )
        self.command_usage_stats: Document = Document(self.db, "command_usage_stats")
