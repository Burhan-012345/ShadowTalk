// Text Chat JavaScript
let socket;
let currentSessionId = null;
let chatDurationInterval = null;
let chatStartTime = null;

function initializeChat() {
  socket = io();

  socket.on("connect", function () {
    updateConnectionStatus("connected");
  });

  socket.on("disconnect", function () {
    updateConnectionStatus("disconnected");
  });

  socket.on("searching", function (data) {
    updateConnectionStatus("searching");
    document.getElementById(
      "chatStatus"
    ).textContent = `Searching... (${data.count} users online)`;
  });

  socket.on("match_found", function (data) {
    currentSessionId = data.session_id;
    updateConnectionStatus("connected");
    enableChat();
    startChatTimer();
    addSystemMessage("Connected with a stranger!");
  });

  socket.on("receive_message", function (data) {
    addMessage(data.message, "other", data.timestamp);
    playNotificationSound();
  });

  socket.on("partner_left", function () {
    addSystemMessage("Stranger has left the chat");
    endChat();
  });

  socket.on("typing", function () {
    showTypingIndicator();
  });

  socket.on("stop_typing", function () {
    hideTypingIndicator();
  });
}

function startChat() {
  if (!socket) return;

  socket.emit("join_chat", {
    type: "text",
    interests: getSelectedInterests(),
  });

  document.getElementById("startChatBtn").disabled = true;
  document.getElementById("nextChatBtn").disabled = true;
  document.getElementById("endChatBtn").disabled = false;
}

function nextChat() {
  endChat();
  setTimeout(startChat, 1000);
}

function endChat() {
  if (currentSessionId) {
    socket.emit("leave_chat", { session_id: currentSessionId });
    currentSessionId = null;
  }

  resetChat();
  stopChatTimer();
  updateConnectionStatus("disconnected");
}

function sendMessage() {
  const messageInput = document.getElementById("messageInput");
  const message = messageInput.value.trim();

  if (message && currentSessionId) {
    socket.emit("send_message", {
      session_id: currentSessionId,
      message: message,
    });

    addMessage(message, "own", new Date().toISOString());
    messageInput.value = "";

    // Stop typing indicator
    socket.emit("stop_typing");
  }
}

function addMessage(content, type, timestamp) {
  const messagesContainer = document.getElementById("chatMessages");
  const messageElement = document.createElement("div");
  messageElement.className = `message ${type}`;

  messageElement.innerHTML = `
        <div class="message-content">${escapeHtml(content)}</div>
        <div class="message-time">${formatTime(timestamp)}</div>
    `;

  messagesContainer.appendChild(messageElement);
  messagesContainer.scrollTop = messagesContainer.scrollHeight;

  // Remove welcome message if it exists
  const welcomeMessage = messagesContainer.querySelector(".welcome-message");
  if (welcomeMessage) {
    welcomeMessage.remove();
  }
}

function addSystemMessage(content) {
  const messagesContainer = document.getElementById("chatMessages");
  const messageElement = document.createElement("div");
  messageElement.className = "message system";
  messageElement.style.cssText = `
        text-align: center;
        color: var(--text-secondary);
        font-style: italic;
        margin: 1rem 0;
    `;
  messageElement.textContent = content;

  messagesContainer.appendChild(messageElement);
  messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function enableChat() {
  document.getElementById("messageInput").disabled = false;
  document.getElementById("sendBtn").disabled = false;
  document.getElementById("nextChatBtn").disabled = false;
  document.getElementById("endChatBtn").disabled = false;
}

function resetChat() {
  document.getElementById("messageInput").disabled = true;
  document.getElementById("sendBtn").disabled = true;
  document.getElementById("startChatBtn").disabled = false;
  document.getElementById("nextChatBtn").disabled = true;
  document.getElementById("endChatBtn").disabled = true;

  const messagesContainer = document.getElementById("chatMessages");
  messagesContainer.innerHTML = `
        <div class="welcome-message">
            <i class="fas fa-comments"></i>
            <h3>Welcome to Text Chat</h3>
            <p>Click "Start Chat" to connect with a random stranger</p>
        </div>
    `;
}

function updateConnectionStatus(status) {
  const statusElement = document.getElementById("chatStatus");
  const connectionStatus = document.getElementById("connectionStatus");

  statusElement.textContent = status.charAt(0).toUpperCase() + status.slice(1);
  statusElement.className = `chat-status ${status}`;
  connectionStatus.textContent =
    status.charAt(0).toUpperCase() + status.slice(1);
}

function showTypingIndicator() {
  document.getElementById("typingIndicator").style.display = "block";
}

function hideTypingIndicator() {
  document.getElementById("typingIndicator").style.display = "none";
}

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

function getSelectedInterests() {
  // This would typically get interests from user profile or selection
  return [];
}

function playNotificationSound() {
  // Simple notification sound
  const audio = new Audio(
    "data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA"
  );
  audio.volume = 0.3;
  audio.play().catch(() => {});
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

// Event listeners
document.addEventListener("DOMContentLoaded", function () {
  initializeChat();

  const messageInput = document.getElementById("messageInput");
  const sendBtn = document.getElementById("sendBtn");

  // Send message on Enter key
  messageInput.addEventListener("keypress", function (e) {
    if (e.key === "Enter") {
      sendMessage();
    }
  });

  // Typing indicators
  let typing = false;
  let typingTimeout;

  messageInput.addEventListener("input", function () {
    if (!typing && currentSessionId) {
      typing = true;
      socket.emit("typing");
    }

    clearTimeout(typingTimeout);
    typingTimeout = setTimeout(function () {
      typing = false;
      if (currentSessionId) {
        socket.emit("stop_typing");
      }
    }, 1000);
  });
});
