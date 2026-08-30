import "@testing-library/jest-dom/vitest";

// jsdom no implementa la Pointer Events API completa (hasPointerCapture /
// setPointerCapture / releasePointerCapture, ni scrollIntoView) — Radix UI
// (Select, entre otros) los usa internamente. Sin este polyfill, cualquier
// test que interactúe con un <Select> revienta con
// "target.hasPointerCapture is not a function". Limitación conocida y
// documentada de jsdom, no un bug de la app ni de Radix.
if (typeof window !== "undefined") {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.setPointerCapture ??= () => {};
  Element.prototype.releasePointerCapture ??= () => {};
  Element.prototype.scrollIntoView ??= () => {};
}
