"""FastAPI webhook server for external triggers and reminders."""

import asyncio
from datetime import datetime
from typing import Any, Callable, Coroutine

from loguru import logger

try:
    from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False


class WebhookPayload(BaseModel):
    """Incoming webhook payload."""
    event: str
    message: str | None = None
    data: dict[str, Any] | None = None
    session_key: str | None = None


class ReminderPayload(BaseModel):
    """Create reminder payload."""
    title: str
    message: str
    trigger_at: str  # ISO format datetime
    channel: str = "webhook"
    recipient: str
    metadata: dict[str, Any] | None = None


class WebhookResponse(BaseModel):
    """Standard webhook response."""
    success: bool
    message: str
    data: dict[str, Any] | None = None


def create_webhook_app(
    on_message: Callable[[str, str | None], Coroutine[Any, Any, str]] | None = None,
    reminder_service: Any = None,
    api_key: str | None = None
) -> "FastAPI":
    """
    Create a FastAPI app for webhook endpoints.
    
    Args:
        on_message: Callback for processing messages (async fn(message, session_key) -> response).
        reminder_service: ReminderService instance for reminder management.
        api_key: Optional API key for authentication.
    
    Returns:
        Configured FastAPI app.
    """
    if not FASTAPI_AVAILABLE:
        raise RuntimeError("FastAPI not installed. Run: pip install fastapi uvicorn")
    
    app = FastAPI(
        title="Koda Webhook API",
        description="External trigger and reminder API for Koda AI Assistant",
        version="1.0.0"
    )
    
    def verify_api_key(request: Request) -> bool:
        """Verify API key if configured."""
        if not api_key:
            return True
        
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:] == api_key
        
        query_key = request.query_params.get("api_key")
        return query_key == api_key
    
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "ok", "service": "koda", "timestamp": datetime.now().isoformat()}
    
    @app.post("/webhook/trigger", response_model=WebhookResponse)
    async def trigger_webhook(
        payload: WebhookPayload,
        request: Request,
        background_tasks: BackgroundTasks
    ):
        """
        Trigger Koda with a webhook event.
        
        Use this to:
        - Send messages to Koda for processing
        - Trigger automated workflows
        - Integrate external services
        """
        if not verify_api_key(request):
            raise HTTPException(status_code=401, detail="Invalid API key")
        
        if not on_message:
            raise HTTPException(status_code=503, detail="Message handler not configured")
        
        logger.info(f"Webhook triggered: event={payload.event}")
        
        # Build message from event and data
        message = payload.message or f"Webhook event: {payload.event}"
        if payload.data:
            message += f"\nData: {payload.data}"
        
        try:
            # Process asynchronously if long-running
            response = await on_message(message, payload.session_key)
            
            return WebhookResponse(
                success=True,
                message="Processed successfully",
                data={"response": response}
            )
        except Exception as e:
            logger.error(f"Webhook processing failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/webhook/remind", response_model=WebhookResponse)
    async def create_reminder(payload: ReminderPayload, request: Request):
        """
        Create a new reminder via webhook.
        
        The reminder will be sent at the specified time via the chosen channel.
        """
        if not verify_api_key(request):
            raise HTTPException(status_code=401, detail="Invalid API key")
        
        if not reminder_service:
            raise HTTPException(status_code=503, detail="Reminder service not configured")
        
        try:
            trigger_at = datetime.fromisoformat(payload.trigger_at)
            
            reminder = reminder_service.add_reminder(
                title=payload.title,
                message=payload.message,
                trigger_at=trigger_at,
                channel=payload.channel,
                recipient=payload.recipient,
                metadata=payload.metadata
            )
            
            return WebhookResponse(
                success=True,
                message="Reminder created",
                data={
                    "id": reminder.id,
                    "trigger_at": datetime.fromtimestamp(reminder.trigger_at_ms / 1000).isoformat()
                }
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid datetime format: {e}")
        except Exception as e:
            logger.error(f"Failed to create reminder: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/webhook/reminders", response_model=WebhookResponse)
    async def list_reminders(request: Request, pending_only: bool = True):
        """List all reminders."""
        if not verify_api_key(request):
            raise HTTPException(status_code=401, detail="Invalid API key")
        
        if not reminder_service:
            raise HTTPException(status_code=503, detail="Reminder service not configured")
        
        reminders = reminder_service.list_reminders(pending_only=pending_only)
        
        return WebhookResponse(
            success=True,
            message=f"Found {len(reminders)} reminders",
            data={
                "reminders": [
                    {
                        "id": r.id,
                        "title": r.title,
                        "message": r.message,
                        "trigger_at": datetime.fromtimestamp(r.trigger_at_ms / 1000).isoformat(),
                        "channel": r.channel.value,
                        "recipient": r.recipient,
                        "sent": r.sent
                    }
                    for r in reminders
                ]
            }
        )
    
    @app.delete("/webhook/reminders/{reminder_id}", response_model=WebhookResponse)
    async def delete_reminder(reminder_id: str, request: Request):
        """Delete a reminder by ID."""
        if not verify_api_key(request):
            raise HTTPException(status_code=401, detail="Invalid API key")
        
        if not reminder_service:
            raise HTTPException(status_code=503, detail="Reminder service not configured")
        
        if reminder_service.remove_reminder(reminder_id):
            return WebhookResponse(success=True, message="Reminder deleted")
        
        raise HTTPException(status_code=404, detail="Reminder not found")
    
    @app.post("/webhook/agent", response_model=WebhookResponse)
    async def agent_message(request: Request):
        """
        Send a raw message to the agent.
        
        Body should be JSON with 'message' field.
        """
        if not verify_api_key(request):
            raise HTTPException(status_code=401, detail="Invalid API key")
        
        if not on_message:
            raise HTTPException(status_code=503, detail="Message handler not configured")
        
        try:
            body = await request.json()
            message = body.get("message", "")
            session_key = body.get("session_key", "webhook:default")
            
            if not message:
                raise HTTPException(status_code=400, detail="Message required")
            
            response = await on_message(message, session_key)
            
            return WebhookResponse(
                success=True,
                message="Processed",
                data={"response": response}
            )
        except Exception as e:
            logger.error(f"Agent message failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    return app


class WebhookServer:
    """Webhook server manager."""
    
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8080,
        on_message: Callable[[str, str | None], Coroutine[Any, Any, str]] | None = None,
        reminder_service: Any = None,
        api_key: str | None = None
    ):
        self.host = host
        self.port = port
        self.on_message = on_message
        self.reminder_service = reminder_service
        self.api_key = api_key
        self._server = None
        self._task = None
    
    async def start(self) -> None:
        """Start the webhook server."""
        if not FASTAPI_AVAILABLE:
            logger.warning("FastAPI not installed, webhook server disabled")
            return
        
        import uvicorn
        
        app = create_webhook_app(
            on_message=self.on_message,
            reminder_service=self.reminder_service,
            api_key=self.api_key
        )
        
        config = uvicorn.Config(
            app,
            host=self.host,
            port=self.port,
            log_level="info"
        )
        self._server = uvicorn.Server(config)
        
        logger.info(f"Starting webhook server on {self.host}:{self.port}")
        self._task = asyncio.create_task(self._server.serve())
    
    async def stop(self) -> None:
        """Stop the webhook server."""
        if self._server:
            self._server.should_exit = True
            if self._task:
                await self._task
            logger.info("Webhook server stopped")
