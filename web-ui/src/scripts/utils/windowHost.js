const READY_EVENTS = ["gkmas-window-host-ready", "pywebviewready"];

function getNativeWindowHost() {
  return window.__gkmasWindowHost__ ?? null;
}

export function getWindowHostApi() {
  return getNativeWindowHost()?.api ?? window.pywebview?.api ?? null;
}

export function getWindowHostKind() {
  if (getNativeWindowHost()) {
    return getNativeWindowHost().kind ?? "pywebview";
  }

  if (window.pywebview?.api) {
    return "pywebview";
  }

  return null;
}

export function isWindowHostAvailable() {
  return !!getWindowHostApi();
}

export function syncWindowHostShellClass() {
  const hasWindowHost = isWindowHostAvailable();
  const isPywebview = !!window.pywebview?.api;

  document.documentElement.classList.toggle("window-host-shell", hasWindowHost);
  document.body.classList.toggle("window-host-shell", hasWindowHost);
  document.documentElement.classList.toggle("pywebview-shell", isPywebview);
  document.body.classList.toggle("pywebview-shell", isPywebview);
}

export function addWindowHostReadyListener(listener) {
  const wrapped = () => listener(getWindowHostKind());
  READY_EVENTS.forEach(eventName => window.addEventListener(eventName, wrapped));

  return () => {
    READY_EVENTS.forEach(eventName => window.removeEventListener(eventName, wrapped));
  };
}
