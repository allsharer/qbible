package org.qbible.core

/**
 * Expected, user-reportable errors. Each carries a user-facing message and the
 * same machine [code] as the desktop app (`qbible/errors.py`), so the shared
 * test vectors in `spec/` can compare them.
 */
open class QBibleException(val code: String, message: String) : Exception(message)

open class ReferenceException(code: String, message: String) : QBibleException(code, message)

class ReferenceSyntaxException(message: String) : ReferenceException("reference_syntax", message)

class UnknownBookException(message: String, val candidates: List<Book> = emptyList()) :
    ReferenceException("unknown_book", message)

class InvalidChapterException(message: String) : ReferenceException("invalid_chapter", message)

class InvalidVerseException(message: String) : ReferenceException("invalid_verse", message)

class SearchQueryException(message: String) : QBibleException("invalid_search", message)

class DataException(message: String) : QBibleException("data_error", message)

class UserDataException(message: String) : QBibleException("user_data_error", message)

class NotFoundException(message: String) : QBibleException("not_found", message)
