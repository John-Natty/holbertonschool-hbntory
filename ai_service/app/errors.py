"""Exceptions locales du client MCP du service IA."""


class MCPClientError(Exception):
    """Classe de base des erreurs MCP attendues."""


class MCPConnectionError(MCPClientError):
    """Signale que la session MCP n'est pas disponible."""


class MCPTimeoutError(MCPClientError):
    """Signale le dépassement du délai d'un échange MCP."""


class MCPProtocolError(MCPClientError):
    """Signale une réponse incompatible avec le protocole attendu."""


class MCPToolNotFoundError(MCPProtocolError):
    """Signale l'absence d'un outil MCP obligatoire."""


class MCPInvalidArgumentError(MCPClientError):
    """Signale des arguments refusés avant tout appel MCP."""


class MCPToolResponseError(MCPClientError):
    """Représente une erreur métier structurée retournée par un outil."""

    def __init__(
        self,
        tool_name: str,
        code: str,
    ) -> None:
        """Conserve uniquement les informations métier sûres."""

        self.tool_name = tool_name
        self.code = code
        self.message = "L'outil MCP a signalé une erreur métier."

        super().__init__(
            f"{self.message} Outil : {tool_name}. Code : {code}."
        )


class IntentClassifierError(Exception):
    """Classe de base des erreurs attendues du classificateur."""


class IntentClassifierUnavailableError(IntentClassifierError):
    """Signale que le fournisseur de classification est indisponible."""


class IntentClassifierTimeoutError(IntentClassifierError):
    """Signale le dépassement du délai de classification."""


class IntentClassifierResponseError(IntentClassifierError):
    """Signale une réponse de classification invalide."""


class NVIDIAClientError(Exception):
    """Classe de base des erreurs NVIDIA attendues et nettoyées."""


class NVIDIATimeoutError(NVIDIAClientError):
    """Signale le dépassement du délai d'un appel NVIDIA."""


class NVIDIAConnectionError(NVIDIAClientError):
    """Signale une erreur réseau avant toute réponse NVIDIA."""


class NVIDIAAuthenticationError(NVIDIAClientError):
    """Signale le refus des informations d'authentification."""


class NVIDIARateLimitError(NVIDIAClientError):
    """Signale que le quota ou le débit autorisé est dépassé."""


class NVIDIAServiceError(NVIDIAClientError):
    """Signale un statut HTTP non réussi retourné par NVIDIA."""


class NVIDIAResponseError(NVIDIAClientError):
    """Signale une réponse NVIDIA vide ou structurellement invalide."""


class GeneratedAnswerError(Exception):
    """Signale une rédaction générée invalide ou insuffisamment ancrée."""
