from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from web.local_clipboard import ClipboardUnavailableError, copy_text_to_system_clipboard

router = APIRouter(prefix="/api/local", tags=["local"])


class ClipboardRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(max_length=5 * 1024 * 1024)


@router.post("/clipboard")
def copy_to_clipboard(payload: ClipboardRequest) -> dict[str, bool]:
    try:
        copy_text_to_system_clipboard(payload.text)
    except ClipboardUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return {"copied": True}
