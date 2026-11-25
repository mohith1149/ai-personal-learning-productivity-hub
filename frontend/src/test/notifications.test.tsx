import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { installFakeApi } from "./fakeApi";
import { renderAt } from "./render";

describe("e-mail reminder settings", () => {
  it("saves e-mail reminder settings and says honestly when a test e-mail was not sent", async () => {
    const fake = installFakeApi();
    renderAt("/settings");
    const card = await screen.findByRole("region", { name: "E-mail reminders" });
    await userEvent.click(await within(card).findByRole("checkbox", { name: "Send me e-mail reminders" }));
    await userEvent.clear(within(card).getByLabelText("Daily plan at"));
    await userEvent.type(within(card).getByLabelText("Daily plan at"), "06:30");
    await userEvent.click(within(card).getByRole("button", { name: "Save reminders" }));
    expect(await within(card).findByText("Saved.")).toBeInTheDocument();
    expect(fake.notifications.settings).toMatchObject({ email_enabled: true, reminder_time: "06:30" });

    fake.notifications.testStatus = "failed";
    await userEvent.click(within(card).getByRole("button", { name: "Send a test e-mail" }));
    expect(await within(card).findByText(/The test e-mail was not sent/)).toHaveTextContent("username or password");
    expect(within(await within(card).findByRole("list", { name: "Recent e-mails" })).getByText("Failed")).toBeInTheDocument();
  });

  it("warns that nothing can be sent when the server has no e-mail account", async () => {
    const fake = installFakeApi();
    fake.notifications.settings.server_ready = false;
    renderAt("/settings");
    expect(await screen.findByText(/no e-mail account yet/)).toBeInTheDocument();
  });
});
