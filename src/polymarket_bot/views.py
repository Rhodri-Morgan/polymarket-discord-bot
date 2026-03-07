"""Reusable Discord UI views — pagination buttons, sort dropdowns."""

from __future__ import annotations

import discord

from polymarket_bot.formatting import format_market_list, total_pages


class MarketPaginationView(discord.ui.View):
    """Prev/Next buttons for paginating through a market list."""

    def __init__(self, markets: list[dict], per_page: int = 5, timeout: float = 300):
        super().__init__(timeout=timeout)
        self.markets = markets
        self.per_page = per_page
        self.page = 0
        self.num_pages = total_pages(len(markets), per_page)
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.prev_button.disabled = self.page <= 0
        self.next_button.disabled = self.page >= self.num_pages - 1

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.page = max(0, self.page - 1)
        self._update_buttons()
        embeds = format_market_list(self.markets, page=self.page, per_page=self.per_page)
        await interaction.response.edit_message(embeds=embeds, view=self)

    @discord.ui.button(label="▶ Next", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.page = min(self.num_pages - 1, self.page + 1)
        self._update_buttons()
        embeds = format_market_list(self.markets, page=self.page, per_page=self.per_page)
        await interaction.response.edit_message(embeds=embeds, view=self)
