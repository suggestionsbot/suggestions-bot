We use a custom fork of `Disnake` with some added features + fixes as detailed here.

This mainly exists such that if we wish to upgrade from say, `2.5.x` -> `2.6.x` we know exactly what things require porting.

---

## Features

- Show gateway session on initial startup
  - Logs session related information to console with log level `WARNING` to avoid being suppressed or needing special handling to show. (Anything lower is suppressed bot side.)
  - Implementation details:
    - After `data: gateway.GatewayBot = await self.request(Route("GET", "/gateway/bot"))` in `get_bot_gateway`
      - https://paste.disnake.dev/?id=1660196180710978
- Heavily modified guild caching in relation to <https://github.com/suggestionsbot/suggestions-bot/issues/24>
  - Introduced the variable `guild_ids`
  - Disabled the guild cache even with enabled guild intents
  - Change `state._add_guild_from_data` to not create and cache a guild object
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
- Move thread caching onto `Message`
  - Due to our intents, threads on messages were not being cached correctly which meant features didnt work
  - Fix: Move caching of message.thread onto the message itself


## Notes

On startup even with `Intents.none()` we still receive partial guilds, noted as unavailable (or something like that). This allows for partial cache hits and explains the inconsistencies of bug reproduction as we require a guild who invited the bot during runtime as the first reproduction step.

Versions are bumped to overcome some CI caching issues.

We don't follow or publish to upstream, a shame I know. Security issues however (such as process crashing) are noted exceptions and dealt with on a case by case basis.

