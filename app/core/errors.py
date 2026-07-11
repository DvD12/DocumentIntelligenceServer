class DocIntelError(Exception):
    """Errors safe to surface to agents/UI as actionable guidance."""

    code = "error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ParseError(DocIntelError):
    code = "parse_error"


class UnknownTagsError(DocIntelError):
    code = "unknown_tags"


class UnknownDocumentsError(DocIntelError):
    code = "unknown_documents"


class StoreUnavailableError(DocIntelError):
    code = "store_unavailable"
