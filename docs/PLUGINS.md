# Phase 1 Plugins

## Plugin Folder Shape

Each plugin lives in its own folder:

```text
plugins/plugin_name
```

Each plugin folder must contain:

1. `manifest.json`
2. `plugin.py`

## Manifest

```json
{
  "name": "hello_terry",
  "version": "1.0.0",
  "description": "A working sample plugin."
}
```

## Python Entry Point

`plugin.py` must define:

```python
def create_plugin():
    return YourPlugin()
```

The plugin object must have a `commands()` method.

That method returns command names and functions.

## Included Plugin

Phase 1 includes:

```text
plugins/hello_terry
```

It provides:

1. `hello`
2. `utc_time`

