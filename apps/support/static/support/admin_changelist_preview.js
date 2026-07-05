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

  function findRow(chatId) {
    var badge = document.querySelector('.support-status-badge[data-chat-id="' + chatId + '"]');
    if (badge) {
      var badgeRow = badge.closest("tr");
      if (badgeRow) return badgeRow;
    }
    var changeUrl = "/admin/support/supportchat/" + chatId + "/change/";
    var anchor = document.querySelector('a[href="' + changeUrl + '"]');
    return anchor ? anchor.closest("tr") : null;
  }

  function paintUnread(badge, unread) {
    badge.setAttribute("data-unread", unread);
    badge.style.display = "inline-flex";
    badge.style.alignItems = "center";
    badge.style.gap = "4px";
    badge.style.background = "#dc3545";
    badge.style.color = "#fff";
    badge.style.fontWeight = "700";
    badge.style.padding = "2px 9px";
    badge.style.borderRadius = "10px";
    badge.style.fontSize = "11px";
    badge.style.whiteSpace = "nowrap";
    badge.textContent = "● Yangi (" + unread + ")";
  }

  function paintRead(badge) {
    badge.setAttribute("data-unread", "0");
    badge.style.display = "";
    badge.style.background = "";
    badge.style.color = "#6c757d";
    badge.style.fontWeight = "";
    badge.style.padding = "";
    badge.style.borderRadius = "";
    badge.style.fontSize = "11px";
    badge.style.whiteSpace = "nowrap";
    badge.textContent = "O‘qilgan";
  }

  function floatRowToTop(row) {
    var tbody = row.parentNode;
    if (!tbody || tbody.firstElementChild === row) return;
    tbody.insertBefore(row, tbody.firstElementChild);
    row.style.transition = "background-color 0.8s ease";
    row.style.backgroundColor = "#fff3cd";
    setTimeout(function () {
      row.style.backgroundColor = "";
    }, 1400);
  }

  function updateUnreadBadge(chatId, unread) {
    var row = findRow(chatId);
    if (!row) return;
    var badge = row.querySelector(".support-status-badge");
    if (badge) {
      if (unread) paintUnread(badge, unread);
      else paintRead(badge);
    }
    if (unread) floatRowToTop(row);
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
