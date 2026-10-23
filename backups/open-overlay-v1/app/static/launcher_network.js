"use strict";
(() => {
  const ui = globalThis.OperatorUI;
  if (!ui) return;
  const render = ui.render.bind(ui);
  ui.render = function () {
    render();
    const network = ui.snapshot?.network;
    if (!network) return;
    document.getElementById("this-pc-ip").textContent = network.local_ip || network.local_ips.join(" · ") || "Sin IPv4 de red";
    document.getElementById("overlay-pc-ip").textContent = network.overlay_pc_ip || "Sin configurar";
    const link = document.getElementById("lan-overlay-url");
    link.hidden = !network.lan_enabled;
    if (network.lan_enabled) {
      link.href = network.overlay_url;
      link.textContent = network.overlay_url;
    } else {
      link.removeAttribute("href");
      link.textContent = "";
    }
    document.getElementById("network-info").textContent = network.lan_enabled ?
      "Overlay publicado solo para la IP indicada. Abre esta URL en la PC de overlay." :
      "Uso local. Configura la PC de overlay al ejecutar Start-TRAD.ps1; requiere una red privada.";
  };
  ui.ready.then(() => ui.render());
})();
