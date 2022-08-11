We use a custom fork of `Disnake` with some added features + fixes as detailed here.

This mainly exists such that if we wish to upgrade from say, `2.5.x` -> `2.6.x` we know exactly what things require porting.

---

## Features

- `Interaction.deffered_without_send` -> `bool`
  - Hooks into the `Interaction` object to see if a given interaction has been differed without a follow-up send occurring. We do this as we need to clean up after the bot in the case an error occurs otherwise our users will simply get "Interaction failed to respond" which is not ideal
  - Implementation details:
    - New variable on `Interaction` -> `self.has_been_followed_up: bool = False`
      - Set to `True` in `Interaction.send` __if__ we enter `sender = self.followup.send`
    - New property
      - https://paste.disnake.dev/?id=1660196042475314
- Show gateway session on initial startup
  - Logs session related information to console with log level `WARNING` to avoid being suppressed or needing special handling to show. (Anything lower is suppressed bot side.)
  - Implementation details:
    - After `data: gateway.GatewayBot = await self.request(Route("GET", "/gateway/bot"))` in `get_bot_gateway`
      - https://paste.disnake.dev/?id=1660196180710978
- `disnake.Guild.icon.url` erroring when `icon` is `None`
  - Due to the lack of guild intents, using `disnake.Guild.icon.url` requires guarding to ensure we can actually use the icon. Given we need this is a decent number of places I plan on implementing a method for this which will ensure we either get the icon url or `None` rather than an error and removing the need to program in a defensive manner. A similar port will also likely be applied to `disnake.User`
  - *I consider this one a feature due to the nature of the fix.*
  - Related issues: https://github.com/suggestionsbot/suggestions-bot-rewrite/issues/3

## Fixes

- Process crashes due to `Intents.none()` with relation to interactions
  - `discord.py`, and by extension `disnake` are built around the idea of at-least having the guilds intent. In this case, a lack of guild objects results in a reproducible process crash for the bot handling the interaction. 
  - *Note, the fix detailed here and the fix applied to `disnake` itself are different. We don't care for overwrites at this time, and we have not rebased against upstream since the relevant patches were applied.*
- `AttributeError`'s on `NoneType` objects due to `Intents.none()`
  - On suggestions with un-cached guilds, if they have a thread it can result in an error as the existence check for `self.guild` will be truthy even with a `disnake.Object` instance, despite requiring `disnake.Guild` as subsequent usage after existence checks call `disnake.Guild.get_thread`
  - Implementation details:
    - Modify `disnake.Message.thread` to the following
      - https://paste.disnake.dev/?id=1660196640886432

## Notes

On startup even with `Intents.none()` we still receive partial guilds, noted as unavailable (or something like that). This allows for partial cache hits and explains the inconsistencies of bug reproduction as require a guild who invited the bot during runtime as the first reproduction step.

Versions are bumped to overcome some CI caching issues.

We don't follow or publish to upstream, a shame I know. Security issues however (such as process crashing) are noted exceptions and dealt with on a case by case basis.

