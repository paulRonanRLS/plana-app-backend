from pydantic import BaseModel


class ErrorDetail(BaseModel):
    """Structured error details for client-friendly error messages."""
    ocr_confidence: str | None = None
    suggestion: str | None = None


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: ErrorDetail | None = None


class ErrorWrapper(BaseModel):
    error: ErrorResponse
