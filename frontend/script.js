// ---------------------------------------------------------------------------
// Vignan IIT Assistant — frontend chat logic
// Talks to the FastAPI backend's /api/chat endpoint.
// ---------------------------------------------------------------------------

const API_BASE_URL = "http://localhost:8001";

const chatWindow = document.getElementById("chatWindow");
const chatForm = document.getElementById("chatForm");
const chatInput = document.getElementById("chatInput");
const sendBtn = document.getElementById("sendBtn");
const emptyState = document.getElementById("emptyState");
const newChatBtn = document.getElementById("newChatBtn");
const statusDot = document.getElementById("statusDot");
const statusText = document.getElementById("statusText");

let conversationHistory = []; // [{role, content}, ...]
let isWaitingForResponse = false;

// ---------------------------------------------------------------------------
// Health check
// ---------------------------------------------------------------------------
async function checkHealth() {
  try {
    const res = await fetch(`${API_BASE_URL}/api/health`);
    if (!res.ok) throw new Error("bad status");
    const data = await res.json();
    statusDot.classList.add("online");
    statusDot.classList.remove("offline");
    statusText.textContent = `Online · ${data.collection_document_count} chunks indexed`;
  } catch (err) {
    statusDot.classList.add("offline");
    statusDot.classList.remove("online");
    statusText.textContent = "Backend unreachable";
  }
}
checkHealth();
setInterval(checkHealth, 30000);

// ---------------------------------------------------------------------------
// Auto-resize textarea
// ---------------------------------------------------------------------------
chatInput.addEventListener("input", () => {
  chatInput.style.height = "auto";
  chatInput.style.height = Math.min(chatInput.scrollHeight, 160) + "px";
});

chatInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    chatForm.requestSubmit();
  }
});

// ---------------------------------------------------------------------------
// Suggestion chips
// ---------------------------------------------------------------------------
document.querySelectorAll(".suggestion-chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    chatInput.value = chip.textContent;
    chatForm.requestSubmit();
  });
});

// ---------------------------------------------------------------------------
// New chat
// ---------------------------------------------------------------------------
newChatBtn.addEventListener("click", () => {
  conversationHistory = [];
  chatWindow.innerHTML = "";
  chatWindow.appendChild(emptyState);
  emptyState.style.display = "block";
});

// ---------------------------------------------------------------------------
// Rendering helpers
// ---------------------------------------------------------------------------
function scrollToBottom() {
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function renderUserMessage(text) {
  const row = document.createElement("div");
  row.className = "message-row user";
  row.innerHTML = `
    <div class="avatar user">U</div>
    <div class="message-content">
      <div class="message-role">You</div>
      <div class="message-bubble">${escapeHtml(text)}</div>
    </div>
  `;
  chatWindow.appendChild(row);
  scrollToBottom();
}

function renderTypingIndicator() {
  const row = document.createElement("div");
  row.className = "message-row assistant";
  row.id = "typingRow";
  row.innerHTML = `
    <div class="avatar assistant">V</div>
    <div class="message-content">
      <div class="message-role">Vignan IIT Assistant</div>
      <div class="typing-indicator"><span></span><span></span><span></span></div>
    </div>
  `;
  chatWindow.appendChild(row);
  scrollToBottom();
}

function removeTypingIndicator() {
  const row = document.getElementById("typingRow");
  if (row) row.remove();
}

function renderAssistantMessage(answer, sources) {
  const row = document.createElement("div");
  row.className = "message-row assistant";

  let sourcesHtml = "";
  if (sources && sources.length > 0) {
    const chips = sources
      .map(
        (s, i) => `
        <a class="source-chip" href="${escapeHtml(s.url)}" target="_blank" rel="noopener noreferrer" title="${escapeHtml(s.snippet)}">
          <span class="source-index">${i + 1}</span>
          <span>${escapeHtml(s.title || s.url)}</span>
        </a>`
      )
      .join("");
    sourcesHtml = `
      <div class="sources-block">
        <div class="sources-title">Sources</div>
        ${chips}
      </div>`;
  }

  row.innerHTML = `
    <div class="avatar assistant">V</div>
    <div class="message-content">
      <div class="message-role">Vignan IIT Assistant</div>
      <div class="message-bubble">${escapeHtml(answer)}</div>
      ${sourcesHtml}
    </div>
  `;
  chatWindow.appendChild(row);
  scrollToBottom();
}

function renderErrorMessage(text) {
  const row = document.createElement("div");
  row.className = "message-row assistant";
  row.innerHTML = `
    <div class="avatar assistant">V</div>
    <div class="message-content">
      <div class="message-role">Vignan IIT Assistant</div>
      <div class="message-bubble" style="color:#dc2626;">${escapeHtml(text)}</div>
    </div>
  `;
  chatWindow.appendChild(row);
  scrollToBottom();
}

// ---------------------------------------------------------------------------
// Submit handler
// ---------------------------------------------------------------------------
chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const message = chatInput.value.trim();
  if (!message || isWaitingForResponse) return;

  if (emptyState && emptyState.style.display !== "none") {
    emptyState.style.display = "none";
  }

  renderUserMessage(message);
  conversationHistory.push({ role: "user", content: message });

  chatInput.value = "";
  chatInput.style.height = "auto";
  isWaitingForResponse = true;
  sendBtn.disabled = true;

  renderTypingIndicator();

  try {
    const res = await fetch(`${API_BASE_URL}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        history: conversationHistory.slice(0, -1), // exclude current turn
      }),
    });

    removeTypingIndicator();

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      renderErrorMessage(
        errData.detail || "Something went wrong talking to the server."
      );
    } else {
      const data = await res.json();
      renderAssistantMessage(data.answer, data.sources);
      conversationHistory.push({ role: "assistant", content: data.answer });
    }
  } catch (err) {
    removeTypingIndicator();
    renderErrorMessage(
      "Could not reach the chatbot backend. Make sure the API server is running at " +
        API_BASE_URL
    );
  } finally {
    isWaitingForResponse = false;
    sendBtn.disabled = false;
    chatInput.focus();
  }
});
