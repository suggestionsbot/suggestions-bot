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