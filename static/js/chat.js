// =============================================
// COMPLETE REAL-TIME CHAT IMPLEMENTATION
// Enhanced with Global Gender-Based Matching
// =============================================

// Global Variables
let socket;
let currentSessionId = null;
let currentPartner = null;
let chatDurationInterval = null;
let chatStartTime = null;
let isSearching = false;
let waitingPosition = 0;
let typingTimeout = null;
let isTyping = false;
let reconnectAttempts = 0;
let maxReconnectAttempts = 5;

// Message Management
let messageQueue = [];
let pendingMessages = new Map();
let unreadMessages = new Set();

// User Settings
const USER_SETTINGS = {
  soundEnabled: true,
  notifications: true,
  autoTranslate: false,
  toxicityFilter: true,
  suggestReplies: true,
  readReceipts: true,
  typingIndicators: true,
  theme: "dark",
  preferredLanguage: 'en',
  genderPreference: 'opposite'
};

// Initialize Chat Application
function initializeChat() {
  connectSocket();
  loadUserSettings();
  setupEventListeners();
  setupUI();
  initializeUserProfile();

  console.log("🌍 Global chat application initialized");
}

// Socket Connection Management
function connectSocket() {
  socket = io({
    reconnection: true,
    reconnectionAttempts: maxReconnectAttempts,
    reconnectionDelay: 1000,
    reconnectionDelayMax: 5000,
    timeout: 20000,
  });

  // Connection Events
  socket.on("connect", handleSocketConnect);
  socket.on("disconnect", handleSocketDisconnect);
  socket.on("reconnect", handleSocketReconnect);
  socket.on("reconnect_attempt", handleReconnectAttempt);
  socket.on("reconnect_error", handleReconnectError);
  socket.on("reconnect_failed", handleReconnectFailed);
  socket.on("error", handleSocketError);

  // Chat Management Events
  socket.on("connection_established", handleConnectionEstablished);
  socket.on("chat_search_started", handleChatSearchStarted);
  socket.on("chat_search_cancelled", handleChatSearchCancelled);
  socket.on("chat_status_update", handleChatStatusUpdate);
  socket.on("chat_match_found", handleChatMatchFound);
  socket.on("chat_ended", handleChatEnded);
  socket.on("partner_disconnected", handlePartnerDisconnected);

  // Messaging Events
  socket.on("new_message", handleNewMessage);
  socket.on("message_sent", handleMessageSent);
  socket.on("message_delivery_status", handleMessageDeliveryStatus);
  socket.on("message_error", handleMessageError);

  // Typing Indicators
  socket.on("partner_typing", handlePartnerTyping);
  socket.on("partner_stopped_typing", handlePartnerStoppedTyping);

  // User Presence
  socket.on("user_online_status", handleUserOnlineStatus);
  socket.on("online_count_update", handleOnlineCountUpdate);

  // Voice/Video Chat
  socket.on("voice_chat_invitation", handleVoiceChatInvitation);
  socket.on("voice_chat_response", handleVoiceChatResponse);
  socket.on("voice_chat_started", handleVoiceChatStarted);
  socket.on("webrtc_signal", handleWebRTCSignal);

  // Media Sharing
  socket.on("media_message", handleMediaMessage);
  socket.on("media_sent", handleMediaSent);
  socket.on("media_error", handleMediaError);

  // System Events
  socket.on("report_submitted", handleReportSubmitted);
  socket.on("user_blocked", handleUserBlocked);
}

// Connection Event Handlers
function handleSocketConnect() {
  console.log("✅ Connected to server");
  updateConnectionStatus("connected");
  reconnectAttempts = 0;
  showNotification(
    "Connected",
    "You are now connected to the global chat server",
    "success"
  );

  // Process any queued messages
  processMessageQueue();
}

function handleSocketDisconnect(reason) {
  console.log("❌ Disconnected from server:", reason);
  updateConnectionStatus("disconnected");

  if (reason === "io server disconnect") {
    // Server initiated disconnect, need to manually reconnect
    socket.connect();
  }
}

function handleSocketReconnect(attemptNumber) {
  console.log("🔄 Reconnected to server after", attemptNumber, "attempts");
  updateConnectionStatus("connected");
  showNotification(
    "Reconnected",
    "Connection to chat server restored",
    "success"
  );
}

function handleReconnectAttempt(attemptNumber) {
  console.log("🔄 Reconnection attempt:", attemptNumber);
  updateConnectionStatus("reconnecting");
  reconnectAttempts = attemptNumber;
}

function handleReconnectError(error) {
  console.log("❌ Reconnection error:", error);
}

function handleReconnectFailed() {
  console.log("💥 Failed to reconnect after", maxReconnectAttempts, "attempts");
  updateConnectionStatus("failed");
  showNotification(
    "Connection Failed",
    "Unable to connect to chat server. Please refresh the page.",
    "error"
  );
}

function handleSocketError(error) {
  console.error("💥 Socket error:", error);
  showNotification(
    "Connection Error",
    "An error occurred with the chat connection",
    "error"
  );
}

function handleConnectionEstablished(data) {
  console.log("🌍 Connection established:", data);
  updateOnlineCount(data.online_users);
  updateGlobalStats(data);
}

// Global Chat Management Functions
function startGlobalChat(chatType = "text", interests = [], language = 'en') {
  if (!socket || isSearching) return;

  const userInterests = interests.length > 0 ? interests : getDefaultInterests();
  
  // Get user's location from browser if available
  getUserLocation().then(location => {
    socket.emit("start_chat_search", {
      type: chatType,
      interests: userInterests,
      filters: getChatFilters(),
      language: language,
      location: location
    });

    updateUIForGlobalSearch();
    addSystemMessage("🌍 Searching for a chat partner worldwide...");
    showGlobalSearchIndicator();
  }).catch(error => {
    console.log("📍 Location detection failed, using global search");
    // Fallback without location
    socket.emit("start_chat_search", {
      type: chatType,
      interests: userInterests,
      filters: getChatFilters(),
      language: language
    });

    updateUIForGlobalSearch();
    addSystemMessage("🌍 Searching for a chat partner worldwide...");
    showGlobalSearchIndicator();
  });
}

function startChat(chatType = "text", interests = []) {
  // Alias for global chat
  startGlobalChat(chatType, interests);
}

function cancelChatSearch() {
  if (!socket || !isSearching) return;

  socket.emit("cancel_chat_search", {
    type: "text",
  });

  isSearching = false;
  updateUIForIdle();
  hideGlobalSearchIndicator();
  addSystemMessage("Chat search cancelled");
}

function endChat(reason = "user_left") {
  if (!currentSessionId) return;

  socket.emit("end_chat", {
    session_id: currentSessionId,
    reason: reason,
  });

  cleanupChat();
  addSystemMessage("Chat ended");
}

function nextChat() {
  if (currentSessionId) {
    endChat("next_chat_requested");
  }

  // Start new search after a short delay
  setTimeout(() => {
    startGlobalChat();
  }, 1000);
}

function getChatStatus() {
  if (!socket) return;

  socket.emit("get_chat_status", {
    type: "text",
  });
}

// Event Handlers for Chat Management
function handleChatSearchStarted(data) {
  console.log("🔍 Chat search started:", data);
  isSearching = true;
  waitingPosition = data.position;

  updateUIForGlobalSearch();
  updateWaitingInfo(data);
  
  let searchMessage = `🌍 Searching globally for partners...`;
  if (data.searching_globally) {
    searchMessage += ` Position ${data.position} in queue`;
  }
  
  addSystemMessage(searchMessage);
}

function handleChatSearchCancelled(data) {
  console.log("❌ Chat search cancelled:", data);
  isSearching = false;
  updateUIForIdle();
  hideGlobalSearchIndicator();
  addSystemMessage("Chat search cancelled");
}

function handleChatStatusUpdate(data) {
  console.log("📊 Chat status update:", data);
  updateWaitingInfo(data);
}

function handleChatMatchFound(data) {
  console.log("🎉 Chat match found:", data);
  isSearching = false;
  currentSessionId = data.session_id;
  currentPartner = {
    id: data.partner_id,
    name: data.partner_name,
    interests: data.partner_interests,
    gender: data.partner_gender,
    location: data.partner_location
  };

  updateUIForChatting();
  startChatTimer();
  hideGlobalSearchIndicator();

  let welcomeMessage = `🎉 Connected with ${data.partner_name || 'a stranger'}!`;
  
  // Add location info
  if (data.partner_location && data.partner_location !== 'Unknown') {
    welcomeMessage += ` from ${data.partner_location}`;
  }
  
  // Add gender info
  if (data.partner_gender && data.partner_gender !== 'Not specified') {
    welcomeMessage += ` (${data.partner_gender})`;
  }
  
  // Add common interests
  if (data.common_interests && data.common_interests.length > 0) {
    welcomeMessage += ` | Common interests: ${data.common_interests.join(", ")}`;
  }
  
  // Add match type
  if (data.match_type === 'gender_based') {
    welcomeMessage += ` | 🎯 Gender-based match`;
  } else {
    welcomeMessage += ` | 🤝 Interest-based match`;
  }

  addSystemMessage(welcomeMessage, "success");
  playNotificationSound("connected");

  // Show connection quality indicator
  showConnectionQuality(data.partner_location);

  // Clear any existing messages
  clearMessageQueue();
}

function handleChatEnded(data) {
  console.log("🔚 Chat ended:", data);

  let endMessage = "Chat session ended";
  if (data.partner_left) {
    endMessage = "Partner left the chat";
  } else if (data.reason === 'user_reported') {
    endMessage = "Chat ended due to user report";
  } else if (data.reason === 'user_blocked') {
    endMessage = "User blocked";
  } else if (data.reason === 'partner_banned') {
    endMessage = "Partner was banned";
  }

  addSystemMessage(endMessage);
  cleanupChat();
}

function handlePartnerDisconnected(data) {
  console.log("🔌 Partner disconnected:", data);
  addSystemMessage("Partner disconnected. They may reconnect...");
  updateConnectionStatus("partner_disconnected");
}

// Messaging System
function sendMessage() {
  const messageInput = document.getElementById("messageInput");
  const message = messageInput.value.trim();

  if (!message || !currentSessionId) return;

  const tempId = generateTempId();
  const timestamp = new Date().toISOString();

  // Add to pending messages
  pendingMessages.set(tempId, {
    content: message,
    timestamp: timestamp,
    status: "sending",
  });

  // Show message immediately
  const messageElementId = addMessage(
    message,
    "own",
    timestamp,
    null,
    "neutral",
    tempId
  );

  // Send via socket
  if (socket.connected) {
    socket.emit("send_message", {
      session_id: currentSessionId,
      message: message,
      temp_id: tempId,
      type: "text",
    });
  } else {
    // Queue message for when connection is restored
    messageQueue.push({
      session_id: currentSessionId,
      message: message,
      temp_id: tempId,
      type: "text",
    });
  }

  // Clear input and hide typing indicator
  messageInput.value = "";
  hideTypingIndicator();
  stopTypingIndicator();

  // Hide suggested replies
  hideSuggestedReplies();

  console.log("💬 Message sent:", { tempId, message });
}

function sendMediaMessage(file) {
  if (!currentSessionId || !file) return;

  const tempId = generateTempId();
  const reader = new FileReader();

  reader.onload = function (e) {
    const fileData = e.target.result;

    // Show upload preview
    showMediaPreview(file, tempId);

    // Send via socket
    socket.emit("send_media", {
      session_id: currentSessionId,
      file_data: fileData,
      file_name: file.name,
      file_type: file.type,
      file_size: file.size,
      temp_id: tempId,
    });
  };

  reader.readAsDataURL(file);
}

// Message Event Handlers
function handleNewMessage(data) {
  console.log("📩 New message received:", data);

  // Add message to chat
  const messageId = addMessage(
    data.content,
    "other",
    data.timestamp,
    null,
    "neutral",
    data.id
  );

  // Mark as unread until user views it
  unreadMessages.add(data.id);

  // Play notification sound
  playNotificationSound("message");

  // Generate suggested replies
  if (USER_SETTINGS.suggestReplies) {
    generateSuggestedReplies(data.content);
  }

  // Auto-translate if enabled
  if (USER_SETTINGS.autoTranslate) {
    translateMessage(data.content, messageId);
  }

  // Send delivery confirmation
  socket.emit("message_delivered", {
    message_id: data.id,
    session_id: data.session_id,
  });

  // Mark as read if chat is active
  markMessageAsRead(data.id, data.session_id);
}

function handleMessageSent(data) {
  console.log("✅ Message sent confirmation:", data);

  // Update message status from sending to sent
  updateMessageStatus(data.temp_id, "sent");

  // Update the temporary ID to permanent ID in pending messages
  if (pendingMessages.has(data.temp_id)) {
    const messageData = pendingMessages.get(data.temp_id);
    pendingMessages.delete(data.temp_id);
    pendingMessages.set(data.message_id, {
      ...messageData,
      status: "sent",
    });
  }
}

function handleMessageDeliveryStatus(data) {
  console.log("📨 Message delivery status:", data);
  updateMessageStatus(data.message_id, data.status);
}

function handleMessageError(data) {
  console.error("❌ Message error:", data);
  updateMessageStatus(data.temp_id, "failed");
  showNotification(
    "Message Failed",
    "Failed to send message. Please try again.",
    "error"
  );
}

// Typing Indicators
function startTypingIndicator() {
  if (!currentSessionId || isTyping) return;

  isTyping = true;
  socket.emit("start_typing", {
    session_id: currentSessionId,
  });
}

function stopTypingIndicator() {
  if (!currentSessionId || !isTyping) return;

  isTyping = false;
  socket.emit("stop_typing", {
    session_id: currentSessionId,
  });
}

function handlePartnerTyping(data) {
  if (USER_SETTINGS.typingIndicators) {
    showTypingIndicator(data.user_name);
  }
}

function handlePartnerStoppedTyping(data) {
  hideTypingIndicator();
}

// Voice/Video Chat
function requestVoiceChat() {
  if (!currentSessionId) return;

  socket.emit("voice_chat_request", {
    session_id: currentSessionId,
  });

  showNotification("Voice Chat", "Voice chat request sent to partner", "info");
}

function handleVoiceChatInvitation(data) {
  if (confirm(`${data.from_user_name} wants to start a voice chat. Accept?`)) {
    socket.emit("voice_chat_response", {
      session_id: data.session_id,
      accepted: true,
    });
  } else {
    socket.emit("voice_chat_response", {
      session_id: data.session_id,
      accepted: false,
    });
  }
}

function handleVoiceChatResponse(data) {
  if (data.accepted) {
    showNotification(
      "Voice Chat",
      "Voice chat accepted! Starting...",
      "success"
    );
    initializeVoiceChat();
  } else {
    showNotification(
      "Voice Chat",
      "Voice chat request was declined",
      "warning"
    );
  }
}

function handleVoiceChatStarted(data) {
  showNotification(
    "Voice Chat",
    "Voice chat started! You can now speak.",
    "success"
  );
  // Initialize WebRTC connection here
}

// WebRTC Signaling
function handleWebRTCSignal(data) {
  // Handle WebRTC signaling for voice/video chat
  console.log("📡 WebRTC signal received:", data);
  // Implement WebRTC signal handling based on your WebRTC implementation
}

// Media Sharing
function handleMediaMessage(data) {
  console.log("🖼️ Media message received:", data);

  // Add media message to chat
  addMediaMessage(data, "other");
  playNotificationSound("media");
}

function handleMediaSent(data) {
  console.log("✅ Media sent confirmation:", data);
  updateMediaMessageStatus(data.temp_id, "sent");
}

function handleMediaError(data) {
  console.error("❌ Media error:", data);
  updateMediaMessageStatus(data.temp_id, "failed");
  showNotification(
    "Media Upload Failed",
    data.error || "Failed to send media",
    "error"
  );
}

// Moderation & Safety
function reportUser(reason, additionalInfo = "") {
  if (!currentSessionId) return;

  socket.emit("report_user", {
    session_id: currentSessionId,
    reason: reason,
    type: "inappropriate_behavior",
    additional_info: additionalInfo,
  });
}

function blockUser() {
  if (!currentPartner) return;

  socket.emit("block_user", {
    user_id: currentPartner.id,
    session_id: currentSessionId,
  });
}

function handleReportSubmitted(data) {
  showNotification(
    "Report Submitted",
    "Thank you for your report. We will review it shortly.",
    "success"
  );
}

function handleUserBlocked(data) {
  showNotification(
    "User Blocked",
    "User has been blocked successfully.",
    "success"
  );
}

// User Presence
function handleUserOnlineStatus(data) {
  // Update user status in UI if needed
  console.log("👤 User online status:", data);
}

function handleOnlineCountUpdate(data) {
  updateOnlineCount(data.count);
}

// Global Chat UI Management Functions
function updateConnectionStatus(status) {
  const statusElement = document.getElementById("chatStatus");
  const connectionStatus = document.getElementById("connectionStatus");

  const statusConfig = {
    connected: { text: "🌍 Connected Globally", class: "connected" },
    disconnected: { text: "Disconnected", class: "disconnected" },
    reconnecting: { text: "Reconnecting...", class: "reconnecting" },
    failed: { text: "Connection Failed", class: "failed" },
    searching: { text: "Searching Locally", class: "searching" },
    searching_global: { text: "🌍 Searching Worldwide", class: "searching-global" },
    partner_disconnected: { text: "Partner Disconnected", class: "warning" },
  };

  const config = statusConfig[status] || statusConfig.disconnected;

  if (statusElement) {
    statusElement.textContent = config.text;
    statusElement.className = `chat-status ${config.class}`;
  }

  if (connectionStatus) {
    connectionStatus.textContent = config.text;
  }
}

function updateUIForGlobalSearch() {
  document.getElementById("startChatBtn").disabled = true;
  document.getElementById("nextChatBtn").disabled = true;
  document.getElementById("endChatBtn").disabled = false;
  document.getElementById("messageInput").disabled = true;
  document.getElementById("sendBtn").disabled = true;

  updateConnectionStatus("searching_global");
  showGlobalSearchStats();
}

function updateUIForChatting() {
  document.getElementById("startChatBtn").disabled = true;
  document.getElementById("nextChatBtn").disabled = false;
  document.getElementById("endChatBtn").disabled = false;
  document.getElementById("messageInput").disabled = false;
  document.getElementById("sendBtn").disabled = false;

  updateConnectionStatus("connected");
  hideWaitingInfo();
  hideGlobalSearchIndicator();
}

function updateUIForIdle() {
  document.getElementById("startChatBtn").disabled = false;
  document.getElementById("nextChatBtn").disabled = true;
  document.getElementById("endChatBtn").disabled = true;
  document.getElementById("messageInput").disabled = true;
  document.getElementById("sendBtn").disabled = true;

  updateConnectionStatus("disconnected");
  hideGlobalSearchIndicator();
}

function updateWaitingInfo(data) {
  const waitingInfo = document.getElementById("waitingInfo");
  if (!waitingInfo) return;

  if (data.in_queue) {
    waitingInfo.innerHTML = `
            <div class="waiting-position">Position: ${data.position}/${data.total_waiting}</div>
            <div class="estimated-wait">Est. wait: ${data.estimated_wait}s</div>
            <div class="waiting-progress">
                <div class="progress-bar">
                    <div class="progress-fill" style="width: ${(data.position / data.total_waiting) * 100}%"></div>
                </div>
            </div>
        `;
    waitingInfo.style.display = "block";
  } else {
    waitingInfo.style.display = "none";
  }
}

function hideWaitingInfo() {
  const waitingInfo = document.getElementById("waitingInfo");
  if (waitingInfo) {
    waitingInfo.style.display = "none";
  }
}

function showGlobalSearchIndicator() {
  const searchInfo = document.getElementById("searchInfo");
  if (searchInfo) {
    searchInfo.innerHTML = `
            <div class="global-search-indicator">
                <i class="fas fa-globe-americas"></i>
                <span>Searching globally for opposite gender partners...</span>
                <div class="searching-animation">
                    <div class="pulse-dot"></div>
                    <div class="pulse-dot"></div>
                    <div class="pulse-dot"></div>
                </div>
            </div>
        `;
  }
}

function hideGlobalSearchIndicator() {
  const searchInfo = document.getElementById("searchInfo");
  if (searchInfo) {
    searchInfo.innerHTML = '';
  }
}

function showGlobalSearchStats() {
  const statsElement = document.getElementById('globalStats');
  if (statsElement) {
    statsElement.innerHTML = `
            <div class="global-stats">
                <div class="stat-item">
                    <i class="fas fa-users"></i>
                    <span>Searching worldwide</span>
                </div>
                <div class="stat-item">
                    <i class="fas fa-venus-mars"></i>
                    <span>Opposite gender matching</span>
                </div>
                <div class="stat-item">
                    <i class="fas fa-bolt"></i>
                    <span>Real-time connection</span>
                </div>
            </div>
        `;
  }
}

function showConnectionQuality(partnerLocation) {
  const qualityIndicator = document.querySelector('.connection-quality');
  if (qualityIndicator) {
    qualityIndicator.innerHTML = `
            <div class="quality-info">
                <i class="fas fa-signal"></i>
                <span>Global Connection</span>
                <small>Partner: ${partnerLocation || 'Unknown location'}</small>
            </div>
        `;
    qualityIndicator.style.display = 'block';
  }
}

function updateOnlineCount(count) {
  const onlineCountElement = document.getElementById("onlineCount");
  if (onlineCountElement) {
    onlineCountElement.textContent = `${count} users online`;
  }
}

function updateGlobalStats(data) {
  // Update any global statistics in the UI
  const globalStats = document.getElementById('globalStats');
  if (globalStats && data.global_stats) {
    // Update with real global stats if available
  }
}

function showTypingIndicator(partnerName = "Stranger") {
  const indicator = document.getElementById("typingIndicator");
  if (indicator) {
    indicator.innerHTML = `<span class="typing-dots"></span> ${partnerName} is typing...`;
    indicator.style.display = "block";
  }
}

function hideTypingIndicator() {
  const indicator = document.getElementById("typingIndicator");
  if (indicator) {
    indicator.style.display = "none";
  }
}

// Message Display Functions
function addMessage(
  content,
  type,
  timestamp,
  translation = null,
  tone = "neutral",
  messageId = null
) {
  const messagesContainer = document.getElementById("chatMessages");
  if (!messagesContainer) return null;

  const messageElement = document.createElement("div");
  messageElement.className = `message ${type}`;
  messageElement.dataset.messageId = messageId || generateTempId();

  const actualMessageId = messageElement.dataset.messageId;
  const formattedTime = formatTime(timestamp);

  let toneIndicator = "";
  if (tone !== "neutral") {
    toneIndicator = `<span class="tone-indicator tone-${tone}" title="${tone}">${getToneEmoji(
      tone
    )}</span>`;
  }

  let translationHtml = "";
  if (translation) {
    translationHtml = `<div class="translation">${escapeHtml(
      translation
    )}</div>`;
  }

  let statusHtml = "";
  if (type === "own") {
    statusHtml = `<span class="message-status" id="status-${actualMessageId}">⏱</span>`;
  }

  messageElement.innerHTML = `
        <div class="message-content">
            <div class="message-text">${escapeHtml(content)}</div>
            ${toneIndicator}
            ${statusHtml}
        </div>
        ${translationHtml}
        <div class="message-time">${formattedTime}</div>
    `;

  messagesContainer.appendChild(messageElement);
  scrollToBottom();

  // Remove welcome message if it exists
  removeWelcomeMessage();

  return actualMessageId;
}

function addMediaMessage(data, type) {
  const messagesContainer = document.getElementById("chatMessages");
  if (!messagesContainer) return;

  const messageElement = document.createElement("div");
  messageElement.className = `message ${type} media-message`;
  messageElement.dataset.messageId = data.message_id;

  const formattedTime = formatTime(data.timestamp);

  let mediaContent = "";
  if (data.file_type.startsWith("image/")) {
    mediaContent = `
            <div class="media-content image-content">
                <img src="${data.preview_url}" alt="${data.file_name}" class="media-preview">
                <div class="media-info">Image: ${data.file_name}</div>
            </div>
        `;
  } else if (data.file_type.startsWith("audio/")) {
    mediaContent = `
            <div class="media-content audio-content">
                <i class="fas fa-music"></i>
                <div class="media-info">Audio: ${data.file_name}</div>
                <audio controls>
                    <source src="${data.preview_url}" type="${data.file_type}">
                </audio>
            </div>
        `;
  } else {
    mediaContent = `
            <div class="media-content file-content">
                <i class="fas fa-file"></i>
                <div class="media-info">File: ${data.file_name}</div>
                <a href="${data.preview_url}" download="${data.file_name}" class="download-btn">Download</a>
            </div>
        `;
  }

  messageElement.innerHTML = `
        <div class="message-content">
            ${mediaContent}
        </div>
        <div class="message-time">${formattedTime}</div>
    `;

  messagesContainer.appendChild(messageElement);
  scrollToBottom();
  removeWelcomeMessage();
}

function updateMessageStatus(messageId, status) {
  const statusElement = document.getElementById(`status-${messageId}`);
  if (!statusElement) return;

  const statusConfig = {
    sending: { text: "⏱", class: "sending" },
    sent: { text: "✓", class: "sent" },
    delivered: { text: "✓", class: "delivered" },
    read: { text: "✓✓", class: "read" },
    failed: { text: "✗", class: "failed" },
  };

  const config = statusConfig[status] || statusConfig.sending;

  statusElement.textContent = config.text;
  statusElement.className = `message-status ${config.class}`;

  // Update in pending messages
  if (pendingMessages.has(messageId)) {
    const message = pendingMessages.get(messageId);
    message.status = status;
    pendingMessages.set(messageId, message);
  }
}

function updateMediaMessageStatus(tempId, status) {
  const messageElement = document.querySelector(
    `[data-message-id="${tempId}"]`
  );
  if (!messageElement) return;

  if (status === "sent") {
    messageElement.classList.add("sent");
  } else if (status === "failed") {
    messageElement.classList.add("failed");
    messageElement.innerHTML +=
      '<div class="upload-failed">Upload failed</div>';
  }
}

// Utility Functions
function generateTempId() {
  return "temp_" + Date.now() + "_" + Math.random().toString(36).substr(2, 9);
}

function formatTime(timestamp) {
  const date = new Date(timestamp);
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function formatDuration(seconds) {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins.toString().padStart(2, "0")}:${secs
    .toString()
    .padStart(2, "0")}`;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function getToneEmoji(tone) {
  const emojis = {
    happy: "😊",
    sad: "😢",
    excited: "🎉",
    angry: "😠",
    neutral: "",
  };
  return emojis[tone] || "";
}

function scrollToBottom() {
  const messagesContainer = document.getElementById("chatMessages");
  if (messagesContainer) {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }
}

function removeWelcomeMessage() {
  const welcomeMessage = document.querySelector(".welcome-message");
  if (welcomeMessage) {
    welcomeMessage.remove();
  }
}

function addSystemMessage(content, type = "info") {
  const messagesContainer = document.getElementById("chatMessages");
  if (!messagesContainer) return;

  const messageElement = document.createElement("div");
  messageElement.className = `message system system-${type}`;

  messageElement.innerHTML = `
        <div class="system-content">
            <i class="fas fa-info-circle"></i>
            <span>${escapeHtml(content)}</span>
        </div>
        <div class="message-time">${formatTime(new Date().toISOString())}</div>
    `;

  messagesContainer.appendChild(messageElement);
  scrollToBottom();
  removeWelcomeMessage();
}

// Chat Timer
function startChatTimer() {
  chatStartTime = new Date();
  chatDurationInterval = setInterval(updateChatDuration, 1000);
}

function stopChatTimer() {
  if (chatDurationInterval) {
    clearInterval(chatDurationInterval);
    chatDurationInterval = null;
  }
  document.getElementById("chatDuration").textContent = "00:00";
}

function updateChatDuration() {
  if (chatStartTime) {
    const now = new Date();
    const duration = Math.floor((now - chatStartTime) / 1000);
    document.getElementById("chatDuration").textContent =
      formatDuration(duration);
  }
}

// Notification System
function showNotification(title, message, type = "info") {
  if (!USER_SETTINGS.notifications) return;

  // Create notification element
  const notification = document.createElement("div");
  notification.className = `notification notification-${type}`;
  notification.innerHTML = `
        <div class="notification-header">
            <strong>${title}</strong>
            <button class="notification-close">&times;</button>
        </div>
        <div class="notification-body">${message}</div>
    `;

  // Add to notification container
  const container =
    document.getElementById("notificationContainer") ||
    createNotificationContainer();
  container.appendChild(notification);

  // Auto-remove after 5 seconds
  setTimeout(() => {
    if (notification.parentNode) {
      notification.remove();
    }
  }, 5000);

  // Close button event
  notification.querySelector(".notification-close").onclick = () =>
    notification.remove();

  // Play sound for important notifications
  if (type === "error" || type === "success") {
    playNotificationSound(type);
  }
}

function createNotificationContainer() {
  const container = document.createElement("div");
  container.id = "notificationContainer";
  container.className = "notification-container";
  document.body.appendChild(container);
  return container;
}

function playNotificationSound(type = "message") {
  if (!USER_SETTINGS.soundEnabled) return;

  const sounds = {
    message: "message_sound",
    connected: "connected_sound",
    disconnected: "disconnected_sound",
    error: "error_sound",
    success: "success_sound",
    media: "media_sound",
  };

  const soundId = sounds[type];
  if (soundId) {
    // In a real implementation, you'd play actual audio files
    console.log("🔊 Playing sound:", soundId);
    
    // Simple browser notification sound
    try {
      const audioContext = new (window.AudioContext || window.webkitAudioContext)();
      const oscillator = audioContext.createOscillator();
      const gainNode = audioContext.createGain();
      
      oscillator.connect(gainNode);
      gainNode.connect(audioContext.destination);
      
      oscillator.type = 'sine';
      
      if (type === 'message') {
        oscillator.frequency.setValueAtTime(800, audioContext.currentTime);
      } else if (type === 'connected') {
        oscillator.frequency.setValueAtTime(1000, audioContext.currentTime);
      } else if (type === 'error') {
        oscillator.frequency.setValueAtTime(400, audioContext.currentTime);
      }
      
      gainNode.gain.setValueAtTime(0.1, audioContext.currentTime);
      gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.2);
      
      oscillator.start(audioContext.currentTime);
      oscillator.stop(audioContext.currentTime + 0.2);
    } catch (e) {
      console.log("🔇 Audio context not supported");
    }
  }
}

// Settings Management
function loadUserSettings() {
  const savedSettings = localStorage.getItem("chatSettings");
  if (savedSettings) {
    Object.assign(USER_SETTINGS, JSON.parse(savedSettings));
  }
  applyUserSettings();
}

function saveUserSettings() {
  localStorage.setItem("chatSettings", JSON.stringify(USER_SETTINGS));
}

function applyUserSettings() {
  // Apply theme
  document.documentElement.setAttribute("data-theme", USER_SETTINGS.theme);

  // Apply other settings as needed
  console.log("⚙️ User settings applied:", USER_SETTINGS);
}

function updateSetting(setting, value) {
  USER_SETTINGS[setting] = value;
  saveUserSettings();
  applyUserSettings();
}

// Location Services
function getUserLocation() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      // Fallback to timezone-based location
      const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
      resolve(timezone || "Global");
      return;
    }

    // Get approximate location from browser
    navigator.geolocation.getCurrentPosition(
      position => {
        const { latitude, longitude } = position.coords;
        
        // Try to get location name from coordinates (simplified)
        getLocationNameFromCoords(latitude, longitude)
          .then(locationName => {
            resolve(locationName || `${latitude.toFixed(2)}, ${longitude.toFixed(2)}`);
          })
          .catch(() => {
            resolve(`${latitude.toFixed(2)}, ${longitude.toFixed(2)}`);
          });
      },
      error => {
        console.log("📍 Geolocation error:", error);
        // Fallback to IP-based location or timezone
        const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
        resolve(timezone || "Global");
      },
      { 
        timeout: 5000, 
        enableHighAccuracy: false,
        maximumAge: 300000 // 5 minutes
      }
    );
  });
}

function getLocationNameFromCoords(lat, lng) {
  // This would typically use a reverse geocoding service
  // For demo purposes, return a mock location based on coordinates
  return new Promise((resolve) => {
    // Mock implementation - in production, use a real geocoding service
    const locations = [
      "North America", "Europe", "Asia", "South America", 
      "Africa", "Australia", "Middle East"
    ];
    
    // Simple region detection based on coordinates
    let region = "Global";
    if (lat > 0 && lng > -30 && lng < 40) region = "Europe";
    else if (lat > 0 && lng > 70 && lng < 140) region = "Asia";
    else if (lat > 0 && lng < -30) region = "North America";
    else if (lat < 0 && lng > -80 && lng < -35) region = "South America";
    else if (lat < 0 && lng > 110 && lng < 155) region = "Australia";
    else if (lat > -10 && lat < 40 && lng > 20 && lng < 60) region = "Middle East";
    else if (lat < 0 && lat > -35 && lng > 10 && lng < 50) region = "Africa";
    
    resolve(region);
  });
}

// Media Preview and Upload
function showMediaPreview(file, tempId) {
  const messagesContainer = document.getElementById("chatMessages");
  if (!messagesContainer) return;

  const previewElement = document.createElement("div");
  previewElement.className = "message own media-message uploading";
  previewElement.dataset.tempId = tempId;

  let previewContent = "";
  if (file.type.startsWith("image/")) {
    const reader = new FileReader();
    reader.onload = function (e) {
      previewContent = `
                <div class="media-content image-content">
                    <img src="${e.target.result}" alt="${file.name}" class="media-preview">
                    <div class="media-info">Uploading: ${file.name}</div>
                    <div class="upload-progress">
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: 0%"></div>
                        </div>
                    </div>
                </div>
            `;
      previewElement.innerHTML =
        previewContent +
        `<div class="message-time">${formatTime(
          new Date().toISOString()
        )}</div>`;
    };
    reader.readAsDataURL(file);
  } else {
    previewContent = `
            <div class="media-content file-content">
                <i class="fas fa-file"></i>
                <div class="media-info">Uploading: ${file.name}</div>
                <div class="upload-progress">
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: 0%"></div>
                    </div>
                </div>
            </div>
        `;
    previewElement.innerHTML =
      previewContent +
      `<div class="message-time">${formatTime(new Date().toISOString())}</div>`;
  }

  messagesContainer.appendChild(previewElement);
  scrollToBottom();
  removeWelcomeMessage();
}

// Suggested Replies
function generateSuggestedReplies(message) {
  if (!USER_SETTINGS.suggestReplies) return;

  const replies = getSuggestedReplies(message);
  displaySuggestedReplies(replies);
}

function getSuggestedReplies(message) {
  const lowerMessage = message.toLowerCase();

  // Greeting responses
  if (
    lowerMessage.includes("hello") ||
    lowerMessage.includes("hi") ||
    lowerMessage.includes("hey")
  ) {
    return ["Hello!", "Hi there!", "Hey! How are you?", "Nice to meet you!"];
  }

  // How are you responses
  if (lowerMessage.includes("how are you")) {
    return [
      "I'm good, thanks!",
      "Doing well, how about you?",
      "Great! How are you?",
      "Pretty good!",
    ];
  }

  // Question responses
  if (lowerMessage.includes("?")) {
    return [
      "Interesting question!",
      "I'm not sure",
      "What do you think?",
      "That's a good question",
    ];
  }

  // Default conversation continuers
  return [
    "Interesting!",
    "Tell me more",
    "I see",
    "That's cool",
    "Really?",
    "Wow!",
  ];
}

function displaySuggestedReplies(replies) {
  const container = document.getElementById("suggestedReplies");
  if (!container) return;

  container.innerHTML = "";

  replies.slice(0, 4).forEach((reply) => {
    const button = document.createElement("button");
    button.className = "suggested-reply";
    button.textContent = reply;
    button.onclick = () => {
      document.getElementById("messageInput").value = reply;
      sendMessage();
      container.style.display = "none";
    };
    container.appendChild(button);
  });

  container.style.display = "flex";
}

function hideSuggestedReplies() {
  const container = document.getElementById("suggestedReplies");
  if (container) {
    container.style.display = "none";
  }
}

// Translation (Mock Implementation)
function translateMessage(message, messageId) {
  // Mock translation - in real implementation, use a translation API
  setTimeout(() => {
    const translation = `Translated: ${message}`;
    addTranslationToMessage(messageId, translation);
  }, 1000);
}

function addTranslationToMessage(messageId, translation) {
  const messageElement = document.querySelector(
    `[data-message-id="${messageId}"]`
  );
  if (messageElement) {
    const translationElement = document.createElement("div");
    translationElement.className = "translation";
    translationElement.textContent = translation;
    messageElement
      .querySelector(".message-content")
      .appendChild(translationElement);
  }
}

// Queue Management
function processMessageQueue() {
  while (messageQueue.length > 0 && socket.connected) {
    const messageData = messageQueue.shift();
    socket.emit("send_message", messageData);
  }
}

function clearMessageQueue() {
  messageQueue = [];
  pendingMessages.clear();
  unreadMessages.clear();
}

function cleanupChat() {
  currentSessionId = null;
  currentPartner = null;
  isSearching = false;

  stopChatTimer();
  stopTypingIndicator();
  hideTypingIndicator();
  hideSuggestedReplies();
  clearMessageQueue();
  hideGlobalSearchIndicator();

  updateUIForIdle();
  resetChatUI();
}

function resetChatUI() {
  const messagesContainer = document.getElementById("chatMessages");
  if (messagesContainer) {
    messagesContainer.innerHTML = `
            <div class="welcome-message">
                <i class="fas fa-globe-americas"></i>
                <h3>Welcome to Global Chat</h3>
                <p>Connect with people worldwide. We match males with females for better conversations.</p>
                <div class="feature-list">
                    <div class="feature">
                        <i class="fas fa-venus-mars"></i>
                        <span>Gender-based matching</span>
                    </div>
                    <div class="feature">
                        <i class="fas fa-globe"></i>
                        <span>Worldwide connections</span>
                    </div>
                    <div class="feature">
                        <i class="fas fa-shield-alt"></i>
                        <span>Safe & anonymous</span>
                    </div>
                </div>
            </div>
        `;
  }
}

// Setup Functions
function setupEventListeners() {
  // Message input events
  const messageInput = document.getElementById("messageInput");
  const sendBtn = document.getElementById("sendBtn");

  if (messageInput) {
    messageInput.addEventListener("keypress", function (e) {
      if (e.key === "Enter") {
        sendMessage();
      }
    });

    messageInput.addEventListener("input", function () {
      if (this.value.trim() && currentSessionId) {
        startTypingIndicator();
      } else {
        stopTypingIndicator();
      }
    });

    messageInput.addEventListener("blur", function () {
      stopTypingIndicator();
    });
  }

  if (sendBtn) {
    sendBtn.addEventListener("click", sendMessage);
  }

  // Chat control buttons
  const startBtn = document.getElementById("startChatBtn");
  const nextBtn = document.getElementById("nextChatBtn");
  const endBtn = document.getElementById("endChatBtn");

  if (startBtn) startBtn.addEventListener("click", () => startGlobalChat());
  if (nextBtn) nextBtn.addEventListener("click", nextChat);
  if (endBtn) endBtn.addEventListener("click", () => endChat());

  // File upload
  const fileInput = document.getElementById("fileInput");
  if (fileInput) {
    fileInput.addEventListener("change", function (e) {
      const file = e.target.files[0];
      if (file) {
        sendMediaMessage(file);
      }
    });
  }

  // Media upload button
  const mediaBtn = document.getElementById("mediaBtn");
  if (mediaBtn) {
    mediaBtn.addEventListener("click", () => {
      document.getElementById("fileInput").click();
    });
  }

  // Voice chat button
  const voiceBtn = document.getElementById("voiceChatBtn");
  if (voiceBtn) {
    voiceBtn.addEventListener("click", requestVoiceChat);
  }

  // Report and block buttons
  const reportBtn = document.getElementById("reportBtn");
  if (reportBtn) {
    reportBtn.addEventListener("click", () => {
      const reason = prompt("Please enter the reason for reporting:");
      if (reason) {
        reportUser(reason);
      }
    });
  }

  const blockBtn = document.getElementById("blockBtn");
  if (blockBtn) {
    blockBtn.addEventListener("click", () => {
      if (confirm("Are you sure you want to block this user?")) {
        blockUser();
      }
    });
  }

  // Page visibility change
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) {
      // Page is hidden, stop typing indicators
      stopTypingIndicator();
    }
  });

  // Window beforeunload
  window.addEventListener("beforeunload", function () {
    if (currentSessionId) {
      endChat("page_closed");
    }
  });
}

function setupUI() {
  // Create additional UI elements if needed
  createNotificationContainer();

  // Initialize tooltips and other UI enhancements
  initializeTooltips();
}

function initializeUserProfile() {
  // Initialize user profile information
  const userGender = document.getElementById('userGender');
  const userLocation = document.getElementById('userLocation');
  
  if (userGender) {
    // This would typically come from your backend
    userGender.textContent = 'Loading...';
  }
  
  if (userLocation) {
    getUserLocation().then(location => {
      userLocation.textContent = location;
    }).catch(() => {
      userLocation.textContent = 'Global';
    });
  }
}

function initializeTooltips() {
  // Add tooltip functionality to elements
  const elements = document.querySelectorAll("[data-tooltip]");
  elements.forEach((element) => {
    element.addEventListener("mouseenter", showTooltip);
    element.addEventListener("mouseleave", hideTooltip);
  });
}

function showTooltip(e) {
  const tooltip = document.createElement("div");
  tooltip.className = "tooltip";
  tooltip.textContent = this.dataset.tooltip;
  document.body.appendChild(tooltip);

  const rect = this.getBoundingClientRect();
  tooltip.style.left = rect.left + "px";
  tooltip.style.top = rect.top - tooltip.offsetHeight - 5 + "px";

  this._tooltip = tooltip;
}

function hideTooltip() {
  if (this._tooltip) {
    this._tooltip.remove();
    this._tooltip = null;
  }
}

// Default data
function getDefaultInterests() {
  return ["general", "chatting", "friendship", "random", "global"];
}

function getChatFilters() {
  return {
    language: USER_SETTINGS.preferredLanguage,
    age_range: [18, 99],
    same_interests: true,
    gender_preference: USER_SETTINGS.genderPreference
  };
}

// Message read tracking
function markMessageAsRead(messageId, sessionId) {
  if (unreadMessages.has(messageId)) {
    socket.emit("message_read", {
      message_id: messageId,
      session_id: sessionId,
    });
    unreadMessages.delete(messageId);
  }
}

// Export functions for global access
window.startChat = startChat;
window.startGlobalChat = startGlobalChat;
window.nextChat = nextChat;
window.endChat = endChat;
window.sendMessage = sendMessage;
window.cancelChatSearch = cancelChatSearch;
window.reportUser = reportUser;
window.blockUser = blockUser;
window.requestVoiceChat = requestVoiceChat;

// Initialize when DOM is loaded
document.addEventListener("DOMContentLoaded", function () {
  initializeChat();
  console.log("🌍 Global chat application loaded successfully");
});

// Export for testing
if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    initializeChat,
    startGlobalChat,
    sendMessage,
    endChat,
    getUserLocation
  };
}
