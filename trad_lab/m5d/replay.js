"use strict";
addEventListener("DOMContentLoaded", async () => {
  const capability = await (await fetch("/m5c/capabilities")).json();
  if (capability.phase !== "M5-D replay") return;
  const ui = globalThis.OperatorUI;
  await ui.ready;
  const panel = document.createElement("div");
  panel.textContent = "PRUEBA LAN · captions sintéticos · SIN micrófono / ASR / DeepL. ";
  const status = document.createElement("span");
  for (const [action, label] of [["start", "1. Iniciar prueba LAN"], ["next", "2. Siguiente caption"], ["stop", "3. Terminar prueba LAN"]]) {
    const button = document.createElement("button");
    button.textContent = label;
    button.onclick = async () => {
      try {
        const response = await fetch(`/api/m5d/replay/${action}`, {method:"POST", headers:{"x-operator-token":ui.token}});
        if (!response.ok) throw Error(`Prueba rechazada (${response.status}); revisar propietario y sesión.`);
        const result = await response.json();
        status.textContent = `${result.state} · caption ${result.sequence}`;
        await ui.refresh();
      } catch (error) { status.textContent = error.message; }
    };
    panel.append(button);
  }
  panel.append(status); document.body.prepend(panel);
  // These are separate from the original session controls; native capture is also
  // rejected on the server. CLEAR / OCULTAR / REANUDAR stay original.
  document.getElementById("start").onclick = () => { status.textContent = "Utiliza Iniciar prueba LAN; la captura está bloqueada."; };
  document.getElementById("stop").onclick = () => { status.textContent = "Utiliza Terminar prueba LAN."; };
});
