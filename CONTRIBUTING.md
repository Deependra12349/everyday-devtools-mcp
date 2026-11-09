# Contributing

Thanks for helping improve Everyday DevTools MCP!

## Ground rules

1. **Zero dependencies.** Only the Python standard library — this is the
   project's main promise.
2. **Offline only.** Tools must never make network calls.
3. **Small and sharp.** One tool = one clear job, with a short description.

## Adding a tool

1. Add the implementation function in `everyday_devtools_mcp/server.py`.
2. Register it in the `TOOLS` dict with a description and JSON schema.
3. Add a check for it in `tests/test_mcp.py`.
4. Run the test before opening a PR:

   ```bash
   python tests/test_mcp.py
   ```

5. Add a row for the tool in the README table.

## Reporting bugs

Open an issue with the tool name, the input you gave, what you expected
and what you got. A failing case from `tests/test_mcp.py` is perfect.
