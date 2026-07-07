# TerryGPT Phase 1 Security

## Local By Default

The API host is `127.0.0.1` in `config/default.toml`.

That means the API listens on the local PC by default.

## API Token

IntelisAi Studio creates a local token file at:

```text
data/secrets.toml
```

Do not share this file.

## Dangerous Actions

The security service marks these actions as requiring confirmation:

1. Delete file.
2. Delete folder.
3. Run terminal command.
4. Download executable.
5. Install software.
6. Send email.

Phase 1 does not execute those actions.

## Remote Access

Phase 1 does not expose IntelisAi Studio to the public internet.

Remote phone access should be added later with a private network tool such as Tailscale.

