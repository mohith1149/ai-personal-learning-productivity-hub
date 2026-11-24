import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { installFakeApi, type Fake } from "./fakeApi";
import { installFakeVideos, mkPlaylist, mkVideo, type FakeVideos } from "./fakeVideos";
import { renderAt } from "./render";

type Setup = { fake: Fake; store: FakeVideos };

/** A ByteByteGo channel collection (2 per day, oldest first) with three not-started videos published Jan 2024. */
function bbg(): Partial<FakeVideos> {
  const pub = (d: number) => new Date(Date.UTC(2024, 0, d)).toISOString();
  return {
    playlists: [mkPlaylist({ id: 1, name: "ByteByteGo", kind: "channel", daily_target: 2, source_url: "https://www.youtube.com/@ByteByteGo", reported_total: 172, retrieved_count: 3 })],
    videos: [
      mkVideo({ id: 11, playlist_ids: [1], title: "How DNS works", url: "https://youtu.be/aaaaaaaaaaa", youtube_video_id: "aaaaaaaaaaa", category: "Networking", published_at: pub(1), duration_seconds: 253, thumbnail_url: "https://i.ytimg.com/vi/a/mq.jpg", channel_title: "ByteByteGo" }),
      mkVideo({ id: 12, playlist_ids: [1], title: "Load balancers", published_at: pub(2), duration_seconds: 3723 }),
      mkVideo({ id: 13, playlist_ids: [1], title: "Rate limiting", published_at: pub(3) }),
    ],
  };
}

async function open(path: string, seed: Partial<FakeVideos> = bbg()): Promise<Setup> {
  const fake = installFakeApi();
  const store = installFakeVideos(fake, seed);
  renderAt(path);
  return { fake, store };
}

const grid = () => screen.findByRole("list", { name: "Video library" });
const cardTitles = (list: HTMLElement) => within(list).getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
const collection = (name: string) => screen.findByRole("tab", { name });

// ================================ library overview + recommendation ================================

describe("overview and recommendation", () => {
  it("shows overall progress and the next video to watch (oldest published first)", async () => {
    await open("/videos?playlist=1");
    const overall = await screen.findByRole("region", { name: "Overall progress" });
    expect(within(overall).getByRole("progressbar", { name: "Overall progress" })).toHaveAttribute("aria-valuenow", "0");
    expect(within(overall).getByText("In library").nextSibling).toHaveTextContent("3");
    const next = screen.getByRole("region", { name: "Recommended next video" });
    expect(await within(next).findByText("How DNS works")).toBeInTheDocument();
    expect(within(next).getByRole("link", { name: "Watch How DNS works next" })).toHaveAttribute("href", "https://youtu.be/aaaaaaaaaaa");
  });

  it("marking the recommended video completed updates progress and recommends the next one, never the same again", async () => {
    const { fake } = await open("/videos");
    const next = await screen.findByRole("region", { name: "Recommended next video" });
    await userEvent.click(await within(next).findByRole("button", { name: "Mark How DNS works as completed (next)" }));

    expect(await within(next).findByText("Load balancers")).toBeInTheDocument();
    expect(within(next).queryByText("How DNS works")).not.toBeInTheDocument();
    expect(fake.callsTo("POST", /\/api\/videos\/11\/complete$/)).toHaveLength(1);
    const overall = screen.getByRole("region", { name: "Overall progress" });
    await waitFor(() => expect(within(overall).getByRole("progressbar", { name: "Overall progress" })).toHaveAttribute("aria-valuenow", "33"));
    expect(within(overall).getByText("Completed").nextSibling).toHaveTextContent("1");
  });

  it("can switch the recommendation to newest first", async () => {
    const { fake } = await open("/videos");
    const next = await screen.findByRole("region", { name: "Recommended next video" });
    expect(await within(next).findByText("How DNS works")).toBeInTheDocument();
    await userEvent.selectOptions(within(next).getByRole("combobox", { name: "Recommendation order" }), "newest");
    expect(await within(next).findByText("Rate limiting")).toBeInTheDocument();
    expect(fake.callsTo("GET", /\/api\/videos\/stats$/).some((c) => c.query.order === "newest")).toBe(true);
  });

  it("says so when everything is completed", async () => {
    const seed = bbg();
    seed.videos = seed.videos!.map((v) => ({ ...v, status: "completed" as const, completed_at: "2026-11-01T10:00:00Z" }));
    await open("/videos", seed);
    expect(await screen.findByText(/Every video in your library is completed/)).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Overall progress" })).toHaveAttribute("aria-valuenow", "100");
  });

  it("an empty library gets an honest empty state and no invented videos", async () => {
    const { store } = await open("/videos", { playlists: [], videos: [] });
    expect(await screen.findByText("No videos yet")).toBeInTheDocument();
    expect(await screen.findByText(/Import or add videos to get a recommendation/)).toBeInTheDocument();
    expect(store.videos).toHaveLength(0);
  });
});

// ================================ collections ================================

describe("collections", () => {
  it("shows every collection as a tab, starting on the whole library", async () => {
    await open("/videos", { ...bbg(), playlists: [...bbg().playlists!, mkPlaylist({ id: 2, name: "Rust talks" })] });
    expect(await collection("All videos")).toHaveAttribute("aria-selected", "true");
    await userEvent.click(await collection("Rust talks"));
    expect(await screen.findByRole("heading", { name: "Rust talks", level: 2 })).toBeInTheDocument();
    expect(await screen.findByText("No videos yet")).toBeInTheDocument();
  });

  it("a channel collection distinguishes what YouTube has, what was retrieved and what is in the library", async () => {
    await open("/videos?playlist=1");
    const overview = await screen.findByRole("region", { name: "ByteByteGo overview" });
    expect(within(overview).getByText("On YouTube").nextSibling).toHaveTextContent("172");
    expect(within(overview).getByText("Retrieved").nextSibling).toHaveTextContent("3");
    expect(within(overview).getByText("In library").nextSibling).toHaveTextContent("3");
    expect(within(overview).getByText("Channel")).toBeInTheDocument();
    expect(within(overview).getByText("0 of 3 completed")).toBeInTheDocument();
  });

  it("shows 'unavailable' when YouTube didn't report a total, never a made-up number", async () => {
    const seed = bbg();
    seed.playlists![0].reported_total = null;
    await open("/videos?playlist=1", seed);
    const overview = await screen.findByRole("region", { name: "ByteByteGo overview" });
    expect(within(overview).getByText("On YouTube").nextSibling).toHaveTextContent("unavailable");
  });

  it("a hand-made collection doesn't show YouTube counts", async () => {
    await open("/videos?playlist=2", { playlists: [mkPlaylist({ id: 2, name: "Mine" })], videos: [] });
    const overview = await screen.findByRole("region", { name: "Mine overview" });
    expect(within(overview).queryByText("On YouTube")).not.toBeInTheDocument();
  });

  it("creates a playlist after validating the name and daily target", async () => {
    const { fake } = await open("/videos", { playlists: [], videos: [] });
    await userEvent.click(await screen.findByRole("button", { name: "New playlist" }));
    const dialog = await screen.findByRole("dialog", { name: "New playlist" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Create playlist" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Please give the playlist a name.");

    await userEvent.type(within(dialog).getByLabelText("Name"), "Mine");
    await userEvent.clear(within(dialog).getByLabelText("Videos to watch per day"));
    await userEvent.type(within(dialog).getByLabelText("Videos to watch per day"), "0");
    await userEvent.click(within(dialog).getByRole("button", { name: "Create playlist" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("whole number from 1 to 50");
    expect(fake.callsTo("POST", /video-playlists/)).toHaveLength(0);

    await userEvent.clear(within(dialog).getByLabelText("Videos to watch per day"));
    await userEvent.type(within(dialog).getByLabelText("Videos to watch per day"), "3");
    await userEvent.click(within(dialog).getByRole("button", { name: "Create playlist" }));
    expect(await screen.findByRole("heading", { name: "Mine", level: 2 })).toBeInTheDocument();
    expect(fake.callsTo("POST", /video-playlists$/)[0].body).toMatchObject({ name: "Mine", daily_target: 3, active: true, recommend_order: "oldest" });
  });

  it("shows the server's message for a duplicate name", async () => {
    await open("/videos");
    await userEvent.click(await screen.findByRole("button", { name: "New playlist" }));
    const dialog = await screen.findByRole("dialog", { name: "New playlist" });
    await userEvent.type(within(dialog).getByLabelText("Name"), "bytebytego");
    await userEvent.click(within(dialog).getByRole("button", { name: "Create playlist" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("already have a playlist with that name");
  });

  it("edits the daily target and recommendation order", async () => {
    const { fake } = await open("/videos?playlist=1");
    expect(await screen.findByText("Watched 0 of 2 today")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    const dialog = await screen.findByRole("dialog", { name: "Edit playlist" });
    await userEvent.clear(within(dialog).getByLabelText("Videos to watch per day"));
    await userEvent.type(within(dialog).getByLabelText("Videos to watch per day"), "3");
    await userEvent.selectOptions(within(dialog).getByLabelText(/Recommend videos/), "newest");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Watched 0 of 3 today")).toBeInTheDocument();
    expect(fake.callsTo("PATCH", /video-playlists\/1$/)[0].body).toMatchObject({ daily_target: 3, recommend_order: "newest" });
  });

  it("deleting a playlist needs confirmation and keeps its videos in the library", async () => {
    const { fake, store } = await open("/videos?playlist=1");
    await userEvent.click(await screen.findByRole("button", { name: "Delete playlist ByteByteGo" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete playlist?" });
    expect(dialog).toHaveTextContent("3 videos stay in your library");
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(fake.callsTo("DELETE", /video-playlists/)).toHaveLength(0);

    await userEvent.click(screen.getByRole("button", { name: "Delete playlist ByteByteGo" }));
    await userEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Delete" }));
    expect(await collection("All videos")).toHaveAttribute("aria-selected", "true");
    expect(fake.callsTo("DELETE", /video-playlists\/1$/)).toHaveLength(1);
    expect(store.videos).toHaveLength(3);
    expect(cardTitles(await grid())).toEqual(["How DNS works", "Load balancers", "Rate limiting"]);
  });

  it("shows the server error when the library can't be loaded, and retries", async () => {
    const fake = installFakeApi();
    installFakeVideos(fake, bbg());
    fake.failNext(/^GET \/api\/video-playlists$/, 500, "Database is down");
    renderAt("/videos");
    expect(await screen.findByRole("alert")).toHaveTextContent("Database is down");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await collection("ByteByteGo")).toBeInTheDocument();
  });
});

// ================================ daily target ================================

describe("today (daily target)", () => {
  it("lists exactly as many videos as the target, in recommended order", async () => {
    await open("/videos?playlist=1");
    const list = await screen.findByRole("list", { name: "Up next today" });
    expect(within(list).getByText("How DNS works")).toBeInTheDocument();
    expect(within(list).getByText("Load balancers")).toBeInTheDocument();
    expect(within(list).queryByText("Rate limiting")).not.toBeInTheDocument();
  });

  it("marking one watched updates today's count and removes it from the list", async () => {
    const { fake } = await open("/videos?playlist=1");
    const list = await screen.findByRole("list", { name: "Up next today" });
    await userEvent.click(within(list).getByRole("button", { name: "Mark How DNS works as watched today" }));
    await waitFor(() => expect(screen.getByText("Watched 1 of 2 today")).toBeInTheDocument());
    expect(fake.callsTo("POST", /\/api\/videos\/11\/complete$/)).toHaveLength(1);
    expect(within(await screen.findByRole("list", { name: "Up next today" })).queryByText("How DNS works")).not.toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "ByteByteGo progress" })).toHaveAttribute("aria-valuenow", "33");
  });

  it("says the target is met and points at what is next", async () => {
    const seed = bbg();
    seed.playlists![0].daily_target = 1;
    seed.videos![0] = { ...seed.videos![0], status: "completed", completed_at: new Date().toISOString() };
    await open("/videos?playlist=1", seed);
    const note = (await screen.findByText(/Today's target is met/)).closest("p")!;
    expect(note).toHaveTextContent("Load balancers");
  });

  it("does not count an earlier day towards today", async () => {
    const seed = bbg();
    seed.videos![0] = { ...seed.videos![0], status: "completed", completed_at: "2026-11-01T10:00:00Z" };
    await open("/videos?playlist=1", seed);
    expect(await screen.findByText("Watched 0 of 2 today")).toBeInTheDocument();
    expect(screen.getByText("1 of 3 completed")).toBeInTheDocument();
  });

  it("shows the server's message if marking fails", async () => {
    const { fake } = await open("/videos?playlist=1");
    fake.failNext(/^POST \/api\/videos\/\d+\/complete/, 422, "Could not complete that video");
    const list = await screen.findByRole("list", { name: "Up next today" });
    await userEvent.click(within(list).getByRole("button", { name: "Mark How DNS works as watched today" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not complete that video");
    expect(screen.getByText("Watched 0 of 2 today")).toBeInTheDocument();
  });
});

// ================================ video cards ================================

describe("video cards", () => {
  it("show thumbnail, title, duration, published date, status and a safe Watch link", async () => {
    await open("/videos?playlist=1");
    const list = await grid();
    const card = within(list).getByRole("heading", { name: "How DNS works" }).closest("li")!;
    expect(card.querySelector("img")).toHaveAttribute("src", "https://i.ytimg.com/vi/a/mq.jpg");
    expect(within(card).getByText("4:13")).toBeInTheDocument();
    expect(within(card).getByText("Published 1 Jan 2024")).toBeInTheDocument();
    expect(within(card).getByText("Networking")).toBeInTheDocument();
    expect(within(card).getByRole("combobox", { name: "Status of How DNS works" })).toHaveValue("unwatched");
    const link = within(card).getByRole("link", { name: "Watch How DNS works" });
    expect(link).toHaveAttribute("href", "https://youtu.be/aaaaaaaaaaa");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link.getAttribute("rel")).toMatch(/noopener/);
    expect(within(list).getByText("1:02:03")).toBeInTheDocument();       // long videos show hours
    const bare = within(list).getByRole("heading", { name: "Rate limiting" }).closest("li")!;
    expect(within(bare).queryByRole("link", { name: /Watch/ })).not.toBeInTheDocument(); // no link -> no anchor
    expect(bare.querySelector("img")).toBeNull();                         // no thumbnail -> placeholder, no broken image
  });

  it("marks a card completed and reopens it", async () => {
    const { fake } = await open("/videos?playlist=1");
    const card = (await screen.findByRole("heading", { name: "Load balancers", level: 3 })).closest("li")!;
    await userEvent.click(within(card).getByRole("button", { name: "Mark Load balancers as completed" }));
    expect(await within(card).findByRole("button", { name: "Reopen Load balancers" })).toBeInTheDocument();
    expect(within(card).getByText(/Completed /)).toBeInTheDocument();
    expect(fake.callsTo("POST", /\/api\/videos\/12\/complete$/)).toHaveLength(1);
    await userEvent.click(within(card).getByRole("button", { name: "Reopen Load balancers" }));
    expect(await within(card).findByRole("button", { name: "Mark Load balancers as completed" })).toBeInTheDocument();
    expect(fake.callsTo("POST", /\/api\/videos\/12\/uncomplete$/)).toHaveLength(1);
  });

  it("changes status from the menu (Not started / In progress / Completed)", async () => {
    const { fake } = await open("/videos?playlist=1");
    const card = (await screen.findByRole("heading", { name: "Rate limiting", level: 3 })).closest("li")!;
    const select = within(card).getByRole("combobox", { name: "Status of Rate limiting" });
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["Not started", "In progress", "Completed"]);
    await userEvent.selectOptions(select, "watching");
    await waitFor(() => expect(within(card).getByRole("combobox", { name: "Status of Rate limiting" })).toHaveValue("watching"));
    expect(fake.callsTo("POST", /\/api\/videos\/13\/status$/)[0].body).toEqual({ status: "watching" });
    await userEvent.selectOptions(select, "completed");
    await waitFor(() => expect(within(card).getByRole("button", { name: "Reopen Rate limiting" })).toBeInTheDocument());
  });

  it("edits notes in a dialog and shows them on the card", async () => {
    const { fake } = await open("/videos?playlist=1");
    const card = (await screen.findByRole("heading", { name: "Load balancers", level: 3 })).closest("li")!;
    await userEvent.click(within(card).getByRole("button", { name: "Notes for Load balancers" }));
    const dialog = await screen.findByRole("dialog", { name: "Notes: Load balancers" });
    await userEvent.type(within(dialog).getByLabelText("Notes"), "L4 vs L7");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save notes" }));
    expect(await within(card).findByText(/Note: L4 vs L7/)).toBeInTheDocument();
    expect(fake.callsTo("PATCH", /\/api\/videos\/12$/)[0].body).toEqual({ notes: "L4 vs L7" });
  });

  it("edits the title through the edit form", async () => {
    const { fake } = await open("/videos?playlist=1");
    const card = (await screen.findByRole("heading", { name: "Load balancers", level: 3 })).closest("li")!;
    await userEvent.click(within(card).getByRole("button", { name: "Edit Load balancers" }));
    const dialog = await screen.findByRole("dialog", { name: "Edit video" });
    await userEvent.clear(within(dialog).getByLabelText("Title"));
    await userEvent.type(within(dialog).getByLabelText("Title"), "Load balancing 101");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("heading", { name: "Load balancing 101", level: 3 })).toBeInTheDocument();
    expect(fake.callsTo("PATCH", /\/api\/videos\/12$/)[0].body).toMatchObject({ title: "Load balancing 101" });
  });

  it("shows the server's error on a card", async () => {
    const { fake } = await open("/videos?playlist=1");
    fake.failNext(/^POST \/api\/videos\/13\/complete/, 500, "Disk full");
    const card = (await screen.findByRole("heading", { name: "Rate limiting", level: 3 })).closest("li")!;
    await userEvent.click(within(card).getByRole("button", { name: "Mark Rate limiting as completed" }));
    expect(await within(card).findByRole("alert")).toHaveTextContent("Disk full");
  });
});

// ================================ remove vs delete ================================

describe("removing and deleting", () => {
  it("'Remove from library' hides the video everywhere, shows it under Removed, and can be restored", async () => {
    const { fake } = await open("/videos?playlist=1");
    const card = (await screen.findByRole("heading", { name: "Rate limiting", level: 3 })).closest("li")!;
    await userEvent.click(within(card).getByRole("button", { name: "Remove Rate limiting" }));
    const dialog = await screen.findByRole("dialog", { name: "Remove video" });
    expect(dialog).toHaveTextContent("Nothing happens on YouTube");
    await userEvent.click(within(dialog).getByRole("button", { name: "Remove from library" }));

    await waitFor(() => expect(cardTitles(screen.getByRole("list", { name: "Video library" }))).toEqual(["How DNS works", "Load balancers"]));
    expect(fake.callsTo("POST", /\/api\/videos\/13\/remove$/)).toHaveLength(1);
    expect(fake.callsTo("DELETE", /\/api\/videos/)).toHaveLength(0);          // removing is NOT deleting
    expect(screen.getByText("0 of 2 completed")).toBeInTheDocument();          // progress now counts 2 videos
    await userEvent.click(await screen.findByRole("tab", { name: "Removed (1)" }));
    const removed = (await screen.findByRole("heading", { name: "Rate limiting", level: 3 })).closest("li")!;
    expect(within(removed).getByText("Removed")).toBeInTheDocument();
    await userEvent.click(within(removed).getByRole("button", { name: "Restore Rate limiting" }));
    await waitFor(() => expect(screen.getByText("Nothing removed")).toBeInTheDocument());
    await userEvent.click(screen.getByRole("tab", { name: "Library" }));
    expect(cardTitles(await grid())).toContain("Rate limiting");
  });

  it("a removed video is never recommended", async () => {
    await open("/videos");
    const next = await screen.findByRole("region", { name: "Recommended next video" });
    expect(await within(next).findByText("How DNS works")).toBeInTheDocument();
    const card = (await screen.findByRole("heading", { name: "How DNS works", level: 3 })).closest("li")!;
    await userEvent.click(within(card).getByRole("button", { name: "Remove How DNS works" }));
    await userEvent.click(within(await screen.findByRole("dialog", { name: "Remove video" })).getByRole("button", { name: "Remove from library" }));
    expect(await within(next).findByText("Load balancers")).toBeInTheDocument();
    expect(within(next).queryByText("How DNS works")).not.toBeInTheDocument();
  });

  it("'Delete permanently' erases the video", async () => {
    const { fake, store } = await open("/videos?playlist=1");
    const card = (await screen.findByRole("heading", { name: "Rate limiting", level: 3 })).closest("li")!;
    await userEvent.click(within(card).getByRole("button", { name: "Remove Rate limiting" }));
    await userEvent.click(within(await screen.findByRole("dialog", { name: "Remove video" })).getByRole("button", { name: "Delete permanently" }));
    await waitFor(() => expect(cardTitles(screen.getByRole("list", { name: "Video library" }))).not.toContain("Rate limiting"));
    expect(fake.callsTo("DELETE", /\/api\/videos\/13$/)).toHaveLength(1);
    expect(store.videos.map((v) => v.id)).toEqual([11, 12]);
  });

  it("a removed video can be deleted permanently after a confirmation", async () => {
    const seed = bbg();
    seed.videos![2] = { ...seed.videos![2], removed_at: "2026-11-20T00:00:00Z" };
    const { fake } = await open("/videos?playlist=1", seed);
    await userEvent.click(await screen.findByRole("tab", { name: "Removed (1)" }));
    const removed = (await screen.findByRole("heading", { name: "Rate limiting", level: 3 })).closest("li")!;
    await userEvent.click(within(removed).getByRole("button", { name: "Delete Rate limiting permanently" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete permanently?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(fake.callsTo("DELETE", /\/api\/videos/)).toHaveLength(0);
    await userEvent.click(within(removed).getByRole("button", { name: "Delete Rate limiting permanently" }));
    await userEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Delete permanently" }));
    expect(await screen.findByText("Nothing removed")).toBeInTheDocument();
    expect(fake.callsTo("DELETE", /\/api\/videos\/13$/)).toHaveLength(1);
  });
});

// ================================ filters, search, sort ================================

describe("filters, search and sort", () => {
  it("filters by status on the server", async () => {
    const seed = bbg();
    seed.videos![1] = { ...seed.videos![1], status: "watching" };
    seed.videos![2] = { ...seed.videos![2], status: "completed", completed_at: "2026-11-01T10:00:00Z" };
    const { fake } = await open("/videos?playlist=1", seed);
    await grid();
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Filter by status" }), "completed");
    await waitFor(() => expect(cardTitles(screen.getByRole("list", { name: "Video library" }))).toEqual(["Rate limiting"]));
    expect(fake.callsTo("GET", /videos$/).some((c) => c.query.status === "completed")).toBe(true);
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Filter by status" }), "watching");
    await waitFor(() => expect(cardTitles(screen.getByRole("list", { name: "Video library" }))).toEqual(["Load balancers"]));
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Filter by status" }), "unwatched");
    await waitFor(() => expect(cardTitles(screen.getByRole("list", { name: "Video library" }))).toEqual(["How DNS works"]));
  });

  it("searches by title on the server and explains an empty result", async () => {
    const { fake } = await open("/videos?playlist=1");
    await grid();
    await userEvent.type(screen.getByRole("searchbox", { name: "Search videos" }), "rate");
    await waitFor(() => expect(cardTitles(screen.getByRole("list", { name: "Video library" }))).toEqual(["Rate limiting"]));
    expect(fake.callsTo("GET", /videos$/).some((c) => c.query.q === "rate")).toBe(true);
    await userEvent.clear(screen.getByRole("searchbox", { name: "Search videos" }));
    await userEvent.type(screen.getByRole("searchbox", { name: "Search videos" }), "zzz");
    expect(await screen.findByText("No videos match")).toBeInTheDocument();
  });

  it("sorts newest / oldest / recently completed", async () => {
    const seed = bbg();
    seed.videos![0] = { ...seed.videos![0], status: "completed", completed_at: "2026-11-02T10:00:00Z" };
    seed.videos![1] = { ...seed.videos![1], status: "completed", completed_at: "2026-11-05T10:00:00Z" };
    const { fake } = await open("/videos?playlist=1", seed);
    await grid();
    const sort = screen.getByRole("combobox", { name: "Sort videos" });
    await userEvent.selectOptions(sort, "newest");
    await waitFor(() => expect(cardTitles(screen.getByRole("list", { name: "Video library" }))).toEqual(["Rate limiting", "Load balancers", "How DNS works"]));
    await userEvent.selectOptions(sort, "oldest");
    await waitFor(() => expect(cardTitles(screen.getByRole("list", { name: "Video library" }))).toEqual(["How DNS works", "Load balancers", "Rate limiting"]));
    await userEvent.selectOptions(sort, "completed");
    await waitFor(() => expect(cardTitles(screen.getByRole("list", { name: "Video library" }))[0]).toBe("Load balancers"));
    expect(fake.callsTo("GET", /videos$/).map((c) => c.query.sort)).toEqual(expect.arrayContaining(["newest", "oldest", "completed"]));
  });

  it("offers manual reordering only for 'my own order' collections without filters", async () => {
    const seed = bbg();
    seed.playlists![0].recommend_order = "manual";
    const { fake } = await open("/videos?playlist=1", seed);
    const list = await grid();
    expect(within(list).getByRole("button", { name: "Move How DNS works earlier" })).toBeDisabled();
    expect(within(list).getByRole("button", { name: "Move Rate limiting later" })).toBeDisabled();
    await userEvent.click(within(list).getByRole("button", { name: "Move How DNS works later" }));
    await waitFor(() => expect(cardTitles(screen.getByRole("list", { name: "Video library" }))).toEqual(["Load balancers", "How DNS works", "Rate limiting"]));
    expect(fake.callsTo("POST", /\/api\/videos\/11\/move$/)[0].body).toEqual({ direction: "down", playlist_id: 1 });
    await userEvent.type(screen.getByRole("searchbox", { name: "Search videos" }), "o");
    await waitFor(() => expect(screen.queryByRole("button", { name: /Move .* (earlier|later)/ })).not.toBeInTheDocument());
  });

  it("never offers reordering for date-ordered collections", async () => {
    await open("/videos?playlist=1");
    await grid();
    expect(screen.queryByRole("button", { name: /Move .* (earlier|later)/ })).not.toBeInTheDocument();
  });
});

// ================================ add / paste ================================

describe("adding videos by hand", () => {
  it("adds one video to the selected collection", async () => {
    const { fake } = await open("/videos?playlist=1");
    await grid();
    await userEvent.click(screen.getByRole("button", { name: "Add video" }));
    const dialog = await screen.findByRole("dialog", { name: "Add video" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Add video" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Please give the video a title.");
    await userEvent.type(within(dialog).getByLabelText("Title"), "CDN basics");
    await userEvent.type(within(dialog).getByLabelText(/^Link/), "https://youtu.be/ccccccccccc");
    await userEvent.click(within(dialog).getByRole("button", { name: "Add video" }));
    expect(await screen.findByRole("heading", { name: "CDN basics", level: 3 })).toBeInTheDocument();
    expect(fake.callsTo("POST", /video-playlists\/1\/videos$/)[0].body).toEqual({
      title: "CDN basics", url: "https://youtu.be/ccccccccccc", category: null, description: null, notes: null,
    });
  });

  it("keeps the form open with the server's rejection", async () => {
    const { fake } = await open("/videos?playlist=1");
    await grid();
    fake.failNext(/^POST \/api\/video-playlists\/1\/videos$/, 409, "That video is already in this playlist");
    await userEvent.click(screen.getByRole("button", { name: "Add video" }));
    const dialog = await screen.findByRole("dialog", { name: "Add video" });
    await userEvent.type(within(dialog).getByLabelText("Title"), "Again");
    await userEvent.click(within(dialog).getByRole("button", { name: "Add video" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("already in this playlist");
  });

  it("only offers 'Add video' and 'Paste links' inside a collection", async () => {
    await open("/videos");
    await grid();
    expect(screen.queryByRole("button", { name: "Add video" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Paste links" })).not.toBeInTheDocument();
  });
});

describe("pasting links", () => {
  async function openPaste() {
    const s = await open("/videos?playlist=1");
    await grid();
    await userEvent.click(screen.getByRole("button", { name: "Paste links" }));
    return { ...s, dialog: await screen.findByRole("dialog", { name: "Paste video links" }) };
  }

  it("reports added / duplicate / unreadable lines", async () => {
    const { fake, dialog } = await openPaste();
    fireEvent.change(within(dialog).getByLabelText(/Links, one per line/), {
      target: { value: "CDN basics | https://youtu.be/bbbbbbbbbbb\n\nhttps://youtu.be/aaaaaaaaaaa\nnot a link\n" },
    });
    expect(within(dialog).getByText("3 lines")).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Add videos" }));
    const result = await within(dialog).findByRole("status");
    expect(result).toHaveTextContent("Added 1 video");
    expect(result).toHaveTextContent("skipped 1 already in the playlist");
    expect(result).toHaveTextContent("couldn't read 1 line");
    expect(fake.callsTo("POST", /bulk-videos$/)[0].body).toMatchObject({ lines: expect.arrayContaining(["not a link"]) });
    await userEvent.click(within(dialog).getByRole("button", { name: "Done" }));
    expect(await screen.findByRole("heading", { name: "CDN basics", level: 3 })).toBeInTheDocument();
  });

  it("disables submit until something is pasted and refuses more than 200 lines", async () => {
    const { dialog } = await openPaste();
    const submit = within(dialog).getByRole("button", { name: "Add videos" });
    expect(submit).toBeDisabled();
    const box = within(dialog).getByLabelText(/Links, one per line/);
    fireEvent.change(box, { target: { value: Array.from({ length: 201 }, (_, i) => `https://example.com/${i}`).join("\n") } });
    expect(submit).toBeDisabled();
    expect(within(dialog).getByText("Paste at most 200 lines at a time.")).toBeInTheDocument();
    fireEvent.change(box, { target: { value: "https://example.com/1" } });
    expect(submit).toBeEnabled();
  });
});

// ================================ YouTube import ================================

describe("importing from YouTube", () => {
  async function openImport(seed: Partial<FakeVideos> = { playlists: [], videos: [] }) {
    const s = await open("/videos", seed);
    await userEvent.click(await screen.findByRole("button", { name: "Import from YouTube" }));
    return { ...s, dialog: await screen.findByRole("dialog", { name: "Import from YouTube" }) };
  }
  const link = (dialog: HTMLElement, url = "https://www.youtube.com/@ByteByteGo") =>
    userEvent.type(within(dialog).getByLabelText(/YouTube channel or playlist link/), url);
  const rows = () => within(screen.getByRole("list", { name: "Videos found" })).getAllByRole("listitem");

  it("explains how to set up the key when the server has none, and offers no form", async () => {
    const { dialog } = await openImport({ playlists: [], videos: [], youtube: { configured: false, source: { ...mkSource() }, catalog: [], unavailable: 0 } });
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("YOUTUBE_API_KEY");
    expect(within(dialog).queryByRole("button", { name: "Preview videos" })).not.toBeInTheDocument();
  });

  it("previews first - nothing is saved until the user chooses videos and confirms", async () => {
    const { fake, store, dialog } = await openImport();
    await link(dialog);
    await userEvent.selectOptions(within(dialog).getByLabelText("How many videos to retrieve"), "10");
    await userEvent.click(within(dialog).getByRole("button", { name: "Preview videos" }));

    const choose = await screen.findByRole("dialog", { name: "Choose videos to import" });
    expect(fake.callsTo("POST", /youtube\/preview$/)[0].body).toEqual({ url: "https://www.youtube.com/@ByteByteGo", limit: 10 });
    expect(within(choose).getByText("Fake Channel")).toBeInTheDocument();
    expect(within(choose).getByText("On YouTube:").nextSibling).toHaveTextContent("120");
    expect(within(choose).getByText("Retrieved:").nextSibling).toHaveTextContent("10");
    expect(within(choose).getByText("Selected:").nextSibling).toHaveTextContent("0");
    expect(rows()).toHaveLength(10);
    expect(within(rows()[0]).getByText("YT video 120")).toBeInTheDocument();
    expect(rows()[0].querySelector("img")).toHaveAttribute("src", expect.stringContaining("i.ytimg.com"));
    expect(screen.getAllByRole("checkbox").every((c) => !(c as HTMLInputElement).checked)).toBe(true);   // nothing pre-selected
    expect(within(choose).getByRole("button", { name: "Import 0 selected" })).toBeDisabled();
    expect(fake.callsTo("POST", /youtube\/import$/)).toHaveLength(0);
    expect(store.videos).toHaveLength(0);
  });

  it("imports exactly the ticked videos and reports the result", async () => {
    const { fake, store, dialog } = await openImport();
    await link(dialog);
    await userEvent.selectOptions(within(dialog).getByLabelText("How many videos to retrieve"), "10");
    await userEvent.click(within(dialog).getByRole("button", { name: "Preview videos" }));
    const choose = await screen.findByRole("dialog", { name: "Choose videos to import" });
    await userEvent.click(within(choose).getByRole("checkbox", { name: "Select YT video 120" }));
    await userEvent.click(within(choose).getByRole("checkbox", { name: "Select YT video 117" }));
    expect(within(choose).getByText("Selected:").nextSibling).toHaveTextContent("2");
    await userEvent.click(within(choose).getByRole("button", { name: "Import 2 selected" }));

    const done = await screen.findByRole("status");
    expect(done).toHaveTextContent("Imported 2 new videos into Fake Channel");
    expect(done).toHaveTextContent("Nothing was marked as watched");
    expect(fake.callsTo("POST", /youtube\/import$/)[0].body).toEqual({
      url: "https://www.youtube.com/@ByteByteGo", video_ids: ["yt000000120", "yt000000117"], retrieved: 10,
    });
    expect(store.videos.map((v) => v.title)).toEqual(["YT video 120", "YT video 117"]);
    expect(store.videos.every((v) => v.status === "unwatched" && v.completed_at === null)).toBe(true);

    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Done" }));
    expect(await screen.findByRole("heading", { name: "Fake Channel", level: 2 })).toBeInTheDocument();   // jumps to the new collection
    const overview = screen.getByRole("region", { name: "Fake Channel overview" });
    expect(within(overview).getByText("On YouTube").nextSibling).toHaveTextContent("120");
    expect(within(overview).getByText("Retrieved").nextSibling).toHaveTextContent("10");
    expect(within(overview).getByText("In library").nextSibling).toHaveTextContent("2");
    expect(cardTitles(await grid())).toEqual(["YT video 117", "YT video 120"]);   // oldest published first
  });

  it("'Select all new' ticks every video that isn't already in the library", async () => {
    const seed = bbg();
    seed.videos![0] = { ...seed.videos![0], youtube_video_id: "yt000000120", title: "YT video 120" };
    const { dialog } = await openImport(seed);
    await link(dialog);
    await userEvent.selectOptions(within(dialog).getByLabelText("How many videos to retrieve"), "10");
    await userEvent.click(within(dialog).getByRole("button", { name: "Preview videos" }));
    const choose = await screen.findByRole("dialog", { name: "Choose videos to import" });
    const owned = within(choose).getByRole("checkbox", { name: "Select YT video 120" });
    expect(owned).toBeDisabled();
    expect(within(choose).getByText("Already in library")).toBeInTheDocument();
    expect(within(choose).getByText("Already in library:").nextSibling).toHaveTextContent("1");
    await userEvent.click(within(choose).getByRole("button", { name: "Select all new (9)" }));
    expect(within(choose).getByText("Selected:").nextSibling).toHaveTextContent("9");
    expect(owned).not.toBeChecked();
    await userEvent.click(within(choose).getByRole("button", { name: "Clear selection" }));
    expect(within(choose).getByText("Selected:").nextSibling).toHaveTextContent("0");
  });

  it("marks videos removed earlier as restorable", async () => {
    const seed = bbg();
    seed.videos![0] = { ...seed.videos![0], youtube_video_id: "yt000000120", title: "YT video 120", removed_at: "2026-11-01T00:00:00Z" };
    const { dialog } = await openImport(seed);
    await link(dialog);
    await userEvent.click(within(dialog).getByRole("button", { name: "Preview videos" }));
    const choose = await screen.findByRole("dialog", { name: "Choose videos to import" });
    expect(within(choose).getByText("Removed earlier, will be restored")).toBeInTheDocument();
    expect(within(choose).getByRole("checkbox", { name: "Select YT video 120" })).toBeEnabled();
  });

  it.each([
    ["10", 10], ["25", 25], ["50", 50], ["100", 100], ["all", null],
  ])("retrieval option %s sends limit %s", async (option, limit) => {
    const { fake, dialog } = await openImport();
    await link(dialog);
    await userEvent.selectOptions(within(dialog).getByLabelText("How many videos to retrieve"), option);
    await userEvent.click(within(dialog).getByRole("button", { name: "Preview videos" }));
    await screen.findByRole("dialog", { name: "Choose videos to import" });
    expect(fake.callsTo("POST", /youtube\/preview$/)[0].body).toMatchObject({ limit });
  });

  it("a custom number is validated, then sent", async () => {
    const { fake, dialog } = await openImport();
    await link(dialog);
    await userEvent.selectOptions(within(dialog).getByLabelText("How many videos to retrieve"), "custom");
    const box = within(dialog).getByLabelText("Custom number of videos");
    await userEvent.clear(box);
    await userEvent.type(box, "0");
    await userEvent.click(within(dialog).getByRole("button", { name: "Preview videos" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("1 to 2000");
    expect(fake.callsTo("POST", /youtube\/preview$/)).toHaveLength(0);
    await userEvent.clear(box);
    await userEvent.type(box, "7");
    await userEvent.click(within(dialog).getByRole("button", { name: "Preview videos" }));
    const choose = await screen.findByRole("dialog", { name: "Choose videos to import" });
    expect(fake.callsTo("POST", /youtube\/preview$/)[0].body).toMatchObject({ limit: 7 });
    expect(rows()).toHaveLength(7);
    expect(within(choose).getByText(/YouTube has more videos than the 7 retrieved/)).toBeInTheDocument();
  });

  it("asks for a link, and shows the server's message for a bad one", async () => {
    const { fake, dialog } = await openImport();
    await userEvent.click(within(dialog).getByRole("button", { name: "Preview videos" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Paste a YouTube channel or playlist link.");
    expect(fake.callsTo("POST", /youtube\/preview$/)).toHaveLength(0);
    await link(dialog, "https://example.com/nope");
    await userEvent.click(within(dialog).getByRole("button", { name: "Preview videos" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("doesn't look like a YouTube channel or playlist link");
  });

  it("shows YouTube failures (quota, private playlist) without losing the form", async () => {
    const { fake, dialog } = await openImport();
    fake.failNext(/^POST \/api\/youtube\/preview$/, 429, "YouTube's daily request limit for this API key is used up.");
    await link(dialog, "https://www.youtube.com/playlist?list=PLxxxxxxxxxx");
    await userEvent.click(within(dialog).getByRole("button", { name: "Preview videos" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("daily request limit");
    expect(within(dialog).getByLabelText(/YouTube channel or playlist link/)).toHaveValue("https://www.youtube.com/playlist?list=PLxxxxxxxxxx");
  });

  it("shows 'unavailable' for a total YouTube did not report", async () => {
    const { dialog, store } = await openImport();
    store.youtube.source = { ...store.youtube.source, total_available: null };
    await link(dialog);
    await userEvent.click(within(dialog).getByRole("button", { name: "Preview videos" }));
    const choose = await screen.findByRole("dialog", { name: "Choose videos to import" });
    expect(within(choose).getByText("On YouTube:").nextSibling).toHaveTextContent("unavailable");
  });

  it("keeps the selection and shows the error when the import fails, and can go back", async () => {
    const { fake, dialog } = await openImport();
    await link(dialog);
    await userEvent.selectOptions(within(dialog).getByLabelText("How many videos to retrieve"), "10");
    await userEvent.click(within(dialog).getByRole("button", { name: "Preview videos" }));
    const choose = await screen.findByRole("dialog", { name: "Choose videos to import" });
    await userEvent.click(within(choose).getByRole("checkbox", { name: "Select YT video 119" }));
    fake.failNext(/^POST \/api\/youtube\/import$/, 502, "Couldn't reach YouTube. Check your internet connection and try again.");
    await userEvent.click(within(choose).getByRole("button", { name: "Import 1 selected" }));
    expect(await within(choose).findByRole("alert")).toHaveTextContent("Couldn't reach YouTube");
    expect(within(choose).getByRole("checkbox", { name: "Select YT video 119" })).toBeChecked();
    await userEvent.click(within(choose).getByRole("button", { name: "Back" }));
    expect(await screen.findByRole("dialog", { name: "Import from YouTube" })).toBeInTheDocument();
  });

  it("reports videos that were already linked or unavailable", async () => {
    const { store, dialog } = await openImport();
    await link(dialog);
    await userEvent.selectOptions(within(dialog).getByLabelText("How many videos to retrieve"), "10");
    await userEvent.click(within(dialog).getByRole("button", { name: "Preview videos" }));
    const choose = await screen.findByRole("dialog", { name: "Choose videos to import" });
    await userEvent.click(within(choose).getByRole("checkbox", { name: "Select YT video 120" }));
    store.youtube.catalog = store.youtube.catalog.slice(1); // it disappears from YouTube before the user confirms
    await userEvent.click(within(choose).getByRole("button", { name: "Import 1 selected" }));
    expect(await screen.findByRole("status")).toHaveTextContent("1 are no longer available on YouTube and were skipped");
  });
});

function mkSource() {
  return { kind: "channel" as const, id: "UCx", title: "X", url: "https://www.youtube.com/channel/UCx", thumbnail_url: null, total_available: null, handle: null, channel_title: null };
}

// ================================ navigation ================================

describe("navigation", () => {
  it("the sidebar link is live (no Soon badge) and leads to the page", async () => {
    await open("/");
    await screen.findByRole("heading", { name: /Ada Lovelace/ });
    const nav = screen.getAllByRole("navigation")[0];
    const link = within(nav).getByRole("link", { name: /Videos/ });
    expect(within(link).queryByText("Soon")).not.toBeInTheDocument();
    await userEvent.click(link);
    expect(await screen.findByRole("heading", { name: "Videos", level: 1 })).toBeInTheDocument();
  });
});

