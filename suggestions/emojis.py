class Emojis:
    """A class to put all emojis in one place."""

    thumbs_up = "👍"
    thumbs_down = "👎"
    tick = "<:nerdSuccess:605265580416565269>"
    cross = "<:nerdError:605265598343020545>"

    @classmethod
    def default_up_vote(cls):
        return cls.tick

    @classmethod
    def default_down_vote(cls):
        return cls.cross
