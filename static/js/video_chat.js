// video_chat.js - Complete Fixed Version
let localStream = null;
let remoteStream = null;
let peerConnection = null;
let isCallActive = false;
let callStartTime = null;
let callDurationInterval = null;
let isSearching = false;

// Configuration for RTCPeerConnection
const pcConfig = {
  iceServers: [
    { urls: "stun:stun.l.google.com:19302" },
    { urls: "stun:stun1.l.google.com:19302" },
    { urls: "stun:stun2.l.google.com:19302" },
  ],
};

// Secure context check
function checkSecureContext() {
  const isLocalhost =
    location.hostname === "localhost" || location.hostname === "127.0.0.1";
  const isSecure = location.protocol === "https:";

  if (!isSecure && !isLocalhost) {
    showEnhancedErrorModal(
      "Security Warning",
      "Camera access requires HTTPS or localhost. " +
        "Please access via: https://localhost:5000 or http://localhost:5000\n\n" +
        "Current URL: " + location.href,
      false,
      true
    );
    return false;
  }
  return true;
}

// Initialize when page loads
document.addEventListener("DOMContentLoaded", function () {
  console.log("Initializing video chat...");
  console.log("Secure context:", window.isSecureContext);
  console.log("Protocol:", location.protocol);
  console.log("Hostname:", location.hostname);

  if (!checkSecureContext()) {
    updateConnectionStatus("Security Error - Use localhost");
    return;
  }

  initializeVideoChat();
  addTestButton();
});

async function initializeVideoChat() {
  await checkDevices();
  setupSocketListeners();
  updateUIState("ready");
}

async function checkDevices() {
  try {
    console.log("Checking available devices...");
    updateDeviceStatus("cameraStatusText", "Checking...", "status-unknown");
    updateDeviceStatus("microphoneStatusText", "Checking...", "status-unknown");

    // Check if browser supports media devices
    if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) {
      throw new Error("Media devices not supported in this browser");
    }

    const devices = await navigator.mediaDevices.enumerateDevices();
    console.log("Available devices:", devices);

    const videoDevices = devices.filter(
      (device) => device.kind === "videoinput"
    );
    const audioDevices = devices.filter(
      (device) => device.kind === "audioinput"
    );

    if (videoDevices.length > 0) {
      updateDeviceStatus("cameraStatusText", "Available", "status-available");
      console.log("Camera devices found:", videoDevices.length);
    } else {
      updateDeviceStatus("cameraStatusText", "Not Found", "status-unavailable");
      console.warn("No camera devices found");
    }

    if (audioDevices.length > 0) {
      updateDeviceStatus(
        "microphoneStatusText",
        "Available",
        "status-available"
      );
      console.log("Microphone devices found:", audioDevices.length);
    } else {
      updateDeviceStatus(
        "microphoneStatusText",
        "Not Found",
        "status-unavailable"
      );
      console.warn("No microphone devices found");
    }

    const hasDevices = videoDevices.length > 0 && audioDevices.length > 0;

    if (!hasDevices) {
      showNoDevicesModal();
    }

    return hasDevices;
  } catch (error) {
    console.error("Error checking devices:", error);
    updateDeviceStatus("cameraStatusText", "Error", "status-unavailable");
    updateDeviceStatus("microphoneStatusText", "Error", "status-unavailable");
    showEnhancedErrorModal("Device detection failed", error.message, true, false);
    return false;
  }
}

function updateDeviceStatus(elementId, text, statusClass) {
  const element = document.getElementById(elementId);
  if (element) {
    element.textContent = text;
    element.className = `status-badge ${statusClass}`;
  }
}

async function requestMediaAccess() {
  try {
    console.log("Requesting media access...");
    updateConnectionStatus("Requesting camera/microphone access...");

    // Check if we're on a supported environment
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error("WebRTC is not supported in this browser");
    }

    // First, get device list to check what's available
    const devices = await navigator.mediaDevices.enumerateDevices();
    const hasVideo = devices.some(device => device.kind === 'videoinput');
    const hasAudio = devices.some(device => device.kind === 'audioinput');

    console.log(`Devices - Video: ${hasVideo}, Audio: ${hasAudio}`);

    // Build constraints based on available devices
    const constraints = {
      video: hasVideo ? {
        width: { ideal: 640 },
        height: { ideal: 480 },
        frameRate: { ideal: 30 }
      } : false,
      audio: hasAudio ? {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true
      } : false
    };

    console.log("Media constraints:", constraints);

    // Show permission guidance
    showInfoModal(
      "Permission Required",
      "Please allow camera and microphone access in the browser permission dialog. " +
      "Look for the camera/microphone icon in your address bar."
    );

    // Request media access with timeout
    const mediaPromise = navigator.mediaDevices.getUserMedia(constraints);
    const timeoutPromise = new Promise((_, reject) => {
      setTimeout(() => reject(new Error("Permission request timed out")), 10000);
    });

    const stream = await Promise.race([mediaPromise, timeoutPromise]);
    
    hideInfoModal();
    console.log("Media access granted successfully");
    localStream = stream;

    // Setup local video
    setupLocalVideo(stream);

    // Update device status
    updateDeviceStatus("cameraStatusText", "Active", "status-available");
    updateDeviceStatus("microphoneStatusText", "Active", "status-available");

    return true;

  } catch (error) {
    console.error("Media access error:", error);
    hideInfoModal();
    await handleMediaError(error);
    return false;
  }
}

async function handleMediaError(error) {
  let errorMessage = "Unable to access camera/microphone";
  let detailedMessage = "";
  let showRetryButton = true;
  let showAdvancedHelp = false;

  switch (error.name) {
    case "NotAllowedError":
      errorMessage = "Camera/Microphone Permission Denied";
      detailedMessage = 
        "You denied camera/microphone access. To fix this:\n\n" +
        "1. Click the camera/microphone icon in your address bar\n" +
        "2. Select 'Allow' for camera and microphone\n" +
        "3. Refresh the page and try again\n\n" +
        "Or check your browser settings to reset permissions.";
      showAdvancedHelp = true;
      break;
      
    case "NotFoundError":
    case "DevicesNotFoundError":
      errorMessage = "No Camera/Microphone Found";
      detailedMessage = 
        "No camera or microphone was detected on your device.\n\n" +
        "Please check:\n" +
        "• Camera/microphone is properly connected\n" +
        "• No other app is using the camera\n" +
        "• Drivers are properly installed";
      break;
      
    case "NotReadableError":
    case "TrackStartError":
      errorMessage = "Camera/Microphone Already in Use";
      detailedMessage = 
        "Your camera or microphone is being used by another application.\n\n" +
        "Please close:\n" +
        "• Zoom, Teams, Skype\n" +
        "• Other browser tabs using camera\n" +
        "• Any video recording software";
      break;
      
    case "OverconstrainedError":
    case "ConstraintNotSatisfiedError":
      errorMessage = "Camera Requirements Not Met";
      detailedMessage = 
        "Your camera doesn't meet the required specifications.\n\n" +
        "Try:\n" +
        "• Using a different camera\n" +
        "• Updating camera drivers\n" +
        "• Using a different browser";
      break;
      
    case "SecurityError":
      errorMessage = "Security Restrictions";
      detailedMessage = 
        "Camera access is blocked for security reasons.\n\n" +
        "Make sure you're accessing via:\n" +
        "• HTTPS (secure connection)\n" +
        "• Localhost (for development)\n" +
        "• Trusted website";
      break;
      
    default:
      errorMessage = `Error: ${error.name}`;
      detailedMessage = error.message || "An unexpected error occurred";
  }

  console.error("Media error details:", error);
  
  // Show enhanced error modal
  showEnhancedErrorModal(errorMessage, detailedMessage, showRetryButton, showAdvancedHelp);

  // Update device status
  updateDeviceStatus("cameraStatusText", "Error", "status-unavailable");
  updateDeviceStatus("microphoneStatusText", "Error", "status-unavailable");
}

function showEnhancedErrorModal(title, message, showRetry = true, showAdvancedHelp = false) {
  const modal = document.createElement('div');
  modal.id = 'enhancedErrorModal';
  modal.className = 'modal';
  modal.style.display = 'flex';
  
  const advancedHelp = showAdvancedHelp ? `
    <div class="advanced-help">
      <h4>Advanced Troubleshooting:</h4>
      <div class="browser-help">
        <strong>Chrome:</strong> Settings → Privacy and Security → Site Settings → Camera/Microphone
      </div>
      <div class="browser-help">
        <strong>Firefox:</strong> Options → Privacy & Security → Permissions → Camera/Microphone
      </div>
      <div class="browser-help">
        <strong>Edge:</strong> Settings → Site Permissions → Camera/Microphone
      </div>
    </div>
  ` : '';

  modal.innerHTML = `
    <div class="modal-content" style="max-width: 600px;">
      <div class="error-header">
        <i class="fas fa-exclamation-triangle" style="color: #ef4444; font-size: 48px; margin-bottom: 20px;"></i>
        <h3>${title}</h3>
      </div>
      <div class="error-message">
        <p>${message.replace(/\n/g, '<br>')}</p>
      </div>
      ${advancedHelp}
      <div class="modal-buttons" style="margin-top: 20px;">
        <button class="btn-primary" onclick="document.getElementById('enhancedErrorModal').remove()">
          OK
        </button>
        ${showRetry ? `
          <button class="btn-secondary" onclick="document.getElementById('enhancedErrorModal').remove(); setTimeout(() => retryMediaAccess(), 500);">
            Try Again
        </button>
        ` : ''}
        <button class="btn-secondary" onclick="document.getElementById('enhancedErrorModal').remove(); emergencyFallback();">
          Continue Without Camera
        </button>
      </div>
    </div>
  `;

  document.body.appendChild(modal);
}

function setupLocalVideo(stream) {
  const localVideo = document.getElementById("localVideo");
  if (localVideo) {
    localVideo.srcObject = stream;

    // Handle video loading
    localVideo.onloadedmetadata = () => {
      console.log("Local video metadata loaded");
      localVideo
        .play()
        .catch((e) => console.error("Error playing local video:", e));
    };

    localVideo.onerror = (e) => {
      console.error("Local video error:", e);
    };

    localVideo.oncanplay = () => {
      console.log("Local video can play");
    };
  }

  // Show local video controls
  const localContainer = document.querySelector(".video-container:first-child");
  if (localContainer) {
    localContainer.classList.remove("video-off");
  }
}

function setupSocketListeners() {
  try {
    const socket = io();

    socket.on("connect", () => {
      console.log("Socket connected");
      updateConnectionStatus("Connected to server");
      updateUsersWaiting(0);
    });

    socket.on("disconnect", () => {
      console.log("Socket disconnected");
      updateConnectionStatus("Disconnected from server");
      if (isSearching || isCallActive) {
        showEnhancedErrorModal(
          "Connection lost",
          "The connection to the server was lost. Please refresh the page.",
          true
        );
        stopVideoChat();
      }
    });

    socket.on("searching", (data) => {
      console.log("Searching for partner...", data);
      updateConnectionStatus("Searching for partner...");
      updateUsersWaiting(data.count || 0);
      isSearching = true;
    });

    socket.on("match_found", (data) => {
      console.log("Match found:", data);
      isSearching = false;
      handleMatchFound(data);
    });

    socket.on("webrtc_signal", (data) => {
      console.log("Received WebRTC signal:", data.type);
      handleSignal(data);
    });

    socket.on("partner_left", () => {
      console.log("Partner left the chat");
      handlePartnerLeft();
    });

    socket.on("error", (data) => {
      console.error("Socket error:", data);
      showEnhancedErrorModal(
        "Connection Error",
        data.message || "An error occurred",
        true
      );
    });

    window.chatSocket = socket;
  } catch (error) {
    console.error("Error setting up socket listeners:", error);
    showEnhancedErrorModal(
      "Connection Error",
      "Failed to connect to chat server",
      true
    );
  }
}

async function startVideoChat() {
  try {
    console.log("Starting video chat...");
    updateUIState("starting");

    // First, request media access
    const hasAccess = await requestMediaAccess();
    if (!hasAccess) {
      updateUIState("ready");
      return;
    }

    updateConnectionStatus("Searching for partner...");
    updateUIState("searching");

    // Join the video chat queue
    if (window.chatSocket && window.chatSocket.connected) {
      window.chatSocket.emit("join_chat", {
        type: "video",
        interests: [],
      });
    } else {
      throw new Error("Not connected to chat server");
    }
  } catch (error) {
    console.error("Error starting video chat:", error);
    showEnhancedErrorModal("Failed to start video chat", error.message, true);
    updateUIState("ready");
  }
}

function stopVideoChat() {
  console.log("Stopping video chat...");

  // Stop local stream
  if (localStream) {
    localStream.getTracks().forEach((track) => {
      track.stop();
      console.log("Stopped track:", track.kind);
    });
    localStream = null;
  }

  // Close peer connection
  if (peerConnection) {
    peerConnection.close();
    peerConnection = null;
    console.log("Peer connection closed");
  }

  // Clear remote video
  const remoteVideo = document.getElementById("remoteVideo");
  if (remoteVideo) {
    remoteVideo.srcObject = null;
  }

  // Reset state
  isCallActive = false;
  isSearching = false;

  // Leave the chat if we have an active session
  if (window.chatSocket && window.currentSessionId) {
    window.chatSocket.emit("leave_chat", {
      session_id: window.currentSessionId,
    });
    window.currentSessionId = null;
    window.currentPartnerId = null;
  }

  // Update UI
  updateUIState("ready");
  updateConnectionStatus("Ready");
  resetCallDuration();

  // Show waiting overlay
  const waitingOverlay = document.getElementById("waitingOverlay");
  const remoteVideoOverlay = document.getElementById("remoteVideoOverlay");
  if (waitingOverlay) waitingOverlay.style.display = "flex";
  if (remoteVideoOverlay) remoteVideoOverlay.style.display = "none";

  console.log("Video chat stopped");
}

async function handleMatchFound(data) {
  try {
    console.log("Handling match found:", data);
    window.currentSessionId = data.session_id;
    window.currentPartnerId = data.partner_id;

    updateConnectionStatus("Connected to partner");
    isCallActive = true;
    isSearching = false;

    // Update UI
    const waitingOverlay = document.getElementById("waitingOverlay");
    if (waitingOverlay) waitingOverlay.style.display = "none";
    updateUIState("connected");

    // Start call timer
    startCallTimer();

    // Create peer connection and start call
    await createPeerConnection();
    await startCall();

    console.log("Call started successfully");
  } catch (error) {
    console.error("Error handling match found:", error);
    showEnhancedErrorModal("Failed to start call", error.message, true);
    stopVideoChat();
  }
}

async function createPeerConnection() {
  try {
    console.log("Creating peer connection...");
    peerConnection = new RTCPeerConnection(pcConfig);

    // Add local stream tracks
    if (localStream) {
      localStream.getTracks().forEach((track) => {
        peerConnection.addTrack(track, localStream);
        console.log("Added local track:", track.kind);
      });
    }

    // Handle remote stream
    peerConnection.ontrack = (event) => {
      console.log("Received remote track:", event.track.kind);
      if (event.streams && event.streams[0]) {
        remoteStream = event.streams[0];
        setupRemoteVideo(remoteStream);
      }
    };

    // Handle ICE candidates
    peerConnection.onicecandidate = (event) => {
      if (event.candidate && window.chatSocket) {
        console.log("Sending ICE candidate");
        window.chatSocket.emit("webrtc_signal", {
          type: "ice_candidate",
          candidate: event.candidate,
          session_id: window.currentSessionId,
        });
      }
    };

    // Handle connection state changes
    peerConnection.onconnectionstatechange = () => {
      const state = peerConnection.connectionState;
      console.log("Peer connection state:", state);

      switch (state) {
        case "connected":
          updateConnectionStatus("Connected");
          break;
        case "disconnected":
        case "failed":
          updateConnectionStatus("Connection lost");
          if (isCallActive) {
            setTimeout(() => {
              if (
                peerConnection &&
                (peerConnection.connectionState === "disconnected" ||
                  peerConnection.connectionState === "failed")
              ) {
                handlePartnerLeft();
              }
            }, 2000);
          }
          break;
        case "connecting":
          updateConnectionStatus("Connecting...");
          break;
      }
    };

    // Handle ICE connection state
    peerConnection.oniceconnectionstatechange = () => {
      console.log("ICE connection state:", peerConnection.iceConnectionState);
    };

    console.log("Peer connection created successfully");
  } catch (error) {
    console.error("Error creating peer connection:", error);
    throw error;
  }
}

function setupRemoteVideo(stream) {
  const remoteVideo = document.getElementById("remoteVideo");
  if (remoteVideo) {
    remoteVideo.srcObject = stream;

    remoteVideo.onloadedmetadata = () => {
      console.log("Remote video metadata loaded");
      remoteVideo
        .play()
        .catch((e) => console.error("Error playing remote video:", e));
    };

    remoteVideo.onerror = (e) => {
      console.error("Remote video error:", e);
    };

    remoteVideo.oncanplay = () => {
      console.log("Remote video can play");
    };

    // Hide overlays when remote video is active
    const remoteVideoOverlay = document.getElementById("remoteVideoOverlay");
    if (remoteVideoOverlay) remoteVideoOverlay.style.display = "none";
  }
}

async function startCall() {
  try {
    console.log("Starting call...");

    // Create and send offer
    const offer = await peerConnection.createOffer({
      offerToReceiveAudio: true,
      offerToReceiveVideo: true,
    });

    await peerConnection.setLocalDescription(offer);

    console.log("Sending offer...");
    window.chatSocket.emit("webrtc_signal", {
      type: "offer",
      offer: offer,
      session_id: window.currentSessionId,
    });
  } catch (error) {
    console.error("Error starting call:", error);
    throw error;
  }
}

async function handleSignal(data) {
  if (!peerConnection) {
    console.warn("No peer connection for signal");
    return;
  }

  try {
    console.log("Handling signal type:", data.type);

    switch (data.type) {
      case "offer":
        console.log("Received offer");
        await peerConnection.setRemoteDescription(data.offer);
        const answer = await peerConnection.createAnswer();
        await peerConnection.setLocalDescription(answer);

        window.chatSocket.emit("webrtc_signal", {
          type: "answer",
          answer: answer,
          session_id: window.currentSessionId,
        });
        break;

      case "answer":
        console.log("Received answer");
        await peerConnection.setRemoteDescription(data.answer);
        break;

      case "ice_candidate":
        console.log("Received ICE candidate");
        await peerConnection.addIceCandidate(data.candidate);
        break;
    }
  } catch (error) {
    console.error("Error handling signal:", error);
  }
}

function handlePartnerLeft() {
  console.log("Handling partner left");
  showInfoModal("Partner Left", "Your chat partner has left the conversation.");
  stopVideoChat();
}

// UI Control Functions
function toggleVideo() {
  if (localStream) {
    const videoTracks = localStream.getVideoTracks();
    if (videoTracks.length > 0) {
      const videoTrack = videoTracks[0];
      videoTrack.enabled = !videoTrack.enabled;

      const btn = document.getElementById("videoToggle");
      if (btn) {
        btn.innerHTML = videoTrack.enabled
          ? '<i class="fas fa-video"></i>'
          : '<i class="fas fa-video-slash"></i>';
        btn.style.background = videoTrack.enabled ? '#8b5cf6' : '#ef4444';
      }

      const localVideoContainer = document.querySelector(
        ".video-container:first-child"
      );
      if (localVideoContainer) {
        if (videoTrack.enabled) {
          localVideoContainer.classList.remove("video-off");
        } else {
          localVideoContainer.classList.add("video-off");
        }
      }

      console.log("Video toggled:", videoTrack.enabled);
    }
  }
}

function toggleAudio() {
  if (localStream) {
    const audioTracks = localStream.getAudioTracks();
    if (audioTracks.length > 0) {
      const audioTrack = audioTracks[0];
      audioTrack.enabled = !audioTrack.enabled;

      const btn = document.getElementById("audioToggle");
      if (btn) {
        btn.innerHTML = audioTrack.enabled
          ? '<i class="fas fa-microphone"></i>'
          : '<i class="fas fa-microphone-slash"></i>';
        btn.style.background = audioTrack.enabled ? '#8b5cf6' : '#ef4444';
      }

      console.log("Audio toggled:", audioTrack.enabled);
    }
  }
}

function endCall() {
  console.log("End call requested");
  stopVideoChat();
}

function nextUser() {
  console.log("Next user requested");
  stopVideoChat();
  setTimeout(() => {
    startVideoChat();
  }, 1000);
}

// UI Update Functions
function updateUIState(state) {
  const startBtn = document.getElementById("startVideoChatBtn");
  const stopBtn = document.getElementById("stopVideoChatBtn");
  const endCallBtn = document.getElementById("endCallBtn");
  const nextUserBtn = document.getElementById("nextUserBtn");
  const videoToggle = document.getElementById("videoToggle");
  const audioToggle = document.getElementById("audioToggle");

  switch (state) {
    case "ready":
      if (startBtn) startBtn.style.display = "block";
      if (stopBtn) stopBtn.style.display = "none";
      if (endCallBtn) endCallBtn.disabled = true;
      if (nextUserBtn) nextUserBtn.disabled = true;
      if (videoToggle) videoToggle.disabled = true;
      if (audioToggle) audioToggle.disabled = true;
      break;

    case "starting":
      if (startBtn) startBtn.style.display = "none";
      if (stopBtn) stopBtn.style.display = "block";
      if (endCallBtn) endCallBtn.disabled = false;
      if (nextUserBtn) nextUserBtn.disabled = true;
      if (videoToggle) videoToggle.disabled = false;
      if (audioToggle) audioToggle.disabled = false;
      break;

    case "searching":
      if (startBtn) startBtn.style.display = "none";
      if (stopBtn) stopBtn.style.display = "block";
      if (endCallBtn) endCallBtn.disabled = false;
      if (nextUserBtn) nextUserBtn.disabled = true;
      if (videoToggle) videoToggle.disabled = false;
      if (audioToggle) audioToggle.disabled = false;
      break;

    case "connected":
      if (startBtn) startBtn.style.display = "none";
      if (stopBtn) stopBtn.style.display = "block";
      if (endCallBtn) endCallBtn.disabled = false;
      if (nextUserBtn) nextUserBtn.disabled = false;
      if (videoToggle) videoToggle.disabled = false;
      if (audioToggle) audioToggle.disabled = false;
      break;
  }
}

function updateConnectionStatus(status) {
  const statusElement = document.getElementById("connectionStatus");
  const chatStatusElement = document.getElementById("chatStatus");

  if (statusElement) {
    statusElement.textContent = status;
    statusElement.setAttribute("title", status);
  }
  if (chatStatusElement) {
    chatStatusElement.textContent = status;
  }

  console.log("Connection status:", status);
}

function updateUsersWaiting(count) {
  const element = document.getElementById("usersWaiting");
  if (element) {
    element.textContent = count;
  }
}

function startCallTimer() {
  callStartTime = new Date();
  resetCallDuration();

  callDurationInterval = setInterval(() => {
    if (callStartTime) {
      const now = new Date();
      const duration = Math.floor((now - callStartTime) / 1000);
      const minutes = Math.floor(duration / 60);
      const seconds = duration % 60;

      const durationElement = document.getElementById("callDuration");
      if (durationElement) {
        durationElement.textContent = `${minutes
          .toString()
          .padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
      }
    }
  }, 1000);
}

function resetCallDuration() {
  if (callDurationInterval) {
    clearInterval(callDurationInterval);
    callDurationInterval = null;
  }
  callStartTime = null;

  const durationElement = document.getElementById("callDuration");
  if (durationElement) {
    durationElement.textContent = "00:00";
  }
}

// Modal Functions
function showDeviceCheckModal() {
  const modal = document.getElementById("deviceCheckModal");
  if (modal) modal.style.display = "flex";
}

function hideDeviceCheckModal() {
  const modal = document.getElementById("deviceCheckModal");
  if (modal) modal.style.display = "none";
}

function showNoDevicesModal() {
  const modal = document.getElementById("noDevicesModal");
  if (modal) modal.style.display = "flex";
}

function hideNoDevicesModal() {
  const modal = document.getElementById("noDevicesModal");
  if (modal) modal.style.display = "none";
}

function showInfoModal(title, message) {
  // Create info modal if it doesn't exist
  let infoModal = document.getElementById("infoModal");
  if (!infoModal) {
    infoModal = document.createElement("div");
    infoModal.id = "infoModal";
    infoModal.className = "modal";
    document.body.appendChild(infoModal);
  }

  infoModal.innerHTML = `
        <div class="modal-content">
            <h3>${title}</h3>
            <p>${message}</p>
            <div class="modal-buttons">
                <button class="btn-primary" onclick="hideInfoModal()">OK</button>
            </div>
        </div>
    `;

  infoModal.style.display = "flex";
}

function hideInfoModal() {
  const infoModal = document.getElementById("infoModal");
  if (infoModal) {
    infoModal.style.display = "none";
  }
}

function retryMediaAccess() {
  console.log("Retrying media access...");
  startVideoChat();
}

function proceedWithMediaAccess() {
  hideDeviceCheckModal();
  startVideoChat();
}

function retryDeviceDetection() {
  hideNoDevicesModal();
  checkDevices().then((hasDevices) => {
    if (hasDevices) {
      startVideoChat();
    } else {
      showNoDevicesModal();
    }
  });
}

// Emergency fallback for testing without camera
async function emergencyFallback() {
  console.warn("Using emergency fallback - no camera access");
  updateConnectionStatus("Connected (Test Mode - No Camera)");
  updateDeviceStatus("cameraStatusText", "Test Mode", "status-unknown");
  updateDeviceStatus("microphoneStatusText", "Test Mode", "status-unknown");

  // Continue with chat without media
  updateUIState("searching");

  if (window.chatSocket && window.chatSocket.connected) {
    window.chatSocket.emit("join_chat", {
      type: "video",
      interests: [],
    });
  }

  return true;
}

// Add test button for development
function addTestButton() {
  const sidebar = document.querySelector('.chat-sidebar .sidebar-section:last-child');
  if (sidebar) {
    const testButton = document.createElement('button');
    testButton.className = 'btn-secondary btn-full';
    testButton.innerHTML = '<i class="fas fa-video-slash"></i> Test Without Camera';
    testButton.onclick = emergencyFallback;
    testButton.style.marginTop = '10px';
    testButton.style.background = '#666';
    sidebar.appendChild(testButton);
  }
}

// Export functions for global access
window.startVideoChat = startVideoChat;
window.stopVideoChat = stopVideoChat;
window.toggleVideo = toggleVideo;
window.toggleAudio = toggleAudio;
window.endCall = endCall;
window.nextUser = nextUser;
window.checkDevices = checkDevices;
window.proceedWithMediaAccess = proceedWithMediaAccess;
window.retryDeviceDetection = retryDeviceDetection;
window.hideDeviceCheckModal = hideDeviceCheckModal;
window.hideNoDevicesModal = hideNoDevicesModal;
window.emergencyFallback = emergencyFallback;
window.retryMediaAccess = retryMediaAccess;

console.log("Video chat module loaded successfully");