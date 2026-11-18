"""resources/yaml_loader.py — libyaml-backed YAML loading.

PyYAML's ``safe_load()`` uses the pure-Python parser even when libyaml is
installed. The enemy book alone (~380 KB, 629 entries) takes ~2 s that way
versus ~0.16 s with the C parser, and it is parsed at import time.
``load_yaml()`` picks the C safe loader when available and falls back to the
pure-Python one, so behaviour (and rejected tags) is unchanged.
"""
import yaml

try:
    from yaml import CSafeLoader as _SafeLoader
except ImportError:  # libyaml not available — pure-Python fallback
    from yaml import SafeLoader as _SafeLoader


def load_yaml(handle):
    """Parse one YAML document from an open text handle with the fastest safe loader."""
    return yaml.load(handle, Loader=_SafeLoader)
