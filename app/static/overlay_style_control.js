"use strict";
(() => {
  const ui = globalThis.OperatorUI;
  if (!ui) return;
  let saving = false;
  for (const [field, pickerId, buttonId, infoId] of [
    ["text_color", "caption-color", "apply-caption-color", "caption-color-info"],
    ["background_color", "overlay-background-color", "apply-overlay-background-color", "overlay-background-color-info"],
  ]) {
  const picker = document.getElementById(pickerId), button = document.getElementById(buttonId), info = document.getElementById(infoId);
  if (!picker || !button || !info) continue;
  let busy = false, dirty = false, message = "";
  const render = ui.render.bind(ui);
  ui.render = function () {
    render();
    const style = ui.snapshot?.overlay_style;
    const allowed = ui.authorized && !!style && (!ui.snapshot?.session_id || ui.snapshot?.owns_session);
    picker.disabled = button.disabled = saving || !allowed || !style?.[field];
    if (style?.[field] && !dirty && !busy) picker.value = style[field];
    info.textContent = message || (style?.[field] ? `Actual: ${style[field]} · todos los overlays` : "Reinicia el servidor para habilitar el color");
  };
  picker.addEventListener("input", () => { dirty = true; message = ""; });
  button.addEventListener("click", async () => {
    if (button.disabled) return;
    const color = picker.value;
    busy = saving = true; message = "Aplicando color…"; ui.render();
    try {
      const response = await fetch("/api/operator/overlay-style", {method: "POST",
        headers: {"Content-Type": "application/json", "X-Operator-Token": ui.token},
        body: JSON.stringify({[field]: color})});
      if (!response.ok) throw Error("No se pudo guardar el color. Comprueba que esta consola controle la sesión.");
      const result = await response.json();
      if (ui.snapshot) ui.snapshot.overlay_style = result.overlay_style;
      dirty = false; message = `Color aplicado: ${result.overlay_style[field]}`;
    } catch (error) { message = error.message; }
    finally { busy = saving = false; ui.render(); }
  });
  ui.ready.then(() => ui.render());
  }
})();
