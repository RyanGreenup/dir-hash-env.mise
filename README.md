# Mise Deterministic Port Env Plugin

A [mise environment plugin](https://mise.jdx.dev/env-plugin-development.html) to
assigns stable ports to environment variables from a SHA-256 hash of the project
directory. By default, the plugin sets `PORT` to a value from `20000` through
`39999`. The same project path always produces the same port.

## Requirements

The plugin has these requirements:

- mise `2025.1.0` or later.
- A POSIX-compatible shell.
- `sha256sum` or `shasum`.

Linux systems commonly include `sha256sum`. macOS includes `shasum`.

## Installation

Install the plugin from its Git repository:

```sh
mise plugins install deterministic-port https://github.com/ryangreenup/dir-hash-env.mise.git
```

For local development, link the plugin checkout:

```sh
mise plugins link deterministic-port "$PWD"
```

## Quick start

> [!NOTE]
> Using the `[[env]]` syntax, later values win, allowing a fallback.

1. Add the plugin to the `[env]` section of the project `mise.toml` file:

   ```toml
   [[env]]
   '_'.file = { path = ".env.yaml" }

   [[env]]
   # Defaults to PORT otherwise
   _.deterministic-port = { key = "DEV_PORT" }
   [env]
   _.deterministic-port = { keys = ["WEB_PORT", "API_PORT", "DB_PORT"] }
   ```

2. Display the assigned port:

   ```sh
   mise env | grep DEV_PORT
   ```

3. Run a command with the assigned port in its environment:

   ```sh
   mise exec -- env | grep DEV_PORT
   ```

> [!TIP]
> One can acheive this without the plugin, see [^c9baea1]

[^c9baea1]:
    ```toml

    [vars]
    project_port_base = """
    {%- set path_hash = config_root | hash(len=8) -%}
    {{- exec(
    command="printf '%s' $((10000 + (0x" ~ path_hash ~ " % 19997)))"
    ) | trim -}}
    """

    [[env]]
    '_'.file = { path = ".env.yaml" }

    [[env]]
    VITE_DEV_PORT = "{{ vars.project_port_base | int + 1 }}"
    VITE_PROD_PORT = "{{ vars.project_port_base | int + 2 }}"
    PGPORT = "{{ vars.project_port_base | int + 3 }}"
    ```

    this example

## Configuration

### Overview

1. default env var of `PORT`
   ```toml
   [env]
   _.deterministic-port = { }
   ```
2. Single
   ```toml
   [env]
   _.deterministic-port = { key = "DEV_PORT" }
   ```
3. Multiple

   ```toml
   [env]
   _.deterministic-port = { keys = ["WEB_PORT", "API_PORT", "DB_PORT"] }
   ```

### Set multiple variables

Use `keys` to set multiple environment variables:

```toml
[env]
_.deterministic-port = { keys = ["WEB_PORT", "API_PORT", "DB_PORT"] }
```

> [!NOTE]
> The `keys` option takes precedence over `key`.

The first variable receives the hashed port. Each later variable receives the
next port in the configured range.

The allocation returns to the start after it reaches the end of the range. One
activation assigns a different port to each array entry.

Use a unique environment variable name for each entry.

### Set the port range

Use `range_start` and `range_size` to set a different port range:

```toml
[env]
_.deterministic-port = {
  keys = ["WEB_PORT", "API_PORT"],
  range_start = 40000,
  range_size = 1000,
}
```

This example assigns ports from `40000` through `40999`.

### Set the hash input

#### Specific

Use `path` to replace the detected project path:

```toml
[env]
_.deterministic-port = { path = "/shared/project-name" }
```

The plugin selects the hash input in this order:

1. The `path` value in the plugin configuration.
2. The `MISE_PROJECT_ROOT` environment variable.
3. The `PWD` environment variable.

### Resolve a port collision

Use `salt` to derive a different port without renaming or moving the project:

```toml
[env]
_.deterministic-port = { salt = "1" }
```

The same project path and salt always produce the same port. If that port also
collides, change the salt to another string. An empty salt is equivalent to not
setting `salt`.

#### Mise.toml Config Directory Directory

```toml
[env]
_.deterministic-port = { path = "{{ config_root }}" }
```

## Configuration reference

| Option        | Default               | Description                                                                               |
| ------------- | --------------------- | ----------------------------------------------------------------------------------------- |
| `key`         | `"PORT"`              | Sets one environment variable.                                                            |
| `keys`        | Not set               | Sets a non-empty array of environment variables. This option takes precedence over `key`. |
| `range_start` | `20000`               | Sets the first port in the range.                                                         |
| `range_size`  | `20000`               | Sets the number of ports in the range.                                                    |
| `path`        | Detected project path | Replaces the path that the plugin hashes.                                                 |
| `salt`        | `""`                  | Derives another deterministic port without changing the project path.                     |

Each environment variable name must match `[A-Za-z_][A-Za-z0-9_]*`. The
`range_start` value must be from `1` through `65535`.

The range must contain at least one port for each entry in `keys`. The last port
in the range must not be more than `65535`.

## Port calculation

Without a salt, the plugin calculates SHA-256 for the selected project path. A
non-empty salt changes the hash input to the project path, a NUL byte, and the
salt. It reads the first 16 bits of the digest as an unsigned integer.

The calculation matches this TypeScript snippet:

```ts
const rangeStart = 20_000;
const rangeSize = 20_000;

const hash = createHash("sha256")
  .update(projectDirectory)
  .digest()
  .readUInt16BE(0);

const port = rangeStart + (hash % rangeSize);
```

For a non-empty salt, the equivalent hash input is
`.update(projectDirectory).update("\0").update(salt)`.

For multiple variables, it adds the array index to the first offset.

## Limits

- The plugin does not reserve a port or detect a port that another process uses.
  - If a port is not available, set `salt` to a string such as `"1"`. You can
    also select a different range or set an explicit `path` value.
- Theoretically different project paths can receive the same port, but it's
  unlikely.
- A moved / renamed project will receive a different port.
- Duplicate names in `keys` can overwrite an earlier value.

## Troubleshooting

### The hash command is missing

If the plugin reports that it requires `sha256sum` or `shasum`, install one of
these programs.

### The project path is missing

If mise cannot provide a project path, set the `path` option in the plugin
configuration.

### The port range is invalid

Make sure that the range starts at a valid port. Make sure that the range ends
at or before `65535`.

Make sure that `range_size` is not less than the number of entries in `keys`.

### An environment variable name is invalid

Use a name that starts with a letter or an underscore. Use only letters,
numbers, and underscores after the first character.

## Development

Install the development tools:

```sh
mise install
```

Run all lint checks:

```sh
mise run lint
```

Run the test suite in an Alpine container with Podman:

```sh
mise test
```

Run the Python integration suite directly in the current environment:

```sh
mise run test:python
```

Fix supported lint errors:

```sh
mise run lint-fix
```

### Releases

Releases follow semantic versioning. Before merging a release-producing change
to `main`, update `PLUGIN.version` in `metadata.lua` to a version that has not
been tagged.

Every PR and push to `main` runs tests and afterward a release is cut and tagged
(`v<version>`) with generated release notes.

The release job fails when the metadata version already has a tag, preventing an
existing release from being replaced.
