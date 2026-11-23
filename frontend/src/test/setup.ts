import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";
import { installMatchMedia, setSystemDark } from "./systemTheme";

// jsdom has no matchMedia; the theme code needs it.
installMatchMedia();

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
  document.documentElement.classList.remove("dark");
  setSystemDark(false);
});
