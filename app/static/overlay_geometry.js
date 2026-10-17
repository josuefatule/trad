/* Logical canvas coordinates; shared by OBS, preview and geometry tests. */
(function (root) {
  "use strict";
  function geometry(config, viewportWidth, viewportHeight) {
    const innerWidth = config.region_width - 2 * config.padding_x;
    const innerHeight = config.region_height - 2 * config.padding_y;
    const lineHeight = config.font_size * config.line_height;
    const capacity = Math.floor((innerHeight + 1e-7) / lineHeight);
    if (capacity < 1 || innerWidth < 40) throw new Error("Caption region cannot fit text");
    const maxLines = Math.min(config.max_lines, capacity);
    const scale = Math.min(viewportWidth / config.canvas_width, viewportHeight / config.canvas_height);
    return {scale, left: (viewportWidth - config.canvas_width * scale) / 2,
      top: (viewportHeight - config.canvas_height * scale) / 2,
      lineHeight, capacity, maxLines, maxWidth: Math.min(config.max_width, innerWidth),
      warning: maxLines < config.max_lines ?
        `Requested ${config.max_lines} lines; only ${maxLines} fit in ${config.region_height}px at ${config.font_size}px (line-height ${config.line_height}, vertical padding ${config.padding_y}px). Font unchanged.` : ""};
  }
  function apply(config, viewportWidth, viewportHeight, canvas, stage, caption) {
    const g = geometry(config, viewportWidth, viewportHeight);
    Object.assign(canvas.style, {width: `${config.canvas_width}px`, height: `${config.canvas_height}px`,
      left: `${g.left}px`, top: `${g.top}px`, transform: `scale(${g.scale})`});
    Object.assign(stage.style, {left: `${config.region_x}px`, top: `${config.region_y}px`,
      width: `${config.region_width}px`, height: `${config.region_height}px`,
      padding: `${config.padding_y}px ${config.padding_x}px`,
      alignItems: {bottom: "flex-end", top: "flex-start", center: "center"}[config.position]});
    Object.assign(caption.style, {maxWidth: `${g.maxWidth}px`, lineHeight: `${g.lineHeight}px`,
      backgroundColor: `rgba(0, 0, 0, ${config.background_opacity})`});
    return {geometry: g, config: {...config, max_width: g.maxWidth, max_lines: g.maxLines}};
  }
  const api = {geometry, apply};
  root.OverlayGeometry = api;
  if (typeof module !== "undefined") module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
