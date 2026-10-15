from fastapi import APIRouter
from pydantic import BaseModel

from api.config import settings
from api.services.alerts import build_alert_payload, dispatch_webhook

router = APIRouter(prefix="/alerts", tags=["alerts"])


class TestWebhookRequest(BaseModel):
    webhook_url: str


class TestWebhookResponse(BaseModel):
    success: bool
    error: str | None = None


@router.post("/test", response_model=TestWebhookResponse)
async def test_webhook(request: TestWebhookRequest) -> TestWebhookResponse:
    """Dispatches a test notification ping to verify webhook connectivity.

    Args:
        request: TestWebhookRequest containing the target webhook_url.

    Returns:
        TestWebhookResponse with success boolean and optional error message.
    """
    url = request.webhook_url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        return TestWebhookResponse(
            success=False,
            error="Invalid URL format. Must start with http:// or https://",
        )

    summary_stats = {
        "active": 1,
        "warning": 0,
        "failed": 0,
        "ghost": 0,
        "void": 0,
    }
    payload = build_alert_payload(
        webhook_url=url,
        schedule_name="Site Health Check - Webhook Test",
        run_id="test-ping",
        timestamp_str="Just now",
        triggers=["Webhook verification ping successful"],
        summary_stats=summary_stats,
        table_url=f"{settings.app_base_url}/",
        is_healthy=True,
    )

    success, err = await dispatch_webhook(url, payload)
    return TestWebhookResponse(success=success, error=err)
