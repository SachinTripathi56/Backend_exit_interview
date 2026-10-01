"""
Application exceptions and standardized error codes.

Every error returned by the API follows this shape:

    {
      "error": {
        "code": "INTERVIEW_NOT_AVAILABLE",
        "message": "Your interview is not currently available."
      }
    }

Raise `AppError` (or a subclass) anywhere in business logic / services and the
global exception handler registered in main.py will convert it to the
standardized response with the right HTTP status code.
"""
from enum import Enum

from fastapi import status


class ErrorCode(str, Enum):
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    CONFLICT = "CONFLICT"
    INTERVIEW_NOT_AVAILABLE = "INTERVIEW_NOT_AVAILABLE"
    INTERVIEW_ALREADY_COMPLETED = "INTERVIEW_ALREADY_COMPLETED"
    CAMPAIGN_EXPIRED = "CAMPAIGN_EXPIRED"
    CAMPAIGN_INVALID_SCHEDULE = "CAMPAIGN_INVALID_SCHEDULE"
    IMPORT_VALIDATION_FAILED = "IMPORT_VALIDATION_FAILED"
    UNSUPPORTED_FILE_TYPE = "UNSUPPORTED_FILE_TYPE"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    AI_SERVICE_ERROR = "AI_SERVICE_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AppError(Exception):
    """Base application error. Carries an HTTP status + standardized code."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: ErrorCode = ErrorCode.VALIDATION_ERROR

    def __init__(self, message: str, *, code: ErrorCode | None = None, status_code: int | None = None):
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        super().__init__(message)


class UnauthorizedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = ErrorCode.UNAUTHORIZED

    def __init__(self, message: str = "Authentication is required."):
        super().__init__(message)


class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = ErrorCode.FORBIDDEN

    def __init__(self, message: str = "You do not have permission to perform this action."):
        super().__init__(message)


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = ErrorCode.NOT_FOUND

    def __init__(self, message: str = "The requested resource was not found."):
        super().__init__(message)


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = ErrorCode.CONFLICT

    def __init__(self, message: str = "The request conflicts with the current state of the resource."):
        super().__init__(message)


class ValidationAppError(AppError):
    status_code = 422
    code = ErrorCode.VALIDATION_ERROR

    def __init__(self, message: str = "The request failed validation."):
        super().__init__(message)


class InterviewNotAvailableError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = ErrorCode.INTERVIEW_NOT_AVAILABLE

    def __init__(self, message: str = "Your interview is not currently available."):
        super().__init__(message)


class InterviewAlreadyCompletedError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = ErrorCode.INTERVIEW_ALREADY_COMPLETED

    def __init__(self, message: str = "This interview has already been completed."):
        super().__init__(message)


class CampaignExpiredError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = ErrorCode.CAMPAIGN_EXPIRED

    def __init__(self, message: str = "This campaign has expired."):
        super().__init__(message)


class CampaignInvalidScheduleError(AppError):
    status_code = 422
    code = ErrorCode.CAMPAIGN_INVALID_SCHEDULE

    def __init__(self, message: str = "Campaign start_at must be before end_at."):
        super().__init__(message)


class AIServiceError(AppError):
    status_code = 502
    code = ErrorCode.AI_SERVICE_ERROR

    def __init__(self, message: str = "The AI interview service is currently unavailable."):
        super().__init__(message)


class UnsupportedFileTypeError(AppError):
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    code = ErrorCode.UNSUPPORTED_FILE_TYPE

    def __init__(self, message: str = "This file type is not supported."):
        super().__init__(message)


class FileTooLargeError(AppError):
    status_code = 413
    code = ErrorCode.FILE_TOO_LARGE

    def __init__(self, message: str = "The uploaded file is too large."):
        super().__init__(message)


class ImportValidationFailedError(AppError):
    status_code = 422
    code = ErrorCode.IMPORT_VALIDATION_FAILED

    def __init__(self, message: str = "The uploaded file could not be validated."):
        super().__init__(message)
