const remoteVideo = document.querySelector("#remoteVideo");
const startButton = document.querySelector("#startButton");
const stopButton = document.querySelector("#stopButton");
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

startButton.addEventListener("click", startSession);
stopButton.addEventListener("click", stopSession);

async function startSession() {
  setControls(true);
  setState("camera");

  try {
    localStream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: {
        width: { ideal: 960 },
        height: { ideal: 540 },
        frameRate: { ideal: 24, max: 30 },
      },
    });

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
  } catch (error) {
    console.error(error);
    setState("failed");
    alert(`Could not start camera session: ${error.message}`);
    stopSession();
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
  setControls(false);
  setState("idle");
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
  startButton.disabled = isRunning;
  stopButton.disabled = !isRunning;
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
