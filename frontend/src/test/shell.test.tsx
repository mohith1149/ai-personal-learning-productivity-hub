import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { NAV_GROUPS } from "../nav";
import { ThemeProvider } from "../theme";
import { emptyDashboard } from "./fakeDashboard";
import { setSystemDark } from "./systemTheme";

const USER = { id: 1, email: "me@example.com", display_name: "Ada Lovelace", timezone: "Asia/Kolkata" };

type Auth = { setup_required: boolean; authenticated: boolean; user: typeof USER | null };
let auth: Auth;
let calls: { url: string; method: string }[];

/** Fake backend: only /api/auth/* and an empty /api/dashboard are needed here. Anything else is a test failure. */
function installFakeBackend() {
  calls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ url, method });
      if (url === "/api/auth/status") return Response.json(auth);
      if (url === "/api/dashboard") return Response.json(emptyDashboard()); // a brand-new account
      if (url === "/api/auth/logout" && method === "POST") {
        auth = { setup_required: false, authenticated: false, user: null };
        return new Response(null, { status: 204 });
      }
      throw new Error(`Unexpected request in test: ${method} ${url}`);
    }),
  );
}

function renderAt(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <ThemeProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={[path]}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>
    </ThemeProvider>,
  );
}

beforeEach(() => {
  auth = { setup_required: false, authenticated: true, user: USER };
  installFakeBackend();
});

describe("auth gating", () => {
  it("shows the setup screen, not the shell, before an account exists", async () => {
    auth = { setup_required: true, authenticated: false, user: null };
    renderAt("/tasks");
    expect(await screen.findByText(/let's set up your hub/i)).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Main" })).not.toBeInTheDocument();
  });

  it("shows login, not the shell, when signed out — whatever URL is requested", async () => {
    auth = { setup_required: false, authenticated: false, user: null };
    renderAt("/projects");
    expect(await screen.findByText("Welcome back")).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Main" })).not.toBeInTheDocument();
  });

  it("sends a signed-in user away from /login to the dashboard", async () => {
    renderAt("/login");
    expect(await screen.findByText(/Ada Lovelace/)).toBeInTheDocument();
    expect(screen.queryByText("Welcome back")).not.toBeInTheDocument();
  });
});

describe("navigation", () => {
  it("lists every planned section and flags unbuilt ones as Soon", async () => {
    renderAt("/");
    const nav = await screen.findByRole("navigation", { name: "Main" });
    for (const item of NAV_GROUPS.flatMap((g) => g.items)) {
      const link = within(nav).getByRole("link", { name: new RegExp(item.label) });
      expect(link).toHaveAttribute("href", item.to);
      if (item.status === "soon") expect(within(link).getByText("Soon")).toBeInTheDocument();
      else expect(within(link).queryByText("Soon")).not.toBeInTheDocument();
    }
  });

  it("marks the current page link as active", async () => {
    renderAt("/");
    const nav = await screen.findByRole("navigation", { name: "Main" });
    expect(within(nav).getByRole("link", { name: /Dashboard/ })).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("link", { name: /Tasks/ })).not.toHaveAttribute("aria-current");
  });

  it("renders an honest placeholder for an unbuilt feature (no fake data)", async () => {
    renderAt("/assistant");
    expect(await screen.findByRole("heading", { name: "AI assistant" })).toBeInTheDocument();
    expect(screen.getByText("Not built yet")).toBeInTheDocument();
    expect(screen.getByText(/Planned: Milestone 12/)).toBeInTheDocument();
  });

  it("shows a 404 page for unknown addresses", async () => {
    renderAt("/does-not-exist");
    expect(await screen.findByText("Page not found")).toBeInTheDocument();
  });

  it("navigates between pages when a sidebar link is clicked", async () => {
    renderAt("/");
    const nav = await screen.findByRole("navigation", { name: "Main" });
    await userEvent.click(within(nav).getByRole("link", { name: /Habits/ }));
    expect(await screen.findByRole("heading", { name: "Habits" })).toBeInTheDocument();
  });
});

describe("dashboard", () => {
  it("greets the user by name and, for a new account, invents no numbers", async () => {
    renderAt("/");
    expect(await screen.findByRole("heading", { name: /Good (morning|afternoon|evening), Ada Lovelace/ })).toBeInTheDocument();
    expect(await screen.findByText("Nothing to show yet")).toBeInTheDocument();
    // The main area must contain no digits at all until real metrics exist.
    expect(document.getElementById("main")!.textContent).not.toMatch(/\d/);
  });
});

describe("settings", () => {
  it("shows the real account details from the server", async () => {
    renderAt("/settings");
    expect(await screen.findByRole("heading", { name: "Settings" })).toBeInTheDocument();
    expect(screen.getByText("me@example.com")).toBeInTheDocument();
    expect(screen.getByText("Asia/Kolkata")).toBeInTheDocument();
  });
});

describe("theme", () => {
  it("switches to dark, persists the choice, and switches back", async () => {
    renderAt("/");
    await screen.findByRole("navigation", { name: "Main" });
    const group = screen.getByRole("radiogroup", { name: "Colour theme" });

    await userEvent.click(within(group).getByRole("radio", { name: "Dark" }));
    expect(document.documentElement).toHaveClass("dark");
    expect(localStorage.getItem("hub-theme")).toBe("dark");
    expect(within(group).getByRole("radio", { name: "Dark" })).toHaveAttribute("aria-checked", "true");

    await userEvent.click(within(group).getByRole("radio", { name: "Light" }));
    expect(document.documentElement).not.toHaveClass("dark");
    expect(localStorage.getItem("hub-theme")).toBe("light");
  });

  it("restores a saved theme on load", async () => {
    localStorage.setItem("hub-theme", "dark");
    renderAt("/");
    await screen.findByRole("navigation", { name: "Main" });
    expect(document.documentElement).toHaveClass("dark");
  });

  it("follows the OS setting live while on 'system'", async () => {
    renderAt("/");
    await screen.findByRole("navigation", { name: "Main" });
    expect(document.documentElement).not.toHaveClass("dark");
    setSystemDark(true);
    await waitFor(() => expect(document.documentElement).toHaveClass("dark"));
  });

  it("ignores a corrupted saved value", async () => {
    localStorage.setItem("hub-theme", "purple");
    renderAt("/");
    await screen.findByRole("navigation", { name: "Main" });
    expect(document.documentElement).not.toHaveClass("dark");
  });
});

describe("mobile drawer", () => {
  it("opens, closes on Escape, and closes after choosing a page", async () => {
    renderAt("/");
    await screen.findByRole("navigation", { name: "Main" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    const opener = screen.getByRole("button", { name: "Open navigation" });
    await userEvent.click(opener);
    expect(screen.getByRole("dialog", { name: "Navigation" })).toBeInTheDocument();
    expect(opener).toHaveAttribute("aria-expanded", "true");

    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await userEvent.click(opener);
    const dialog = screen.getByRole("dialog", { name: "Navigation" });
    await userEvent.click(within(dialog).getByRole("link", { name: /Courses/ }));
    expect(await screen.findByRole("heading", { name: "Courses" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("closes when the backdrop or close button is used, and restores page scrolling", async () => {
    renderAt("/");
    await screen.findByRole("navigation", { name: "Main" });
    await userEvent.click(screen.getByRole("button", { name: "Open navigation" }));
    expect(document.body.style.overflow).toBe("hidden");
    await userEvent.click(screen.getByRole("button", { name: "Close navigation" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(document.body.style.overflow).not.toBe("hidden");
  });
});

describe("sign out", () => {
  it("calls the logout endpoint and returns to the login screen", async () => {
    renderAt("/");
    await screen.findByRole("navigation", { name: "Main" });
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(await screen.findByText("Welcome back")).toBeInTheDocument();
    expect(calls).toContainEqual({ url: "/api/auth/logout", method: "POST" });
    expect(screen.queryByRole("navigation", { name: "Main" })).not.toBeInTheDocument();
  });
});
