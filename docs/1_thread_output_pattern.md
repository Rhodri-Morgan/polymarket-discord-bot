# Thread-Based Output Pattern

All cog output that produces lists of data uses Discord threads, not paginated button views or flat channel messages.

## Why Threads

- **Button interactions expire** after ~5 minutes — useless for scheduled/cron posts that have no user session.
- **Threads are persistent** — scrollable, searchable, don't expire.
- **No view state management** — no `discord.ui.View` instances, no timeout handling, no button callbacks.

## Message Flow

```
channel.send(summary_embed)          # 1. Post summary to channel
  └─ summary.create_thread(name=...) # 2. Create thread on the summary message
       └─ thread.send(embeds=batch)  # 3. Post data in batches inside the thread
```

### Step 1 — Summary Embed

Post to the channel via `channel.send()`, **not** `interaction.followup.send()`. Discord `WebhookMessage` objects returned by `followup.send()` do not support `create_thread()`.

The summary embed acts as the thread anchor visible in the main channel. It should contain:
- Title with result count
- Filter/configuration context (excluded categories, thresholds)
- Generation timestamp

### Step 2 — Thread Creation

```python
thread = await summary.create_thread(
    name=f"Feature Name — {datetime.now(timezone.utc).strftime('%b %d %H:%M')} UTC",
)
```

Thread names include the UTC timestamp so multiple runs are distinguishable.

### Step 3 — Batched Data Posts

Data is posted inside the thread in batches to stay within Discord's 10-embed-per-message limit:

```python
for batch_start in range(0, len(items), ITEMS_PER_MESSAGE):
    embeds = format_items(items, page=batch_start // ITEMS_PER_MESSAGE, per_page=ITEMS_PER_MESSAGE)
    await thread.send(embeds=embeds)
```

## Slash Command Interaction

Slash commands cannot directly use the thread pattern because the interaction must be acknowledged. The flow is:

1. `interaction.response.defer()` — acknowledge within 3 seconds
2. Fetch data
3. `interaction.followup.send("Status message...")` — tell the user something is happening
4. Use `interaction.channel` (not the followup) to post the summary + thread

```python
await interaction.followup.send("Fetching data...")
channel = interaction.channel
await _post_feature_thread(channel, data)
```

## Reference Implementations

Any cog under `src/polymarket_bot/cogs/` that posts list data will have a `_post_*_thread()` function following this pattern. Grep for `create_thread` to find current implementations.
