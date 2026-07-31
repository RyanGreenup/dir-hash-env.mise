# mise deterministic-port

A [mise environment plugin](https://mise.jdx.dev/env-plugin-development.html)
that assigns stable, project-specific ports from the SHA-256 hash of the project
directory.

By default it sets `PORT` to a value in the inclusive range 20000–39999. The
same directory always produces the same port, matching this TypeScript logic:

```ts
const hash = createHash("sha256").update(projectDirectory).digest().readUInt16BE(0)
const port = 20_000 + (hash % 20_000)
```

## Installation

Install the plugin from its Git repository (replace the URL with the repository
where you publish it):

```sh
mise plugins install deterministic-port https://github.com/OWNER/REPOSITORY.git
```

For local development, link this checkout instead:

```sh
mise plugins link deterministic-port "$PWD"
```

## Usage

Enable the default `PORT` variable in a project's `mise.toml`:

```toml
[env]
_.deterministic-port = {}
```

Set a different variable name:

```toml
[env]
_.deterministic-port = { key = "DEV_PORT" }
```

Set several consecutive, wrapping ports from the same project hash:

```toml
[env]
_.deterministic-port = { keys = ["WEB_PORT", "API_PORT", "DB_PORT"] }
```

The first key receives the hashed port. Later keys receive the following ports,
wrapping within the configured range, so one plugin activation never assigns the
same port twice.

### Options

| Option | Default | Description |
| --- | --- | --- |
| `key` | `"PORT"` | A single environment variable name. Ignored when `keys` is set. |
| `keys` | unset | A non-empty array of environment variable names. |
| `range_start` | `20000` | First port in the allocation range. |
| `range_size` | `20000` | Number of ports in the allocation range. |
| `path` | `$MISE_PROJECT_ROOT` | Hash input override. Falls back to `$PWD` when mise does not expose a project root. |

The configured range must fit within valid TCP/UDP ports (`1`–`65535`) and be
large enough for every requested key. The runtime needs either `sha256sum`
(common on Linux) or `shasum` (included with macOS).

Inspect the result with:

```sh
mise env | grep PORT
mise exec -- env | grep PORT
```

## Development

```sh
mise install
mise run lint
```
