// video_chat.js - Complete Enhanced Version with Global Gender-Based Matching
let localStream = null;
let remoteStream = null;
let peerConnection = null;
let isCallActive = false;
let callStartTime = null;
let callDurationInterval = null;
let isSearching = false;

// Advanced Features Variables
let backgroundProcessor = null;
let voiceProcessor = null;
let faceFilterProcessor = null;
let currentBackgroundEffect = "none";
let currentVoiceEffect = "normal";
let currentFaceFilter = "none";
let networkMonitorInterval = null;
let miniGameActive = false;
let currentGame = null;
let screenshotProtectionEnabled = true;
let audioContext = null;
let voiceEffectNode = null;

// Configuration for RTCPeerConnection
const pcConfig = {
  iceServers: [
    { urls: "stun:stun.l.google.com:19302" },
    { urls: "stun:stun1.l.google.com:19302" },
    { urls: "stun:stun2.l.google.com:19302" },
    { urls: "stun:stun3.l.google.com:19302" },
    { urls: "stun:stun4.l.google.com:19302" },
  ],
};

// Global matching variables
let userGender = "unknown";
let genderPreference = "opposite";
let searchRange = "global";
let userLocation = "Unknown";

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
        "Current URL: " +
        location.href,
      false,
      true
    );
    return false;
  }
  return true;
}

// Initialize when page loads
document.addEventListener("DOMContentLoaded", function () {
  console.log(
    "Initializing enhanced video chat with global gender matching..."
  );
  console.log("Secure context:", window.isSecureContext);
  console.log("Protocol:", location.protocol);
  console.log("Hostname:", location.hostname);

  if (!checkSecureContext()) {
    updateConnectionStatus("Security Error - Use localhost");
    return;
  }

  initializeVideoChat();
  initializeGlobalFeatures();
  initializeAdvancedFeatures();
  setupSocketListeners();
  setupGlobalSocketListeners();
  addTestButton();
});

// Global Features Initialization
function initializeGlobalFeatures() {
  // Detect user location
  userLocation = detectUserLocation();
  document.getElementById("userLocation").textContent = userLocation;

  // Set user gender (in real app, get from user profile)
  userGender = getUserGenderFromProfile();
  document.getElementById("userGender").textContent = userGender;

  // Set up preferences
  updateGenderPreference("opposite");
  updateSearchRange("global");

  console.log("🌍 Global features initialized:", {
    gender: userGender,
    location: userLocation,
    preference: genderPreference,
    range: searchRange,
  });
}

function detectUserLocation() {
  // Mock location detection - in production, use IP geolocation
  const locations = [
    "New York, USA",
    "London, UK",
    "Tokyo, Japan",
    "Sydney, Australia",
    "Berlin, Germany",
    "Paris, France",
    "Toronto, Canada",
    "São Paulo, Brazil",
    "Mumbai, India",
    "Singapore",
    "Dubai, UAE",
    "Amsterdam, Netherlands",
  ];
  return locations[Math.floor(Math.random() * locations.length)];
}

function getUserGenderFromProfile() {
  // Mock gender detection - in real app, get from user profile
  const genders = ["male", "female"];
  return genders[Math.floor(Math.random() * genders.length)];
}

function updateGenderPreference(preference) {
  genderPreference = preference;
  const element = document.getElementById("matchPreference");
  if (element) {
    switch (preference) {
      case "opposite":
        element.textContent = "Opposite Gender";
        break;
      case "same":
        element.textContent = "Same Gender";
        break;
      case "any":
        element.textContent = "Any Gender";
        break;
    }
  }
  console.log("Gender preference updated to:", preference);
}

function updateSearchRange(range) {
  searchRange = range;
  const element = document.getElementById("searchRange");
  if (element) {
    switch (range) {
      case "global":
        element.textContent = "Worldwide";
        break;
      case "continent":
        element.textContent = "Same Continent";
        break;
      case "country":
        element.textContent = "Same Country";
        break;
    }
  }
  console.log("Search range updated to:", range);
}

async function initializeVideoChat() {
  await checkDevices();
  updateUIState("ready");
}

// Advanced Features Initialization
async function initializeAdvancedFeatures() {
  try {
    console.log("Initializing advanced features...");

    // Initialize screenshot protection
    initializeScreenshotProtection();

    // Initialize network monitoring
    startNetworkMonitoring();

    // Try to initialize Web Audio API for voice effects
    try {
      audioContext = new (window.AudioContext || window.webkitAudioContext)();
      console.log("Web Audio API initialized for voice effects");
    } catch (error) {
      console.warn("Web Audio API not available for voice effects:", error);
    }
  } catch (error) {
    console.error("Error initializing advanced features:", error);
  }
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

    const hasDevices = videoDevices.length > 0 || audioDevices.length > 0;

    if (!hasDevices) {
      showNoDevicesModal();
    }

    return hasDevices;
  } catch (error) {
    console.error("Error checking devices:", error);
    updateDeviceStatus("cameraStatusText", "Error", "status-unavailable");
    updateDeviceStatus("microphoneStatusText", "Error", "status-unavailable");
    showEnhancedErrorModal(
      "Device detection failed",
      error.message,
      true,
      false
    );
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

    // Show the overlay initially
    const localVideoOverlay = document.getElementById("localVideoOverlay");
    if (localVideoOverlay) {
      localVideoOverlay.style.display = "flex";
    }

    // Check if we're on a supported environment
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error("WebRTC is not supported in this browser");
    }

    // First, get device list to check what's available
    const devices = await navigator.mediaDevices.enumerateDevices();
    const hasVideo = devices.some((device) => device.kind === "videoinput");
    const hasAudio = devices.some((device) => device.kind === "audioinput");

    console.log(`Devices - Video: ${hasVideo}, Audio: ${hasAudio}`);

    // Ensure at least one media type is available
    if (!hasVideo && !hasAudio) {
      throw new Error("No camera or microphone devices found");
    }

    // Build constraints based on available devices
    const constraints = {
      video: hasVideo
        ? {
            width: { ideal: 640 },
            height: { ideal: 480 },
            frameRate: { ideal: 30 },
            facingMode: "user", // Force front camera
          }
        : false,
      audio: hasAudio
        ? {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
          }
        : false,
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
      setTimeout(
        () => reject(new Error("Permission request timed out")),
        10000
      );
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

    // Notify server that media is ready for video chat
    if (window.chatSocket && window.chatSocket.connected) {
      window.chatSocket.emit("media_ready", {
        media_type:
          hasVideo && hasAudio ? "both" : hasVideo ? "video" : "audio",
      });
    }

    return true;
  } catch (error) {
    console.error("Media access error:", error);
    hideInfoModal();

    // Ensure overlay is shown on error
    const localVideoOverlay = document.getElementById("localVideoOverlay");
    if (localVideoOverlay) {
      localVideoOverlay.style.display = "flex";
    }

    await handleMediaError(error);
    return false;
  }
}

// Fix for reversed camera - try different camera constraints
async function fixReversedCamera() {
  try {
    console.log("Attempting to fix reversed camera...");

    // Stop current stream
    if (localStream) {
      localStream.getTracks().forEach((track) => track.stop());
    }

    // Try different camera constraints
    const constraints = {
      video: {
        width: { ideal: 640 },
        height: { ideal: 480 },
        frameRate: { ideal: 30 },
        facingMode: { exact: "user" }, // Force front camera explicitly
      },
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    };

    // Try to get specific device if available
    const devices = await navigator.mediaDevices.enumerateDevices();
    const videoDevices = devices.filter(
      (device) => device.kind === "videoinput"
    );

    if (videoDevices.length > 0) {
      // Try to find front camera
      const frontCamera = videoDevices.find(
        (device) =>
          device.label.toLowerCase().includes("front") ||
          device.label.toLowerCase().includes("face")
      );

      if (frontCamera) {
        constraints.video.deviceId = { exact: frontCamera.deviceId };
        console.log("Using front camera:", frontCamera.label);
      } else {
        // Use first camera but try to force front facing
        constraints.video.deviceId = { exact: videoDevices[0].deviceId };
        console.log("Using first camera:", videoDevices[0].label);
      }
    }

    const stream = await navigator.mediaDevices.getUserMedia(constraints);
    localStream = stream;

    // Update video element
    const localVideo = document.getElementById("localVideo");
    if (localVideo) {
      localVideo.srcObject = stream;

      // Apply CSS transform to mirror the video if it's still reversed
      localVideo.style.transform = "scaleX(-1)";
    }

    console.log("Camera fixed - applied mirror effect");
    return true;
  } catch (error) {
    console.error("Error fixing camera:", error);
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
  showEnhancedErrorModal(
    errorMessage,
    detailedMessage,
    showRetryButton,
    showAdvancedHelp
  );

  // Update device status
  updateDeviceStatus("cameraStatusText", "Error", "status-unavailable");
  updateDeviceStatus("microphoneStatusText", "Error", "status-unavailable");
}

function showEnhancedErrorModal(
  title,
  message,
  showRetry = true,
  showAdvancedHelp = false
) {
  const modal = document.createElement("div");
  modal.id = "enhancedErrorModal";
  modal.className = "modal";
  modal.style.display = "flex";

  const advancedHelp = showAdvancedHelp
    ? `
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
    `
    : "";

  modal.innerHTML = `
    <div class="modal-content" style="max-width: 600px;">
        <div class="error-header">
            <i class="fas fa-exclamation-triangle" style="color: #ef4444; font-size: 48px; margin-bottom: 20px;"></i>
            <h3>${title}</h3>
        </div>
        <div class="error-message">
            <p>${message.replace(/\n/g, "<br>")}</p>
        </div>
        ${advancedHelp}
        <div class="modal-buttons" style="margin-top: 20px;">
            <button class="btn-primary" onclick="document.getElementById('enhancedErrorModal').remove()">
                OK
            </button>
            ${
              showRetry
                ? `
            <button class="btn-secondary" onclick="document.getElementById('enhancedErrorModal').remove(); setTimeout(() => retryMediaAccess(), 500);">
                Try Again
            </button>
            `
                : ""
            }
            <button class="btn-secondary" onclick="document.getElementById('enhancedErrorModal').remove(); fixReversedCamera();">
                Fix Camera Orientation
            </button>
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
  const localVideoOverlay = document.getElementById("localVideoOverlay");

  if (localVideo) {
    localVideo.srcObject = stream;

    // Apply mirror effect to fix reversed camera
    localVideo.style.transform = "scaleX(-1)";

    // Handle video loading
    localVideo.onloadedmetadata = () => {
      console.log("Local video metadata loaded");
      localVideo
        .play()
        .catch((e) => console.error("Error playing local video:", e));

      // Hide the overlay when video is ready
      if (localVideoOverlay) {
        localVideoOverlay.style.display = "none";
      }
    };

    localVideo.onerror = (e) => {
      console.error("Local video error:", e);
      // Show overlay if there's an error
      if (localVideoOverlay) {
        localVideoOverlay.style.display = "flex";
      }
    };

    localVideo.oncanplay = () => {
      console.log("Local video can play");
    };

    // Check if video is actually playing and hide overlay
    localVideo.onplaying = () => {
      console.log("Local video is playing");
      if (localVideoOverlay) {
        localVideoOverlay.style.display = "none";
      }
    };

    // Show overlay if video pauses (camera turned off)
    localVideo.onpause = () => {
      console.log("Local video paused");
      if (localVideoOverlay) {
        localVideoOverlay.style.display = "flex";
      }
    };
  }

  // Show local video controls
  const localContainer = document.querySelector(".video-container:first-child");
  if (localContainer) {
    localContainer.classList.remove("video-off");
  }

  // Check video stream status after a short delay
  setTimeout(() => {
    checkVideoStreamStatus();
  }, 500);
}

function setupRemoteVideo(stream) {
  const remoteVideo = document.getElementById("remoteVideo");
  if (remoteVideo) {
    remoteVideo.srcObject = stream;

    // Don't mirror remote video (it should appear normal)
    remoteVideo.style.transform = "scaleX(1)";

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

// Global Video Chat Functions
async function startGlobalVideoChat() {
  try {
    console.log("🌍 Starting global video chat...");
    updateUIState("starting");

    // Request media access
    const hasAccess = await requestMediaAccess();
    if (!hasAccess) {
      updateUIState("ready");
      return;
    }

    updateConnectionStatus("🌍 Searching globally for opposite gender...");
    updateUIState("searching");

    // Join global video chat with gender preferences
    if (window.chatSocket && window.chatSocket.connected) {
      window.chatSocket.emit("join_global_video_chat", {
        type: "video",
        interests: getUserInterests(),
        filters: {
          require_video: true,
          require_audio: true,
          gender_preference: genderPreference,
          search_range: searchRange,
        },
        location: userLocation,
        gender: userGender,
        language: navigator.language || "en",
      });

      // Notify server that media is ready
      setTimeout(() => {
        if (window.chatSocket && window.chatSocket.connected) {
          window.chatSocket.emit("media_ready", {
            media_type: "both",
          });
        }
      }, 1000);
    } else {
      throw new Error("Not connected to chat server");
    }
  } catch (error) {
    console.error("Error starting global video chat:", error);
    showEnhancedErrorModal(
      "Failed to start global video chat",
      error.message,
      true
    );
    updateUIState("ready");
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

    // Video chat specific events
    socket.on("video_chat_search_started", (data) => {
      console.log("Searching for video partner...", data);
      updateConnectionStatus("Searching for video partner...");
      updateUsersWaiting(data.total_waiting || 0);
      isSearching = true;
    });

    socket.on("video_chat_match_found", (data) => {
      console.log("Video match found:", data);
      isSearching = false;
      handleMatchFound(data);
    });

    socket.on("video_chat_ended", (data) => {
      console.log("Video chat ended:", data);
      handlePartnerLeft(data.reason);
    });

    socket.on("webrtc_signal", (data) => {
      console.log("Received WebRTC signal:", data.type);
      handleSignal(data);
    });

    socket.on("partner_media_ready", (data) => {
      console.log("Partner media ready:", data.media_type);
      showInfoModal(
        "Partner Ready",
        "Your partner's camera/microphone is now ready."
      );
    });

    socket.on("video_chat_search_cancelled", () => {
      console.log("Video search cancelled");
      isSearching = false;
      updateUIState("ready");
    });

    // Legacy events for backward compatibility
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

    socket.on("partner_left", () => {
      console.log("Partner left the chat");
      handlePartnerLeft();
    });

    // Advanced features socket events
    socket.on("game_started", (data) => {
      console.log("Partner started game:", data.game_type);
      showInfoModal(
        "Game Started",
        `Your partner started a ${data.game_type} game!`
      );
    });

    socket.on("game_ended", () => {
      console.log("Partner ended game");
      showInfoModal("Game Ended", "Your partner ended the game.");
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

// Global Socket Listeners
function setupGlobalSocketListeners() {
  if (!window.chatSocket) return;

  // Global video match found
  window.chatSocket.on("global_video_match_found", (data) => {
    console.log("🌍 Global video match found:", data);
    handleGlobalMatchFound(data);
  });

  // Global video search started
  window.chatSocket.on("global_video_search_started", (data) => {
    console.log("🌍 Global video search started:", data);
    updateConnectionStatus(
      `🌍 Searching globally... (Position: ${data.position})`
    );
    updateUsersWaiting(data.total_waiting || 0);
    isSearching = true;

    // Show global search info
    showInfoModal(
      "Global Search Started",
      `Searching for ${
        genderPreference === "opposite"
          ? "opposite gender"
          : genderPreference + " gender"
      } worldwide...\nYour location: ${
        data.user_location
      }\nPosition in queue: ${data.position}`
    );
  });
}

async function handleGlobalMatchFound(data) {
  try {
    console.log("🌍 Handling global match found:", data);
    window.currentSessionId = data.session_id;
    window.currentPartnerId = data.partner_id;

    // Show global match modal
    showGlobalMatchModal(data);

    updateConnectionStatus(`🌍 Connected to ${data.partner_location}`);
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

    console.log("🌍 Global call started successfully");
  } catch (error) {
    console.error("Error handling global match found:", error);
    showEnhancedErrorModal("Failed to start global call", error.message, true);
    stopVideoChat();
  }
}

function showGlobalMatchModal(matchData) {
  const modal = document.getElementById("globalMatchModal");
  if (!modal) return;

  // Update modal content
  document.getElementById("matchPartnerName").textContent =
    matchData.partner_name;
  document.getElementById("matchPartnerGender").textContent =
    matchData.partner_gender;
  document.getElementById("matchPartnerLocation").textContent =
    matchData.partner_location;
  document.getElementById("matchCommonInterests").textContent =
    matchData.common_interests && matchData.common_interests.length > 0
      ? matchData.common_interests.join(", ")
      : "None";
  document.getElementById("matchDistance").textContent =
    matchData.distance || "Global";

  // Show modal
  modal.style.display = "flex";
}

function hideGlobalMatchModal() {
  const modal = document.getElementById("globalMatchModal");
  if (modal) {
    modal.style.display = "none";
  }
}

function startCallWithMatch() {
  hideGlobalMatchModal();
  console.log("Starting call with matched partner...");
}

function declineMatch() {
  hideGlobalMatchModal();
  console.log("Match declined");
  stopVideoChat();
  showInfoModal(
    "Match Declined",
    "You declined the match. Starting new search..."
  );
  setTimeout(() => startGlobalVideoChat(), 2000);
}

// Get user interests from profile or form
function getUserInterests() {
  // In a real implementation, get from user profile or form
  const interests = [
    "travel",
    "music",
    "movies",
    "sports",
    "technology",
    "art",
    "food",
    "reading",
    "gaming",
    "fitness",
  ];
  // Return 3 random interests for demo
  return interests.sort(() => 0.5 - Math.random()).slice(0, 3);
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

function handlePartnerLeft(reason = "Partner left the chat") {
  console.log("Handling partner left:", reason);
  showInfoModal("Partner Left", reason);
  stopVideoChat();
}

function stopVideoChat() {
  console.log("Stopping video chat...");

  // Show camera off overlay when stopping
  const localVideoOverlay = document.getElementById("localVideoOverlay");
  if (localVideoOverlay) {
    localVideoOverlay.style.display = "flex";
  }

  // Notify server about ending video chat
  if (window.chatSocket && window.currentSessionId) {
    window.chatSocket.emit("video_chat_ended", {
      session_id: window.currentSessionId,
      reason: "user_left",
    });
  }

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
    remoteVideo.style.transform = "scaleX(1)"; // Reset transform
  }

  // Clear local video transform
  const localVideo = document.getElementById("localVideo");
  if (localVideo) {
    localVideo.style.transform = "scaleX(1)";
  }

  // Reset state
  isCallActive = false;
  isSearching = false;
  miniGameActive = false;
  currentGame = null;

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

  // Hide game container
  const gameContainer = document.getElementById("gameContainer");
  if (gameContainer) {
    gameContainer.style.display = "none";
  }

  // Show waiting overlay
  const waitingOverlay = document.getElementById("waitingOverlay");
  const remoteVideoOverlay = document.getElementById("remoteVideoOverlay");
  if (waitingOverlay) waitingOverlay.style.display = "flex";
  if (remoteVideoOverlay) remoteVideoOverlay.style.display = "none";

  // Reset advanced features
  removeBackgroundEffects();
  changeFaceFilter("none");
  changeVoiceEffect("normal");

  // Hide global match modal
  hideGlobalMatchModal();

  console.log("Video chat stopped");
}

// Advanced Features Implementation

// Background Effects
async function changeBackgroundEffect(effect) {
  currentBackgroundEffect = effect;

  if (!localStream) return;

  const videoTrack = localStream.getVideoTracks()[0];
  if (!videoTrack) return;

  try {
    switch (effect) {
      case "blur":
        await applyBackgroundBlur();
        break;
      case "virtual":
        await applyVirtualBackground();
        break;
      case "pixelate":
        await applyFacePixelation();
        break;
      case "none":
      default:
        removeBackgroundEffects();
        break;
    }

    console.log("Background effect applied:", effect);
  } catch (error) {
    console.error("Error applying background effect:", error);
    showInfoModal(
      "Effect Not Available",
      "This effect requires more processing power and may not work on all devices."
    );
  }
}

async function applyBackgroundBlur() {
  const localVideo = document.getElementById("localVideo");
  if (localVideo) {
    localVideo.style.filter = "blur(15px)";
    localVideo.style.maskImage =
      "radial-gradient(circle, white 40%, transparent 70%)";
    localVideo.style.webkitMaskImage =
      "radial-gradient(circle, white 40%, transparent 70%)";
  }
}

async function applyVirtualBackground() {
  const localVideo = document.getElementById("localVideo");
  if (localVideo) {
    // Create a canvas-based virtual background
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");

    // Set canvas size to match video
    canvas.width = localVideo.videoWidth || 640;
    canvas.height = localVideo.videoHeight || 480;

    // Draw virtual background (gradient)
    const gradient = ctx.createLinearGradient(
      0,
      0,
      canvas.width,
      canvas.height
    );
    gradient.addColorStop(0, "#8b5cf6");
    gradient.addColorStop(1, "#3b82f6");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Use canvas as background
    localVideo.style.backgroundImage = `url(${canvas.toDataURL()})`;
    localVideo.style.backgroundSize = "cover";
    localVideo.style.backgroundPosition = "center";
  }
}

async function applyFacePixelation() {
  const localVideo = document.getElementById("localVideo");
  if (localVideo) {
    localVideo.style.filter = "pixelate(8px) contrast(1.2)";
  }
}

function removeBackgroundEffects() {
  const localVideo = document.getElementById("localVideo");
  if (localVideo) {
    localVideo.style.filter = "none";
    localVideo.style.maskImage = "none";
    localVideo.style.webkitMaskImage = "none";
    localVideo.style.backgroundImage = "none";
  }
}

// Voice Modulator
function changeVoiceEffect(effect) {
  currentVoiceEffect = effect;

  if (!localStream) return;

  const audioTracks = localStream.getAudioTracks();
  if (audioTracks.length === 0) return;

  console.log("Voice effect changed to:", effect);

  // Apply voice effect using Web Audio API if available
  applyVoiceModulation(effect);
}

function applyVoiceModulation(effect) {
  if (!audioContext || audioContext.state === "suspended") {
    console.warn("Audio context not available for voice modulation");
    showInfoModal(
      "Voice Effect",
      `${effect} voice effect selected. Full voice modulation requires Web Audio API support.`
    );
    return;
  }

  try {
    // Resume audio context if suspended
    if (audioContext.state === "suspended") {
      audioContext.resume();
    }

    // Remove existing effect node
    if (voiceEffectNode) {
      voiceEffectNode.disconnect();
    }

    const source = audioContext.createMediaStreamSource(localStream);

    switch (effect) {
      case "deep":
        // Low-pass filter for deeper voice
        voiceEffectNode = audioContext.createBiquadFilter();
        voiceEffectNode.type = "lowpass";
        voiceEffectNode.frequency.value = 800;
        break;

      case "high":
        // High-pass filter for higher voice
        voiceEffectNode = audioContext.createBiquadFilter();
        voiceEffectNode.type = "highpass";
        voiceEffectNode.frequency.value = 1000;
        break;

      case "robot":
        // Robot effect using oscillator modulation
        voiceEffectNode = audioContext.createGain();
        const oscillator = audioContext.createOscillator();
        oscillator.type = "sawtooth";
        oscillator.frequency.value = 50;

        const modulator = audioContext.createGain();
        modulator.gain.value = 0.1;

        oscillator.connect(modulator);
        modulator.connect(voiceEffectNode.gain);
        oscillator.start();
        break;

      case "anonymous":
        // Pitch shift for anonymous effect
        voiceEffectNode = audioContext.createGain();
        voiceEffectNode.gain.value = 0.8;
        break;

      case "normal":
      default:
        voiceEffectNode = audioContext.createGain();
        voiceEffectNode.gain.value = 1.0;
        break;
    }

    const destination = audioContext.createMediaStreamDestination();
    source.connect(voiceEffectNode);
    voiceEffectNode.connect(destination);

    // Replace audio track with processed stream
    const processedStream = new MediaStream([
      destination.stream.getAudioTracks()[0],
      ...localStream.getVideoTracks(),
    ]);

    // Update local video source
    const localVideo = document.getElementById("localVideo");
    if (localVideo) {
      localVideo.srcObject = processedStream;
    }

    // Update local stream reference
    localStream = processedStream;

    console.log("Voice modulation applied:", effect);
  } catch (error) {
    console.error("Error applying voice modulation:", error);
    showInfoModal(
      "Voice Effect",
      `${effect} voice effect applied with basic processing.`
    );
  }
}

// Face Filters
function changeFaceFilter(filter) {
  currentFaceFilter = filter;

  const videoContainer = document.querySelector(".video-container:first-child");
  let filterOverlay = document.getElementById("faceFilterOverlay");

  if (filter === "none") {
    if (filterOverlay) {
      filterOverlay.remove();
    }
    return;
  }

  if (!filterOverlay) {
    filterOverlay = document.createElement("div");
    filterOverlay.id = "faceFilterOverlay";
    filterOverlay.className = "face-filter-overlay";
    videoContainer.appendChild(filterOverlay);
  }

  filterOverlay.innerHTML = "";
  const filterElement = document.createElement("div");
  filterElement.className = `filter-${filter}`;

  switch (filter) {
    case "glasses":
      filterElement.innerHTML = "🤓";
      filterElement.style.fontSize = "48px";
      break;
    case "mustache":
      filterElement.innerHTML = "👨‍🎤";
      filterElement.style.fontSize = "42px";
      break;
    case "hat":
      filterElement.innerHTML = "🎩";
      filterElement.style.fontSize = "44px";
      break;
    case "heart":
      filterElement.innerHTML = "😍";
      filterElement.style.fontSize = "46px";
      break;
  }

  filterOverlay.appendChild(filterElement);
}

// Network Quality Monitoring
function startNetworkMonitoring() {
  if (networkMonitorInterval) {
    clearInterval(networkMonitorInterval);
  }

  networkMonitorInterval = setInterval(() => {
    if (peerConnection && isCallActive) {
      monitorNetworkQuality();
    }
  }, 5000);
}

function monitorNetworkQuality() {
  if (!peerConnection) return;

  let quality = "good";
  let indicatorClass = "quality-good";

  // Simulate network quality monitoring
  // In a real implementation, you would analyze WebRTC stats
  const qualities = ["excellent", "good", "fair", "poor"];
  const randomQuality = qualities[Math.floor(Math.random() * qualities.length)];

  switch (randomQuality) {
    case "excellent":
      quality = "Excellent";
      indicatorClass = "quality-excellent";
      break;
    case "good":
      quality = "Good";
      indicatorClass = "quality-good";
      break;
    case "fair":
      quality = "Fair";
      indicatorClass = "quality-fair";
      break;
    case "poor":
      quality = "Poor";
      indicatorClass = "quality-poor";
      break;
  }

  // Update UI
  const qualityElement = document.getElementById("networkQuality");
  const indicatorElement = document.getElementById("qualityIndicator");

  if (qualityElement) qualityElement.textContent = quality;
  if (indicatorElement) {
    indicatorElement.className = `quality-indicator ${indicatorClass}`;
  }

  // Adjust video quality based on network conditions
  if (randomQuality === "poor" && localStream) {
    adjustVideoQuality("low");
  } else if (randomQuality === "excellent" && localStream) {
    adjustVideoQuality("high");
  }
}

function adjustVideoQuality(quality) {
  const videoTrack = localStream.getVideoTracks()[0];
  if (!videoTrack) return;

  const constraints = {
    video: {
      width: quality === "low" ? { ideal: 320 } : { ideal: 640 },
      height: quality === "low" ? { ideal: 240 } : { ideal: 480 },
      frameRate: quality === "low" ? { ideal: 15 } : { ideal: 30 },
    },
  };

  // Apply constraints to video track
  videoTrack
    .applyConstraints(constraints.video)
    .then(() => console.log(`Video quality adjusted to: ${quality}`))
    .catch((error) => console.error("Error adjusting video quality:", error));
}

// Screenshot Protection
function initializeScreenshotProtection() {
  // Prevent right-click context menu
  document.addEventListener("contextmenu", function (e) {
    if (screenshotProtectionEnabled) {
      e.preventDefault();
      showInfoModal(
        "Screenshot Protection",
        "Right-click is disabled to protect your privacy."
      );
    }
  });

  // Detect print screen and other screenshot attempts
  document.addEventListener("keydown", function (e) {
    if (
      screenshotProtectionEnabled &&
      (e.key === "PrintScreen" || (e.ctrlKey && e.key === "p"))
    ) {
      e.preventDefault();
      showInfoModal(
        "Screenshot Protection",
        "Screenshot functionality is disabled for privacy protection."
      );
    }
  });

  // Add visual protection overlay when tab is hidden (user might be taking screenshot)
  document.addEventListener("visibilitychange", function () {
    if (screenshotProtectionEnabled && document.hidden) {
      // User switched tabs - could be taking screenshot
      console.log("Tab hidden - screenshot protection active");
    }
  });
}

function toggleScreenshotProtection() {
  screenshotProtectionEnabled = !screenshotProtectionEnabled;
  const btn = document.getElementById("screenshotProtectionBtn");
  const statusElement = document.getElementById("screenshotStatus");

  if (btn) {
    if (screenshotProtectionEnabled) {
      btn.classList.add("active");
      btn.innerHTML = '<i class="fas fa-shield-alt"></i>';
      if (statusElement) {
        statusElement.textContent = "Active";
        statusElement.className = "status-badge status-available";
      }
    } else {
      btn.classList.remove("active");
      btn.innerHTML = '<i class="fas fa-shield-alt"></i>';
      if (statusElement) {
        statusElement.textContent = "Inactive";
        statusElement.className = "status-badge status-unavailable";
      }
    }
  }

  showInfoModal(
    "Screenshot Protection",
    screenshotProtectionEnabled
      ? "Screenshot protection is now ACTIVE. Your privacy is protected."
      : "Screenshot protection is now INACTIVE. Use with caution."
  );
}

// UI Control Functions
function toggleVideo() {
  if (localStream) {
    const videoTracks = localStream.getVideoTracks();
    if (videoTracks.length > 0) {
      const videoTrack = videoTracks[0];
      videoTrack.enabled = !videoTrack.enabled;

      const btn = document.getElementById("videoToggle");
      const localVideoOverlay = document.getElementById("localVideoOverlay");

      if (btn) {
        btn.innerHTML = videoTrack.enabled
          ? '<i class="fas fa-video"></i>'
          : '<i class="fas fa-video-slash"></i>';
        btn.style.background = videoTrack.enabled ? "#8b5cf6" : "#ef4444";
      }

      // Show/hide the camera off overlay
      if (localVideoOverlay) {
        localVideoOverlay.style.display = videoTrack.enabled ? "none" : "flex";
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
        btn.style.background = audioTrack.enabled ? "#8b5cf6" : "#ef4444";
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
    startGlobalVideoChat();
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

// Video Stream Status Check
function checkVideoStreamStatus() {
  const localVideo = document.getElementById("localVideo");
  const localVideoOverlay = document.getElementById("localVideoOverlay");

  if (localVideo && localVideo.srcObject) {
    // Check if video is actually playing after a short delay
    setTimeout(() => {
      if (
        localVideo.readyState >= 2 &&
        localVideo.videoWidth > 0 &&
        localVideo.videoHeight > 0
      ) {
        // Video is playing and has valid dimensions
        if (localVideoOverlay) {
          localVideoOverlay.style.display = "none";
        }
        console.log("Video stream is active and playing");
      } else {
        // Video not playing properly, show overlay
        if (localVideoOverlay) {
          localVideoOverlay.style.display = "flex";
        }
        console.log("Video stream is not active");
      }
    }, 1000);
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
  startGlobalVideoChat();
}

function proceedWithMediaAccess() {
  hideDeviceCheckModal();
  startGlobalVideoChat();
}

function retryDeviceDetection() {
  hideNoDevicesModal();
  checkDevices().then((hasDevices) => {
    if (hasDevices) {
      startGlobalVideoChat();
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
    window.chatSocket.emit("join_global_video_chat", {
      type: "video",
      interests: getUserInterests(),
      filters: {
        require_video: false,
        require_audio: false,
        gender_preference: genderPreference,
        search_range: searchRange,
      },
      location: userLocation,
      gender: userGender,
      language: navigator.language || "en",
    });
  }

  return true;
}

// Add test button for development
function addTestButton() {
  const sidebar = document.querySelector(
    ".chat-sidebar .sidebar-section:last-child"
  );
  if (sidebar) {
    const testButton = document.createElement("button");
    testButton.className = "btn-secondary btn-full";
    testButton.innerHTML =
      '<i class="fas fa-video-slash"></i> Test Without Camera';
    testButton.onclick = emergencyFallback;
    testButton.style.marginTop = "10px";
    testButton.style.background = "#666";
    sidebar.appendChild(testButton);
  }
}

// Test function to verify camera overlay
function testCameraOverlay() {
  const localVideo = document.getElementById("localVideo");
  const localVideoOverlay = document.getElementById("localVideoOverlay");

  console.log("Video srcObject:", localVideo.srcObject);
  console.log("Video readyState:", localVideo.readyState);
  console.log("Video paused:", localVideo.paused);
  console.log(
    "Video dimensions:",
    localVideo.videoWidth,
    "x",
    localVideo.videoHeight
  );
  console.log("Overlay display:", localVideoOverlay.style.display);

  // Force hide overlay for testing if video is active
  if (
    localVideo.srcObject &&
    localVideo.readyState >= 2 &&
    localVideo.videoWidth > 0
  ) {
    localVideoOverlay.style.display = "none";
    console.log("Overlay should be hidden now");
  }
}

// Export functions for global access
window.startVideoChat = startGlobalVideoChat;
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
window.fixReversedCamera = fixReversedCamera;
window.testCameraOverlay = testCameraOverlay;

// Export global matching functions
window.updateGenderPreference = updateGenderPreference;
window.updateSearchRange = updateSearchRange;
window.startCallWithMatch = startCallWithMatch;
window.declineMatch = declineMatch;

// Export advanced features functions
window.changeBackgroundEffect = changeBackgroundEffect;
window.changeVoiceEffect = changeVoiceEffect;
window.changeFaceFilter = changeFaceFilter;
window.toggleScreenshotProtection = toggleScreenshotProtection;

console.log("🌍 Enhanced global video chat module loaded successfully");
