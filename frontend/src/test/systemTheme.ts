/** Fake `matchMedia` so tests can simulate the OS switching between light and dark. */
let systemDark = false;
const listeners = new Set<() => void>();

export function installMatchMedia() {
  window.matchMedia = (query: string) =>
    ({
      matches: query.includes("dark") ? systemDark : false,
      media: query,
      addEventListener: (_: string, cb: () => void) => listeners.add(cb),
      removeEventListener: (_: string, cb: () => void) => listeners.delete(cb),
    }) as unknown as MediaQueryList;
}

export function setSystemDark(value: boolean) {
  systemDark = value;
  listeners.forEach((cb) => cb());
}
