const statusEl = document.getElementById("status");
const outputEl = document.getElementById("output");
const token = location.hash.slice(1);

function log(label, data) {
    console.log(label, data);
    outputEl.textContent += `${label}: ${JSON.stringify(data, null, 2)}\n\n`;
}

if (!token) {
    statusEl.textContent = "Missing session token in URL fragment";
} else {
    const ws = new WebSocket(`ws://${location.host}/api/ws`, "jsonrpc2.0");

    ws.addEventListener("open", () => {
        statusEl.textContent = "Authenticating...";
        ws.send(JSON.stringify({
            jsonrpc: "2.0",
            id: 1,
            method: "hello",
            params: { token },
        }));
    });

    ws.addEventListener("message", (event) => {
        const msg = JSON.parse(event.data);
        log("recv", msg);

        if (msg.id === 1 && msg.result) {
            statusEl.textContent = `Connected (API v${msg.result.apiVersion}, server ${msg.result.serverVersion})`;
            ws.send(JSON.stringify({
                jsonrpc: "2.0",
                id: 2,
                method: "get_system",
                params: {},
            }));
            ws.send(JSON.stringify({
                jsonrpc: "2.0",
                id: 3,
                method: "list_editions",
                params: {},
            }));
            ws.send(JSON.stringify({
                jsonrpc: "2.0",
                id: 4,
                method: "get_disk",
                params: {},
            }));
        }
    });

    ws.addEventListener("close", (event) => {
        statusEl.textContent = `Closed (code ${event.code}${event.reason ? `: ${event.reason}` : ""})`;
    });

    ws.addEventListener("error", () => {
        statusEl.textContent = "WebSocket error";
    });
}