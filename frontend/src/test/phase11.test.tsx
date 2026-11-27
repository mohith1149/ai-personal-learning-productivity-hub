import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { installFakeApi, type Fake } from "./fakeApi";
import { renderAt } from "./render";

async function open(setup?: (fake: Fake) => void) {
  const fake = installFakeApi();
  setup?.(fake);
  renderAt("/settings");
  const card = await screen.findByRole("region", { name: "Share your progress" });
  return { fake, card };
}

const on = (token: string) => (f: Fake) => (f.planning.share = { enabled: true, token, path: `/share/${token}` });

describe("share your progress", () => {
  it("is off by default and says what the page shows and never shows", async () => {
    const { card } = await open();
    expect(await within(card).findByRole("button", { name: "Create a share link" })).toBeInTheDocument();
    expect(within(card).queryByLabelText("Share link")).not.toBeInTheDocument();
    expect(card).toHaveTextContent("verified against GitHub");
    expect(card).toHaveTextContent("Never shown:");
    expect(card).toHaveTextContent("private repositories");
  });

  it("creates a link and shows it with this address in front", async () => {
    const { fake, card } = await open();
    await userEvent.click(await within(card).findByRole("button", { name: "Create a share link" }));
    const box = await within(card).findByLabelText("Share link");
    expect(fake.planning.share.enabled).toBe(true);
    expect(box).toHaveValue(`${window.location.origin}${fake.planning.share.path}`);
    expect(within(card).getByRole("link", { name: /Preview/ })).toHaveAttribute("href", box.getAttribute("value"));
    expect(card).toHaveTextContent("weekly report e-mail includes this link");
  });

  it("makes a new link only after confirming, and the old one is gone", async () => {
    const { fake, card } = await open(on("old".padEnd(43, "x")));
    await userEvent.click(await within(card).findByRole("button", { name: "Make a new link" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("current link stops working");
    expect(fake.callsTo("POST", /\/api\/share$/)).toHaveLength(0); // nothing yet
    await userEvent.click(within(dialog).getByRole("button", { name: "Make a new link" }));
    await waitFor(() => expect(fake.callsTo("POST", /\/api\/share$/)).toHaveLength(1));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(fake.planning.share.token).not.toBe("old".padEnd(43, "x"));
    expect(within(card).getByLabelText("Share link")).toHaveValue(`${window.location.origin}${fake.planning.share.path}`);
  });

  it("cancelling the confirmation keeps the link", async () => {
    const { fake, card } = await open(on("keep".padEnd(43, "x")));
    await userEvent.click(await within(card).findByRole("button", { name: "Stop sharing" }));
    await userEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Cancel" }));
    expect(fake.planning.share.enabled).toBe(true);
    expect(fake.callsTo("DELETE", /\/api\/share$/)).toHaveLength(0);
  });

  it("stops sharing", async () => {
    const { fake, card } = await open(on("gone".padEnd(43, "x")));
    await userEvent.click(await within(card).findByRole("button", { name: "Stop sharing" }));
    await userEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Stop sharing" }));
    await waitFor(() => expect(fake.planning.share.enabled).toBe(false));
    expect(await within(card).findByRole("button", { name: "Create a share link" })).toBeInTheDocument();
    expect(within(card).queryByLabelText("Share link")).not.toBeInTheDocument();
  });

  it("shows an error if the link could not be created", async () => {
    const { fake, card } = await open();
    await within(card).findByRole("button", { name: "Create a share link" });
    fake.failNext(/POST \/api\/share/, 500, "Could not create the link");
    await userEvent.click(within(card).getByRole("button", { name: "Create a share link" }));
    expect(await within(card).findByRole("alert")).toHaveTextContent("Could not create the link");
  });
});
