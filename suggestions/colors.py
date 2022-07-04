import disnake
from bot_base.paginators.disnake_paginator import DisnakePaginator


class Colors:
    """A class to keep colors in a single place."""

    error = disnake.Color.from_rgb(214, 48, 49)
    beta_required = disnake.Color.from_rgb(7, 0, 77)
    pending_suggestion = disnake.Color.from_rgb(255, 214, 99)
    approved_suggestion = disnake.Color.from_rgb(0, 230, 64)
    rejected_suggestion = disnake.Color.from_rgb(207, 0, 15)

    @classmethod
    async def show_colors(cls, interaction):
        """Shows the color options on discord."""
        paginator: DisnakePaginator = DisnakePaginator(
            1,
            [
                [
                    "Error",
                    cls.error,
                ],
                [
                    "Beta Required",
                    cls.beta_required,
                ],
                [
                    "Pending Suggestion",
                    cls.pending_suggestion,
                ],
                [
                    "Approved Suggestion",
                    cls.approved_suggestion,
                ],
                [
                    "Rejected Suggestion",
                    cls.rejected_suggestion,
                ],
            ],
        )

        async def format_page(items, page_count):
            color: disnake.Color = items[1]
            description = f"{items[0]}\nRGB: {color.r},{color.g},{color.b}"
            return disnake.Embed(
                title="Bot color palette", description=description, color=items[1]
            )

        paginator.format_page = format_page
        await paginator.start(interaction=interaction)
