# Everyday DevTools MCP

**17 tiny tools your AI assistant wishes it had** — Base64, JSON, JWT, UUID,
hashing, cron, regex, passwords, timestamps and more.
One MCP server. **Zero dependencies. No API keys. Works offline.**

Works with **Claude Code, Cursor, VS Code, Windsurf** and any MCP client.

## Install

```bash
pip install everyday-devtools-mcp
```

## Connect it

**Claude Code**

```bash
claude mcp add devtools -- everyday-devtools-mcp
```

**Cursor / VS Code / Windsurf** — add to your MCP config (`mcp.json` / `settings`):

```json
{
  "mcpServers": {
    "devtools": {
      "command": "everyday-devtools-mcp"
    }
  }
}
```

Then just ask your assistant things like:

- *"Decode this JWT and tell me when it expires"*
- *"What are the next 5 runs of cron `0 9 * * 1`?"*
- *"Hash this string with SHA-256"*
- *"Make me a 24-character password"*

## Tools

| Tool | What it does |
|---|---|
| `base64_encode` / `base64_decode` | Text ⇄ Base64 |
| `url_encode` / `url_decode` | Percent-encode / decode URLs |
| `uuid_generate` | Random UUID v4 (1–100 at once) |
| `hash_text` | MD5 / SHA-1 / SHA-256 / SHA-512 |
| `json_format` / `json_minify` | Validate + pretty-print or minify JSON |
| `jwt_decode` | Read a JWT header/payload, flag expiry (no signature check) |
| `timestamp_convert` | Unix ⇄ human date, seconds or milliseconds |
| `cron_next` | Next run times for any 5-field cron expression |
| `regex_test` | Test a pattern, list all matches |
| `password_generate` | Cryptographically secure strong passwords |
| `slugify` | Text → URL slug |
| `case_convert` | upper / lower / Title / snake / kebab / camel |
| `color_convert` | Hex ⇄ RGB |
| `text_stats` | Characters, words, lines, sentences |

## Why another dev-tools server?

- **Nothing to install besides the package itself** — pure Python standard
  library, no Docker, no Node, no network calls.
- **Fast to start, safe to run** — everything happens locally on your machine.
- **Honest scope** — small sharp tools, each covered by an end-to-end test
  that speaks the real MCP protocol to the server.

## Development

```bash
git clone https://github.com/Deependra12349/everyday-devtools-mcp
cd everyday-devtools-mcp
python tests/test_mcp.py   # spawns the server, runs protocol checks
```

## Contributing

Issues and PRs welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).
New tool ideas are especially welcome if they are small, offline and
dependency-free.

## License

MIT — see [LICENSE](LICENSE).

*Maintained by Deependra, with AI assistance for implementation.
Every tool is verified by the automated protocol test in `tests/`.*
