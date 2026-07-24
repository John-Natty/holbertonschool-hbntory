#!/usr/bin/env python3
"""Compatibilité temporaire avec le SDK MCP Python 1.28.x."""

from pydantic import ConfigDict

from mcp.server.fastmcp.utilities.func_metadata import (
    ArgModelBase,
)


def enforce_strict_tool_arguments() -> None:
    """Refuse les arguments MCP inconnus au niveau racine.

    FastMCP 1.28.x génère les modèles d'arguments à partir
    d'ArgModelBase, dont la configuration ignore par défaut
    les propriétés supplémentaires.

    Cette fonction doit être appelée avant l'enregistrement
    des outils afin que les modèles générés héritent de
    extra="forbid".
    """

    current_config = dict(ArgModelBase.model_config)

    current_config["extra"] = "forbid"

    ArgModelBase.model_config = ConfigDict(
        **current_config,
    )
