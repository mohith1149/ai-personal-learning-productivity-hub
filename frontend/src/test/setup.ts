import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { afterEach, vi } from "vitest";
import { installMatchMedia, setSystemDark } from "./systemTheme";

// The default 1s wait for findBy*/waitFor is too tight when many test files render in parallel (it made one test flaky).
// A longer ceiling doesn't slow passing tests: they return as soon as the element appears.
configure({ asyncUtilTimeout: 4000 });

// jsdom has no matchMedia; the theme code needs it.
installMatchMedia();

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
  document.documentElement.classList.remove("dark");
  setSystemDark(false);
});
