(function () {
  function escapeHtml(value) {
    var div = document.createElement("div");
    div.appendChild(document.createTextNode(value == null ? "" : String(value)));
    return div.innerHTML;
  }

  function getCookie(name) {
    var match = document.cookie.match("(^|;)\\s*" + name + "\\s*=\\s*([^;]+)");
    return match ? match.pop() : "";
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

  function updateUnreadBadge(chatId, unread) {
    var changeUrl = "/admin/support/supportchat/" + chatId + "/change/";
    var anchor = document.querySelector('a[href="' + changeUrl + '"]');
    if (!anchor) return;
    var row = anchor.closest("tr");
    var cell = row ? row.querySelector("th, td") : null;
    if (!cell) return;
    var badge = cell.querySelector(".support-unread-badge");
    if (!unread) {
      if (badge) badge.remove();
      return;
    }
    if (!badge) {
      badge = document.createElement("span");
      badge.className = "support-unread-badge";
      badge.style.background = "#dc3545";
      badge.style.color = "#fff";
      badge.style.padding = "2px 6px";
      badge.style.borderRadius = "10px";
      badge.style.marginLeft = "8px";
      badge.style.fontSize = "12px";
      cell.appendChild(badge);
    }
    badge.textContent = unread;
  }

  function showPreview(chatId) {
    var panel = document.getElementById("support-chat-preview-panel");
    var messagesEl = document.getElementById("support-chat-preview-messages");
    var sendBtn = document.getElementById("support-chat-preview-send");
    var textarea = document.getElementById("support-chat-preview-reply");
    if (!panel || !messagesEl) return;

    panel.style.display = "block";
    panel.dataset.currentChat = chatId;
    messagesEl.innerHTML = "<p style=\"color:#999\">Loading messages...</p>";

    var messagesUrl = "/admin/support/supportchat/messages/" + chatId + "/json/";
    fetch(messagesUrl, { credentials: "same-origin" })
      .then(function (response) {
        return response.json();
      })
      .then(function (messages) {
        messagesEl.innerHTML = "";
        if (!Array.isArray(messages) || !messages.length) {
          messagesEl.innerHTML = "<p style=\"color:#999\">No messages</p>";
          return;
        }
        messages.forEach(function (message) {
          messagesEl.appendChild(renderMessage(message));
        });
        messagesEl.scrollTop = messagesEl.scrollHeight;
      })
      .catch(function () {
        messagesEl.innerHTML = "<p style=\"color:#d33\">Failed to load messages</p>";
      });

    if (sendBtn && textarea) {
      sendBtn.onclick = function () {
        var content = textarea.value.trim();
        if (!content) return;

        var body = new URLSearchParams();
        body.append("reply_content", content);
        fetch("/admin/support/supportchat/" + chatId + "/change/", {
          method: "POST",
          body: body.toString(),
          headers: {
            "X-CSRFToken": getCookie("csrftoken"),
            "Content-Type": "application/x-www-form-urlencoded",
          },
          credentials: "same-origin",
        })
          .then(function (response) {
            if (!response.ok) throw new Error("Reply failed");
            textarea.value = "";
            showPreview(chatId);
          })
          .catch(function () {
            window.alert("Failed to send reply");
          });
      };
    }
  }

  function setupPreview() {
    document.querySelectorAll(".support-chat-reply-btn").forEach(function (button) {
      button.addEventListener("click", function (event) {
        event.preventDefault();
        var chatId = button.getAttribute("data-chat-id");
        if (chatId) showPreview(chatId);
      });
    });

    document.addEventListener("click", function (event) {
      if (event.target && event.target.id === "support-chat-preview-close") {
        event.preventDefault();
        var panel = document.getElementById("support-chat-preview-panel");
        if (panel) panel.style.display = "none";
      }
    });

    var protocol = location.protocol === "https:" ? "wss" : "ws";
    try {
      var lobby = new WebSocket(protocol + "://" + location.host + "/ws/support/admin/lobby/");
      lobby.onmessage = function (event) {
        try {
          var data = JSON.parse(event.data);
          if (data.type !== "chat.update") return;
          updateUnreadBadge(data.chat_id, data.unread_by_admin);
          var panel = document.getElementById("support-chat-preview-panel");
          if (panel && panel.style.display !== "none" && panel.dataset.currentChat === String(data.chat_id)) {
            showPreview(data.chat_id);
          }
        } catch (e) {
          console.error("Invalid support lobby event", e);
        }
      };
    } catch (e) {
      console.error("Failed to connect support lobby", e);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setupPreview);
  } else {
    setupPreview();
  }
})();
