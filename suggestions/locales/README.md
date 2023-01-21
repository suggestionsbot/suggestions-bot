Command Locales
---

Please see [this](https://github.com/suggestionsbot/suggestions-bot-rewrite/issues/9) issue.

---

Files are expected in the following format:

```json
{
    "<COMMAND>_NAME": "The name of the command",
    "<COMMAND>_DESCRIPTION": "The description of the command",
    "<COMMAND>_ARG_<ARGUMENT>_NAME": "The name of this argument",
    "<COMMAND>_ARG_<ARGUMENT>_DESCRIPTION": "The description of this argument",
    "<COMMAND>_INNER_<KEY>": "The value for this key."
}
```

- `_ARG_` is reserved for all parameters to the provided method
- `_INNER_` is reserved for all strings sent within the method itself

## Variables

The following variables *should* be available to all translations:

- `$CHANNEL_ID` - The id for the channel this command was executed in
- `$AUTHOR_ID` - The id for the author who executed this command
- `$GUILD_ID` - The id for the guild this command was executed in

### Extra Values

Certain translations require non-standard values, please refer to the code
or existing `en_GB` translation to see what these values are.

#### Guild Configuration Values

All values within the `objects.GuildConfig` class are available as
`$GUILD_CONFIG_<FIELD>` where the field is the uppercase variable name.

**Note:** *These values will not be available for all translations*

#### User Configuration Values

All values within the `objects.UserConfig` class are available as
`$USER_CONFIG_<FIELD>` where the field is the uppercase variable name.

**Note:** *These values will not be available for all translations*