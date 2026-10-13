"""Exception hierarchy shared by every qbible interface.

Each error carries a user-facing message. Interfaces translate the class into
an exit code (CLI) or HTTP status (server); they never show tracebacks for
these errors.
"""


class QBibleError(Exception):
    """Base class for expected, user-reportable errors."""

    code = "error"


class ReferenceError_(QBibleError):
    """Base class for problems with a scripture reference."""

    code = "invalid_reference"


class ReferenceSyntaxError(ReferenceError_):
    code = "reference_syntax"


class UnknownBookError(ReferenceError_):
    code = "unknown_book"

    def __init__(self, message, candidates=()):
        super().__init__(message)
        self.candidates = tuple(candidates)


class InvalidChapterError(ReferenceError_):
    code = "invalid_chapter"


class InvalidVerseError(ReferenceError_):
    code = "invalid_verse"


class SearchQueryError(QBibleError):
    code = "invalid_search"


class TranslationNotFoundError(QBibleError):
    code = "translation_not_found"


class DataError(QBibleError):
    """The Bible data is missing, unreadable or fails validation."""

    code = "data_error"


class UserDataError(QBibleError):
    code = "user_data_error"


class NotFoundError(QBibleError):
    code = "not_found"
