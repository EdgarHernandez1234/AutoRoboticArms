(() => {
  const wsProto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${wsProto}//${window.location.host}/ws/telemetry`;

  const elIndicator = document.getElementById("ws-indicator");
  const pillWs = document.getElementById("pill-ws");
  const pillHealth = document.getElementById("pill-health");
  const pillAck = document.getElementById("pill-ack");

  const apiKeyInput = document.getElementById("api-key-input");
  const cmdFeedback = document.getElementById("cmd-feedback");
  const logConsole = document.getElementById("log-console");

  // Restore session API key if entered earlier in this tab
  const savedKey = sessionStorage.getItem("ara_api_key");
  if (savedKey) apiKeyInput.value = savedKey;
  apiKeyInput.addEventListener("input", () => {
    sessionStorage.setItem("ara_api_key", apiKeyInput.value.trim());
  });

  function appendLog(text, level = "") {
    const line = document.createElement("div");
    line.className = `log-line ${level}`;
    line.textContent = `[${new Date().toLocaleTimeString()}] ${text}`;
    logConsole.prepend(line);
    while (logConsole.children.length > 80) {
      logConsole.removeChild(logConsole.lastChild);
    }
  }

  function updateTelemetryUI(data) {
    if (!data || !data.joints) return;
    const { base, shoulder, elbow } = data.joints;

    document.getElementById("val-j1").textContent = `${base}°`;
    document.getElementById("val-j2").textContent = `${shoulder}°`;
    document.getElementById("val-j3").textContent = `${elbow}°`;

    document.getElementById("bar-j1").style.width = `${(base / 180) * 100}%`;
    document.getElementById("bar-j2").style.width = `${(shoulder / 180) * 100}%`;
    document.getElementById("bar-j3").style.width = `${(elbow / 180) * 100}%`;

    if (data.cartesian) {
      document.getElementById("val-x").textContent = `${Number(data.cartesian.x).toFixed(2)} cm`;
      document.getElementById("val-y").textContent = `${Number(data.cartesian.y).toFixed(2)} cm`;
      document.getElementById("val-z").textContent = `${Number(data.cartesian.z).toFixed(2)} cm`;
    }

    document.getElementById("val-backlog").textContent = `${data.queue_backlog ?? 0} / 200`;
    document.getElementById("val-cmd").textContent = data.command_type || "--";

    const isNominal = data.status === "NOMINAL" && !data.safe_hold_tripped;
    pillHealth.textContent = `SYSTEM: ${data.status || "UNKNOWN"}`;
    pillHealth.className = `pill ${isNominal ? "ok" : "err"}`;

    pillAck.textContent = `ACK: ${data.hardware_ack || "--"}`;
    pillAck.className = `pill ${data.hardware_ack === "K" ? "ok" : "err"}`;

    if (data.command_type !== "HEARTBEAT") {
      appendLog(
        `${data.command_type} -> J=[${base}°, ${shoulder}°, ${elbow}°] | XYZ=(${data.cartesian?.x}, ${data.cartesian?.y}, ${data.cartesian?.z}) | ACK=${data.hardware_ack}`,
        data.hardware_ack === "K" ? "ok" : "err"
      );
    }
  }

  function connectWebSocket() {
    const socket = new WebSocket(wsUrl);

    socket.onopen = () => {
      elIndicator.className = "pulse-dot online";
      pillWs.textContent = "WS: CONNECTED";
      pillWs.className = "pill ok";
      appendLog("WebSocket telemetry stream connected.", "ok");
    };

    socket.onmessage = (event) => {
      try {
        const frame = JSON.parse(event.data);
        updateTelemetryUI(frame);
      } catch (err) {
        appendLog(`Malformed telemetry frame: ${err.message}`, "err");
      }
    };

    socket.onclose = () => {
      elIndicator.className = "pulse-dot offline";
      pillWs.textContent = "WS: RECONNECTING";
      pillWs.className = "pill err";
      setTimeout(connectWebSocket, 2000);
    };

    socket.onerror = () => {
      socket.close();
    };
  }

  async function sendAuthenticatedPost(endpoint, payload = null) {
    const apiKey = apiKeyInput.value.trim();
    if (!apiKey) {
      cmdFeedback.textContent = "Error: Enter X-API-Key token first.";
      cmdFeedback.style.color = "#ff7b72";
      return;
    }

    try {
      const options = {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": apiKey,
        },
      };
      if (payload) options.body = JSON.stringify(payload);

      const resp = await fetch(endpoint, options);
      const body = await resp.json();

      if (!resp.ok) {
        const detail = body.detail || `HTTP ${resp.status}`;
        cmdFeedback.textContent = `Rejected (${resp.status}): ${detail}`;
        cmdFeedback.style.color = "#ff7b72";
        appendLog(`POST ${endpoint} rejected: ${detail}`, "err");
        return;
      }

      cmdFeedback.textContent = `Accepted: ${JSON.stringify(body)}`;
      cmdFeedback.style.color = "#7ee787";
      appendLog(`POST ${endpoint} -> ${JSON.stringify(body)}`, "ok");
    } catch (err) {
      cmdFeedback.textContent = `Network error: ${err.message}`;
      cmdFeedback.style.color = "#ff7b72";
    }
  }

  document.getElementById("cartesian-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const x = parseFloat(document.getElementById("in-x").value);
    const y = parseFloat(document.getElementById("in-y").value);
    const z = parseFloat(document.getElementById("in-z").value);
    sendAuthenticatedPost("/api/v1/trajectory", {
      waypoints: [{ x, y, z }],
      step_size_cm: 0.5,
    });
  });

  document.getElementById("btn-home").addEventListener("click", () => {
    sendAuthenticatedPost("/api/v1/trajectory", {
      waypoints: [{ x: 10.0, y: 0.0, z: 12.0 }],
      step_size_cm: 0.5,
    });
  });

  document.getElementById("btn-estop").addEventListener("click", () => {
    sendAuthenticatedPost("/api/v1/estop");
  });

  document.getElementById("btn-clear-log").addEventListener("click", () => {
    logConsole.innerHTML = "";
  });

  connectWebSocket();
})();