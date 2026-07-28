import "@testing-library/jest-dom/vitest";

// Fix Node.js 25+ native localStorage shadowing jsdom's polyfill.
// Node 25 exposes a native localStorage global, but without --localstorage-file
// it's a stub with no methods (getItem, setItem, etc. are undefined).
if (
  typeof globalThis.localStorage !== "undefined" &&
  typeof globalThis.localStorage.getItem !== "function"
) {
  const store = new Map<string, string>();
  Object.defineProperty(globalThis, "localStorage", {
    value: {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => {
        store.set(key, String(value));
      },
      removeItem: (key: string) => {
        store.delete(key);
      },
      clear: () => {
        store.clear();
      },
      get length() {
        return store.size;
      },
      key: (index: number) => [...store.keys()][index] ?? null,
    } as Storage,
    writable: true,
    configurable: true,
  });
}

// Polyfill ResizeObserver for Radix UI components (Slider, etc.)
if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

// Polyfill Element.scrollIntoView for jsdom
if (typeof Element.prototype.scrollIntoView === "undefined") {
  Element.prototype.scrollIntoView = () => {};
}

// Polyfill pointer capture for Radix Select under jsdom.
if (typeof Element.prototype.hasPointerCapture === "undefined") {
  Element.prototype.hasPointerCapture = () => false;
  Element.prototype.setPointerCapture = () => {};
  Element.prototype.releasePointerCapture = () => {};
}

// Fix Node.js 25+ AbortSignal incompatibility with jsdom + react-router.
// Node 25's native Request constructor rejects jsdom's AbortSignal polyfill.
// Suppress the unhandled rejection to prevent false test failures.
if (typeof process !== "undefined") {
  process.on("unhandledRejection", (reason: unknown) => {
    if (
      reason instanceof TypeError &&
      String(reason.message).includes("AbortSignal")
    ) {
      // Swallow — Node 25 vs jsdom AbortSignal mismatch in react-router
      return;
    }
    // Re-throw all other unhandled rejections
    throw reason;
  });
}
