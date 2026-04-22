const remoteVideo = document.querySelector("#remoteVideo");
const startButton = document.querySelector("#startButton");
const stopButton = document.querySelector("#stopButton");
const flipButton = document.querySelector("#flipButton");
const connectionState = document.querySelector("#connectionState");
const statusBadge = document.querySelector(".status");
const fpsValue = document.querySelector("#fpsValue");
const latencyValue = document.querySelector("#latencyValue");
const countValue = document.querySelector("#countValue");
const frameValue = document.querySelector("#frameValue");
const detectionsList = document.querySelector("#detectionsList");

let localStream = null;
let peerConnection = null;
let dataChannel = null;
let currentFacingMode = "user";
let currentDeviceId = null;
let isFlippingCamera = false;

startButton.addEventListener("click", startSession);
stopButton.addEventListener("click", stopSession);
flipButton.addEventListener("click", flipCamera);

async function startSession() {
  setControls(true);
  setState("camera");

  try {
    localStream = await getCameraStream({
      facingMode: currentFacingMode,
      exactFacingMode: false,
    });
    rememberCamera(localStream.getVideoTracks()[0]);

    peerConnection = new RTCPeerConnection({
      iceServers: [{ urls: "stun:stun.l.google.com:19302" }],
    });

    peerConnection.addEventListener("connectionstatechange", () => {
      setState(peerConnection.connectionState);
      if (["failed", "closed"].includes(peerConnection.connectionState)) {
        stopSession();
      }
    });

    peerConnection.addEventListener("track", (event) => {
      if (event.track.kind === "video") {
        remoteVideo.srcObject = event.streams[0] || new MediaStream([event.track]);
      }
    });

    dataChannel = peerConnection.createDataChannel("detections", {
      ordered: false,
      maxRetransmits: 0,
    });
    dataChannel.addEventListener("open", () => dataChannel.send("ping"));
    dataChannel.addEventListener("message", (event) => handleDetectionMessage(event.data));

    localStream.getTracks().forEach((track) => peerConnection.addTrack(track, localStream));

    const offer = await peerConnection.createOffer();
    await peerConnection.setLocalDescription(offer);
    await waitForIceGathering(peerConnection);

    const response = await fetch("/offer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(peerConnection.localDescription),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }

    const answer = await response.json();
    await peerConnection.setRemoteDescription(answer);
    setControls(true);
  } catch (error) {
    console.error(error);
    setState("failed");
    alert(`Could not start camera session: ${error.message}`);
    stopSession();
  }
}

async function flipCamera() {
  if (!localStream || !peerConnection || isFlippingCamera) {
    return;
  }

  const sender = peerConnection.getSenders().find((candidate) => candidate.track?.kind === "video");
  const oldTrack = sender?.track || localStream.getVideoTracks()[0];
  if (!sender || !oldTrack) {
    return;
  }

  isFlippingCamera = true;
  setControls(true);

  let nextStream = null;
  try {
    const nextFacingMode = currentFacingMode === "environment" ? "user" : "environment";
    nextStream = await getReplacementCameraStream(oldTrack, nextFacingMode);
    const nextTrack = nextStream.getVideoTracks()[0];
    if (!nextTrack) {
      throw new Error("No video track returned by the camera");
    }

    await sender.replaceTrack(nextTrack);
    localStream.removeTrack(oldTrack);
    oldTrack.stop();
    localStream.addTrack(nextTrack);
    rememberCamera(nextTrack, nextFacingMode);
    nextStream = null;
  } catch (error) {
    if (nextStream) {
      nextStream.getTracks().forEach((track) => track.stop());
    }
    console.error(error);
    alert(`Could not flip camera: ${error.message}`);
  } finally {
    isFlippingCamera = false;
    setControls(Boolean(peerConnection));
  }
}

function stopSession() {
  if (dataChannel) {
    dataChannel.close();
    dataChannel = null;
  }
  if (peerConnection) {
    peerConnection.close();
    peerConnection = null;
  }
  if (localStream) {
    localStream.getTracks().forEach((track) => track.stop());
    localStream = null;
  }
  remoteVideo.srcObject = null;
  currentDeviceId = null;
  isFlippingCamera = false;
  setControls(false);
  setState("idle");
}

function getCameraStream({ facingMode, exactFacingMode = true, deviceId } = {}) {
  return navigator.mediaDevices.getUserMedia({
    audio: false,
    video: getVideoConstraints({ facingMode, exactFacingMode, deviceId }),
  });
}

function getVideoConstraints({ facingMode, exactFacingMode, deviceId } = {}) {
  const constraints = {
    width: { ideal: 960 },
    height: { ideal: 540 },
    frameRate: { ideal: 24, max: 30 },
  };

  if (deviceId) {
    constraints.deviceId = { exact: deviceId };
  } else if (facingMode) {
    constraints.facingMode = exactFacingMode ? { exact: facingMode } : { ideal: facingMode };
  }

  return constraints;
}

async function getReplacementCameraStream(oldTrack, nextFacingMode) {
  try {
    const stream = await getCameraStream({ facingMode: nextFacingMode });
    if (!isSameCamera(oldTrack, stream.getVideoTracks()[0])) {
      return stream;
    }
    stream.getTracks().forEach((track) => track.stop());
  } catch {
    // Device enumeration below covers browsers that do not honor facingMode consistently.
  }

  const nextDeviceId = await getNextCameraDeviceId(oldTrack);
  if (!nextDeviceId) {
    throw new Error("No alternate camera found");
  }
  return getCameraStream({ deviceId: nextDeviceId });
}

async function getNextCameraDeviceId(oldTrack) {
  if (!navigator.mediaDevices?.enumerateDevices) {
    return null;
  }

  const cameras = (await navigator.mediaDevices.enumerateDevices()).filter(
    (device) => device.kind === "videoinput",
  );
  if (cameras.length < 2) {
    return null;
  }

  const oldDeviceId = oldTrack.getSettings?.().deviceId || currentDeviceId;
  const currentIndex = cameras.findIndex((camera) => camera.deviceId === oldDeviceId);
  const nextIndex = currentIndex >= 0 ? (currentIndex + 1) % cameras.length : 0;
  return cameras[nextIndex].deviceId;
}

function isSameCamera(oldTrack, newTrack) {
  if (!oldTrack || !newTrack) {
    return false;
  }

  const oldDeviceId = oldTrack.getSettings?.().deviceId;
  const newDeviceId = newTrack.getSettings?.().deviceId;
  return Boolean(oldDeviceId && newDeviceId && oldDeviceId === newDeviceId);
}

function rememberCamera(track, fallbackFacingMode = currentFacingMode) {
  const settings = track?.getSettings?.() || {};
  currentDeviceId = settings.deviceId || currentDeviceId;
  currentFacingMode = settings.facingMode || fallbackFacingMode;
  flipButton.dataset.facingMode = currentFacingMode;
}

function handleDetectionMessage(raw) {
  if (raw === "pong") {
    return;
  }

  let payload;
  try {
    payload = JSON.parse(raw);
  } catch {
    return;
  }

  if (payload.type !== "detections") {
    return;
  }

  fpsValue.textContent = payload.fps?.toFixed ? payload.fps.toFixed(1) : payload.fps || "0";
  latencyValue.textContent = `${Math.round(payload.inferenceMs || 0)} ms`;
  countValue.textContent = String(payload.detections?.length || 0);
  frameValue.textContent = `frame ${payload.frameId || 0}`;
  renderDetections(payload.detections || []);
}

function renderDetections(detections) {
  detectionsList.innerHTML = "";
  if (detections.length === 0) {
    const empty = document.createElement("li");
    empty.className = "empty";
    empty.textContent = "No objects in the current frame";
    detectionsList.append(empty);
    return;
  }

  detections.slice(0, 12).forEach((detection) => {
    const item = document.createElement("li");
    const confidence = Math.round((detection.confidence || 0) * 100);
    const bbox = detection.bbox || {};
    item.innerHTML = `
      <div class="detection-name">
        <span>${escapeHtml(detection.className || "object")}</span>
        <span>${confidence}%</span>
      </div>
      <div class="detection-box">
        x ${formatPct(bbox.x)}, y ${formatPct(bbox.y)}, w ${formatPct(bbox.w)}, h ${formatPct(bbox.h)}
      </div>
    `;
    detectionsList.append(item);
  });
}

function waitForIceGathering(pc) {
  if (pc.iceGatheringState === "complete") {
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    const timeout = window.setTimeout(() => {
      pc.removeEventListener("icegatheringstatechange", onStateChange);
      resolve();
    }, 2000);
    const onStateChange = () => {
      if (pc.iceGatheringState === "complete") {
        window.clearTimeout(timeout);
        pc.removeEventListener("icegatheringstatechange", onStateChange);
        resolve();
      }
    };
    pc.addEventListener("icegatheringstatechange", onStateChange);
  });
}

function setControls(isRunning) {
  const hasVideoSender = peerConnection?.getSenders().some((sender) => sender.track?.kind === "video");

  startButton.disabled = isRunning;
  stopButton.disabled = !isRunning;
  flipButton.disabled = !isRunning || !hasVideoSender || isFlippingCamera;
  flipButton.classList.toggle("loading", isFlippingCamera);
}

function setState(state) {
  connectionState.textContent = state;
  statusBadge.classList.toggle("connected", state === "connected");
  statusBadge.classList.toggle("failed", state === "failed");
}

function formatPct(value) {
  return `${Math.round((Number(value) || 0) * 100)}%`;
}

function escapeHtml(value) {
  const span = document.createElement("span");
  span.textContent = value;
  return span.innerHTML;
}
