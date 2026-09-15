from pydantic import BaseModel

class ErrorBody(BaseModel):
    code: str; message: str; details: str | None = None; retryable: bool = False
class ErrorResponse(BaseModel):
    success: bool = False; error: ErrorBody
class PreflightCheck(BaseModel):
    name: str; status: str; message: str | None = None; critical: bool = False
class PreflightResponse(BaseModel):
    ready: bool; checks: list[PreflightCheck]
