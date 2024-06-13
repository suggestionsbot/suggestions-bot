from typing import List, Union, TypeVar, Optional, Callable

import disnake
from disnake.ext import commands

from suggestions.interaction_handler import InteractionHandler

# Inspired by https://github.com/nextcord/nextcord-ext-menus

T = TypeVar("T")


class PaginationView(disnake.ui.View):
    FIRST_PAGE = "\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\ufe0f"
    PREVIOUS_PAGE = "\N{BLACK LEFT-POINTING TRIANGLE}\ufe0f"
    NEXT_PAGE = "\N{BLACK RIGHT-POINTING TRIANGLE}\ufe0f"
    LAST_PAGE = "\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\ufe0f"
    STOP = "\N{BLACK SQUARE FOR STOP}\ufe0f"

    def __init__(
        self,
        author_id: int,
        paginator: "DisnakePaginator",
        *,
        timeout: Optional[float] = 180,
    ):
        super().__init__(timeout=timeout)
        self.author_id: int = author_id
        self._paginator: "DisnakePaginator" = paginator

        # Default to disabled, we change them later anyway if actually required.
        self.first_page_button = disnake.ui.Button(label=self.FIRST_PAGE, disabled=True)
        self.previous_page_button = disnake.ui.Button(
            label=self.PREVIOUS_PAGE, disabled=True
        )
        self.next_page_button = disnake.ui.Button(label=self.NEXT_PAGE, disabled=True)
        self.last_page_button = disnake.ui.Button(label=self.LAST_PAGE, disabled=True)
        self.stop_button = disnake.ui.Button(label=self.STOP, disabled=True)

        self.first_page_button.callback = self._paginator.go_to_first_page
        self.previous_page_button.callback = self._paginator.go_to_previous_page
        self.next_page_button.callback = self._paginator.go_to_next_page
        self.last_page_button.callback = self._paginator.go_to_last_page
        self.stop_button.callback = self._paginator.stop_pages

        self.add_item(self.first_page_button)
        self.add_item(self.previous_page_button)
        self.add_item(self.next_page_button)
        self.add_item(self.last_page_button)
        self.add_item(self.stop_button)

    async def interaction_check(self, interaction: disnake.MessageInteraction) -> bool:
        return interaction.user.id == self.author_id

    async def on_timeout(self) -> None:
        self.stop()
        await self._paginator.stop()


class DisnakePaginator:
    def __init__(
        self,
        items_per_page: int,
        input_data: List[T],
        *,
        try_ephemeral: bool = True,
        delete_buttons_on_stop: bool = False,
        page_formatter: Optional[Callable] = None,
    ):
        """
        A simplistic paginator built for Disnake.

        Parameters
        ----------
        items_per_page: int
            How many items to show per page.
        input_data: List[Any]
            The data to be paginated.
        try_ephemeral: bool
            Whether or not to try send the interaction
            as ephemeral. Defaults to ``True``
        delete_buttons_on_stop: bool
            When the paginator is stopped, should
            the buttons be deleted? Defaults to ``False``
            which merely disables them.
        page_formatter: Callable
            An inline formatter to save the need to
            subclass/override ``format_page``
        """
        self._current_page_index = 0
        self._items_per_page: int = items_per_page
        self.__input_data: List[T] = input_data
        self._try_ephemeral: bool = try_ephemeral
        self._delete_buttons_on_stop: bool = delete_buttons_on_stop
        self._inline_format_page: Optional[Callable] = page_formatter

        if items_per_page <= 0:
            raise ValueError("items_per_page must be 1 or higher.")

        if self._items_per_page == 1:
            self._paged_data: List[T] = self.__input_data

        else:
            self._paged_data: List[List[T]] = [
                self.__input_data[i : i + self._items_per_page]
                for i in range(0, len(self.__input_data), self._items_per_page)
            ]

        self._is_done: bool = False
        self._message: Optional[disnake.Message] = None
        self._pagination_view: Optional[PaginationView] = None

    @property
    def current_page(self) -> int:
        """The current page for this paginator."""
        return self._current_page_index + 1

    @current_page.setter
    def current_page(self, value) -> None:
        if value > self.total_pages:
            raise ValueError(
                "Cannot change current page to a page bigger then this paginator."
            )

        self._current_page_index = value - 1

    @property
    def total_pages(self) -> int:
        "How many pages exist in this paginator."
        return len(self._paged_data)

    @property
    def requires_pagination(self) -> bool:
        """Does this paginator have more then 1 page."""
        return len(self._paged_data) != 1

    @property
    def has_prior_page(self) -> bool:
        """Can we move backwards pagination wide."""
        return self.current_page != 1

    @property
    def has_next_page(self) -> bool:
        """Can we move forward pagination wise."""
        return self.current_page != self.total_pages

    async def start(self, ih: InteractionHandler):
        """
        Start paginating this paginator.
        """
        first_page: Union[str, disnake.Embed] = await self.format_page(
            self._paged_data[self._current_page_index], self.current_page
        )

        send_kwargs = {}
        if isinstance(first_page, disnake.Embed):
            send_kwargs["embed"] = first_page
        else:
            send_kwargs["content"] = first_page

        interaction = ih.interaction
        self._pagination_view = PaginationView(interaction.user.id, self)
        if ih.has_sent_something:
            self._message = await interaction.original_message()
            if self.requires_pagination:
                await self._message.edit(**send_kwargs, view=self._pagination_view)

            else:
                await self._message.edit(**send_kwargs)

        else:
            ih.has_sent_something = True
            if self.requires_pagination:
                await interaction.send(
                    **send_kwargs,
                    ephemeral=self._try_ephemeral,
                    view=self._pagination_view,
                )

            else:
                await interaction.send(
                    **send_kwargs,
                    ephemeral=self._try_ephemeral,
                )

            self._message = await interaction.original_message()

        await self._set_buttons()

    async def stop(self):
        """Stop paginating this paginator."""
        self._is_done = True
        await self._set_buttons()

    async def _set_buttons(self) -> disnake.Message:
        """Sets buttons based on current page."""
        if not self.requires_pagination:
            # No pagination required
            return await self._message.edit(view=None)

        if self._is_done:
            # Disable all buttons
            if self._delete_buttons_on_stop:
                return await self._message.edit(view=None)

            self._pagination_view.stop_button.disabled = True
            self._pagination_view.next_page_button.disabled = True
            self._pagination_view.last_page_button.disabled = True
            self._pagination_view.first_page_button.disabled = True
            self._pagination_view.previous_page_button.disabled = True
            return await self._message.edit(view=self._pagination_view)

        # Toggle buttons
        if self.has_prior_page:
            self._pagination_view.first_page_button.disabled = False
            self._pagination_view.previous_page_button.disabled = False
        else:
            # Cannot go backwards
            self._pagination_view.first_page_button.disabled = True
            self._pagination_view.previous_page_button.disabled = True

        if self.has_next_page:
            self._pagination_view.next_page_button.disabled = False
            self._pagination_view.last_page_button.disabled = False
        else:
            self._pagination_view.next_page_button.disabled = True
            self._pagination_view.last_page_button.disabled = True

        self._pagination_view.stop_button.disabled = False

        return await self._message.edit(view=self._pagination_view)

    async def show_page(self, page_number: int):
        """
        Change to the given page.

        Parameters
        ----------
        page_number: int
            The page you wish to see.

        Raises
        ------
        ValueError
            Page number is too big for this paginator.
        """
        self.current_page = page_number
        page: Union[str, disnake.Embed] = await self.format_page(
            self._paged_data[self._current_page_index], self.current_page
        )
        if isinstance(page, disnake.Embed):
            await self._message.edit(embed=page)
        else:
            await self._message.edit(content=page)
        await self._set_buttons()

    async def go_to_first_page(self, interaction: disnake.MessageInteraction):
        """Paginate to the first page."""
        await interaction.response.defer()
        await self.show_page(1)

    async def go_to_previous_page(self, interaction: disnake.Interaction):
        """Paginate to the previous viewable page."""
        await interaction.response.defer()
        await self.show_page(self.current_page - 1)

    async def go_to_next_page(self, interaction: disnake.Interaction):
        """Paginate to the next viewable page."""
        await interaction.response.defer()
        await self.show_page(self.current_page + 1)

    async def go_to_last_page(self, interaction: disnake.Interaction):
        """Paginate to the last viewable page."""
        await interaction.response.defer()
        await self.show_page(self.total_pages)

    async def stop_pages(self, interaction: disnake.Interaction):
        """Stop paginating this paginator."""
        await interaction.response.defer()
        await self.stop()

    async def format_page(
        self, page_items: Union[T, List[T]], page_number: int
    ) -> Union[str, disnake.Embed]:
        """Given the page items, format them how you wish.

        Calls the inline formatter if not overridden,
        otherwise returns ``page_items`` as a string.

        Parameters
        ----------
        page_items: Union[T, List[T]]
            The items for this page.
            If ``items_per_page`` is ``1`` then this
            will be a singular item.
        page_number: int
            This pages number.
        """
        if self._inline_format_page:
            return self._inline_format_page(self, page_items, page_number)

        return str(page_items)
