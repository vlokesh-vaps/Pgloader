class AppError(Exception):
    def __init__(self, code: str, message: str, details: str | None = None, retryable: bool = False):
        self.code, self.message, self.details, self.retryable = code, message, details, retryable
        super().__init__(message)

class ConnectionTestError(AppError): pass
class MetadataFetchError(AppError): pass
class PreflightError(AppError): pass
class PgloaderExecutionError(AppError): pass
class MigrationAlreadyRunningError(AppError): pass
class MigrationCancelledError(AppError): pass
class AssessmentError(AppError): pass
