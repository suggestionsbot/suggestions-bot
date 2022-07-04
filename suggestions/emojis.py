class Emojis:
    """A class to put all emojis in one place."""

    thumbs_up = "👍"
    thumbs_down = "👎"
    tick = "<:nerdSuccess:605265580416565269>"
    cross = "<:nerdError:605265598343020545>"

    @property
    def default_up_vote(self):
        return self.tick

    @property
    def default_down_vote(self):
        return self.cross
