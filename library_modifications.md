We use a custom fork of `Disnake` with some added features + fixes as detailed here.

This mainly exists such that if we wish to upgrade from say, `2.5.x` -> `2.6.x` we know exactly what things require porting.

---

## Features

- `Interaction.deferred_without_send` -> `bool`
  - Hooks into the `Interaction` object to see if a given interaction has been differed without a follow-up send occurring. We do this as we need to clean up after the bot in the case an error occurs otherwise our users will simply get "Interaction failed to respond" which is not ideal
  - Implementation details:
    - New variable on `Interaction` -> `self.has_been_followed_up: bool = False`
      - Set to `True` in `Interaction.send` after message is sent
    - New variable on `InteractionResponse` -> `self.has_been_deferred: bool = False`
      - Set to `True` in `InteractionResponse.defer`
    - New property
      - https://paste.disnake.dev/?id=1660196042475314
- Show gateway session on initial startup
  - Logs session related information to console with log level `WARNING` to avoid being suppressed or needing special handling to show. (Anything lower is suppressed bot side.)
  - Implementation details:
    - After `data: gateway.GatewayBot = await self.request(Route("GET", "/gateway/bot"))` in `get_bot_gateway`
      - https://paste.disnake.dev/?id=1660196180710978
- `disnake.Guild.icon.url` erroring when `icon` is `None`
  - Due to the lack of guild intents, using `disnake.Guild.icon.url` requires guarding to ensure we can actually use the icon. A similar port will also likely be applied to `disnake.User` sooner or later.
  - Fixed by adding a new method `disnake.Guild.try_fetch_icon_url`
  - *I consider this one a feature due to the nature of the fix.*
  - Related issues: https://github.com/suggestionsbot/suggestions-bot-rewrite/issues/3
- Added `__eq__` to `disnake.Embed` 
  - This is used primarily within tests
  - This includes `__eq__` on `EmbedProxy` otherwise they compare as False
- Heavily modified guild caching in relation to <https://github.com/suggestionsbot/suggestions-bot/issues/24>
  - Introduced the variable `guild_ids`
  - Disabled the guild cache even with enabled guild intents
  - See commit <https://github.com/suggestionsbot/disnake/commit/a21e761d72bba13af1f834f7f5b18724ea9ce0f5>

## Fixes

- Process crashes due to `Intents.none()` with relation to interactions
  - `discord.py`, and by extension `disnake` are built around the idea of at-least having the guilds intent. In this case, a lack of guild objects results in a reproducible process crash for the bot handling the interaction. 
  - Implementation details:
    - Prematurely return from `disnake.abc._fill_overwrites` before it hits `everyone_id = self.guild.id`
      - https://paste.disnake.dev/?id=1660197346583275
  - *Note, the fix detailed here and the fix applied to `disnake` itself are different. We don't care for overwrites at this time, and we have not rebased against upstream since the relevant patches were applied.*
- `AttributeError`'s on `discord.Object` objects due to `Intents.none()`
  - On suggestions with un-cached guilds, if they have a thread it can result in an error as the existence check for `self.guild` will be truthy even with a `disnake.Object` instance, despite requiring `disnake.Guild` as subsequent usage after existence checks call `disnake.Guild.get_thread`
  - Implementation details:
    - Modify `disnake.Message.thread` to the following
      - https://paste.disnake.dev/?id=1660197950019675
  - Related issues: https://github.com/DisnakeDev/disnake/issues/699
- Removed the `MessageContentPrefixWarning` as it would trip due to inheritance of the bot base
- `AttributeError`'s on `discord.Object` where `discord.Guild` was expected.
  - This is the same as "`AttributeError`'s on `discord.Object` objects due to `Intents.none()`"
  - Implementation details
    - Fixed by https://paste.disnake.dev/?id=1660730340161476
  - Related issue: https://github.com/DisnakeDev/disnake/issues/712
## Notes

On startup even with `Intents.none()` we still receive partial guilds, noted as unavailable (or something like that). This allows for partial cache hits and explains the inconsistencies of bug reproduction as we require a guild who invited the bot during runtime as the first reproduction step.

Versions are bumped to overcome some CI caching issues.

We don't follow or publish to upstream, a shame I know. Security issues however (such as process crashing) are noted exceptions and dealt with on a case by case basis.

