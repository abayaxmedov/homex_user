(function () {
  function escapeHtml(value) {
    var div = document.createElement("div");
    div.appendChild(document.createTextNode(value == null ? "" : String(value)));
    return div.innerHTML;
  }

  function senderName(message) {
    if (message.sender && message.sender.username) return message.sender.username;
    if (message.sender_role === "admin") return "Admin";
    return message.sender_role || "User";
  }

  function renderMessage(message) {
    var item = document.createElement("div");
    var fromAdmin = message.sender_role === "admin";
    item.style.padding = "8px 10px";
    item.style.margin = "6px 0";
    item.style.borderRadius = "6px";
    item.style.background = fromAdmin ? "#f4f4f5" : "#e9f7ff";
    item.style.border = "1px solid " + (fromAdmin ? "#e4e4e7" : "#d7efff");
    item.style.color = "#111827";
    var when = message.timestamp || message.created_at || "";
    var content = message.content || message.message || "";
    item.innerHTML =
      "<div style=\"font-size:12px;color:#111827\"><strong>" +
      escapeHtml(senderName(message)) +
      "</strong><small style=\"color:#4b5563;margin-left:6px\">" +
      escapeHtml(when) +
      "</small></div><div style=\"margin-top:6px;white-space:pre-wrap;color:#111827;font-size:14px;line-height:1.45\">" +
      escapeHtml(content) +
      "</div>";
    return item;
  }

  function setupAdminChat() {
    var messagesEl = document.getElementById("support-admin-chat-messages");
    var form = document.getElementById("support-admin-reply-form");
    var textarea = document.getElementById("support-admin-reply-content");
    var initialEl = document.getElementById("support-initial-messages");
    if (!messagesEl) return;

    var chatId = messagesEl.dataset.chatId;
    var seen = new Set();

    function appendMessage(message) {
      if (!message || !message.id || seen.has(message.id)) return;
      seen.add(message.id);
      messagesEl.appendChild(renderMessage(message));
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function renderInitial() {
      var initial = [];
      try {
        initial = JSON.parse(initialEl ? initialEl.textContent || "[]" : "[]");
      } catch (e) {
        initial = [];
      }
      messagesEl.innerHTML = "";
      if (!initial.length) {
        messagesEl.innerHTML = "<p style=\"color:#999\">No messages</p>";
        return;
      }
      initial.forEach(appendMessage);
    }

    renderInitial();
    if (!chatId) return;

    var protocol = location.protocol === "https:" ? "wss" : "ws";
    var wsUrl = protocol + "://" + location.host + "/ws/support/" + chatId + "/";
    var ws;
    try {
      ws = new WebSocket(wsUrl);
    } catch (e) {
      ws = null;
    }

    if (ws) {
      ws.onmessage = function (event) {
        try {
          var data = JSON.parse(event.data);
          if (data.type === "history") {
            messagesEl.innerHTML = "";
            seen.clear();
            (data.messages || []).forEach(appendMessage);
          } else if (data.type === "message") {
            appendMessage(data.message || data.data);
          }
        } catch (e) {
          console.error("Invalid support chat event", e);
        }
      };
    }

    if (form && textarea) {
      form.addEventListener("submit", function (event) {
        event.preventDefault();
        var content = textarea.value.trim();
        if (!content) return;
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ content: content }));
          textarea.value = "";
        } else {
          form.submit();
        }
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setupAdminChat);
  } else {
    setupAdminChat();
  }
})();
