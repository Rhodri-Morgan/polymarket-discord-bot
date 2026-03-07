"""Reusable Discord UI views — pagination buttons, sort dropdowns."""

from __future__ import annotations

import discord

from polymarket_bot.formatting import format_market_list, total_pages


class MarketPaginationView(discord.ui.View):
    """Prev/Next buttons for paginating through a market list."""

    def __init__(
        self,
        markets: list[dict],
        per_page: int = 5,
        timeout: float = 300,
        title: str | None = None,
        colour: discord.Colour | None = None,
    ):
        super().__init__(timeout=timeout)
        self.markets = markets
        self.per_page = per_page
        self.page = 0
        self.num_pages = total_pages(len(markets), per_page)
        self._title = title
        self._colour = colour
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.prev_button.disabled = self.page <= 0
        self.next_button.disabled = self.page >= self.num_pages - 1
        self.page_label.label = f"{self.page + 1}/{self.num_pages}"

    def _make_embeds(self) -> list[discord.Embed]:
        embeds = format_market_list(self.markets, page=self.page, per_page=self.per_page)
        if self._title:
            embeds[0].title = self._title
        if self._colour:
            embeds[0].colour = self._colour
        return embeds

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.primary, emoji="⬅️")
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.page = max(0, self.page - 1)
        self._update_buttons()
        await interaction.response.edit_message(embeds=self._make_embeds(), view=self)

    @discord.ui.button(label="1/1", style=discord.ButtonStyle.secondary, disabled=True)
    async def page_label(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        pass  # non-interactive label

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.primary, emoji="➡️")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.page = min(self.num_pages - 1, self.page + 1)
        self._update_buttons()
        await interaction.response.edit_message(embeds=self._make_embeds(), view=self)
