from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from aiortc import RTCPeerConnection, RTCSessionDescription
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import Settings
from app.detector import YoloDetector
from app.webrtc import YoloVideoTransformTrack


LOGGER = logging.getLogger("webrtc-yolo")
ROOT_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT_DIR / "static"
PEER_CONNECTIONS: set[RTCPeerConnection] = set()


class OfferRequest(BaseModel):
    sdp: str = Field(min_length=1)
    type: Literal["offer"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings.from_env()
    detector = YoloDetector(settings)
    app.state.settings = settings
    app.state.detector = detector
    if settings.preload_model:
        await asyncio.to_thread(detector.load)
    yield
    coroutines = [pc.close() for pc in list(PEER_CONNECTIONS)]
    if coroutines:
        await asyncio.gather(*coroutines, return_exceptions=True)
    PEER_CONNECTIONS.clear()


def create_app() -> FastAPI:
    app = FastAPI(title="WebRTC YOLO Camera", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/health")
    async def health() -> dict[str, object]:
        settings: Settings = app.state.settings
        return {
            "status": "ok",
            "model": settings.model_path,
            "device": "cpu",
            "detectEveryN": settings.detect_every_n,
        }

    @app.post("/offer")
    async def offer(payload: OfferRequest) -> dict[str, str]:
        settings: Settings = app.state.settings
        detector: YoloDetector = app.state.detector
        pc = RTCPeerConnection()
        PEER_CONNECTIONS.add(pc)
        transform_track: YoloVideoTransformTrack | None = None
        detections_channel = None

        @pc.on("connectionstatechange")
        async def on_connectionstatechange() -> None:
            LOGGER.info("WebRTC connection state: %s", pc.connectionState)
            if pc.connectionState in {"failed", "closed", "disconnected"}:
                await pc.close()
                PEER_CONNECTIONS.discard(pc)

        @pc.on("datachannel")
        def on_datachannel(channel):
            nonlocal detections_channel, transform_track
            detections_channel = channel
            if transform_track is not None:
                transform_track.set_data_channel(channel)

            @channel.on("message")
            def on_message(message):
                if message == "ping" and channel.readyState == "open":
                    channel.send("pong")

        @pc.on("track")
        def on_track(track):
            nonlocal transform_track, detections_channel
            LOGGER.info("Track received: %s", track.kind)
            if track.kind == "video":
                transform_track = YoloVideoTransformTrack(track, detector, settings.detect_every_n)
                if detections_channel is not None:
                    transform_track.set_data_channel(detections_channel)
                pc.addTrack(transform_track)

            @track.on("ended")
            async def on_ended() -> None:
                LOGGER.info("Track ended: %s", track.kind)

        try:
            await pc.setRemoteDescription(RTCSessionDescription(sdp=payload.sdp, type=payload.type))
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)
        except Exception as exc:
            await pc.close()
            PEER_CONNECTIONS.discard(pc)
            raise HTTPException(status_code=400, detail=f"Invalid WebRTC offer: {exc}") from exc

        return {
            "sdp": pc.localDescription.sdp,
            "type": pc.localDescription.type,
        }

    return app


app = create_app()

