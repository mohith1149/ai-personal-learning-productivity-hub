import {
  Bot,
  CalendarCheck,
  CirclePlay,
  Flame,
  FolderGit2,
  GraduationCap,
  LayoutDashboard,
  ListChecks,
  Map as MapIcon,
  Repeat,
  Settings,
  type LucideIcon,
} from "lucide-react";

export type NavItem = {
  to: string;
  label: string;
  icon: LucideIcon;
  /** "ready" = the feature works end to end. "soon" = route exists but shows an honest placeholder. */
  status: "ready" | "soon";
  /** Which Phase 3 milestone delivers it (shown on the placeholder page). */
  milestone?: string;
  blurb?: string;
};

export type NavGroup = { heading: string; items: NavItem[] };

/**
 * Single source of truth for navigation AND routing.
 * When a milestone ships a feature, flip its status to "ready" and swap its placeholder route in App.tsx.
 */
export const NAV_GROUPS: NavGroup[] = [
  {
    heading: "Today",
    items: [
      { to: "/", label: "Dashboard", icon: LayoutDashboard, status: "ready" },
      {
        to: "/planner",
        label: "Daily planner",
        icon: CalendarCheck,
        status: "soon",
        milestone: "Milestone 10",
        blurb: "Today's tasks, habits, study goal and project work in one plan.",
      },
      {
        to: "/challenge",
        label: "Daily challenge",
        icon: Flame,
        status: "soon",
        milestone: "Milestone 9",
        blurb: "Every day needs verified project work or an explicit excuse. Nothing is auto-completed.",
      },
    ],
  },
  {
    heading: "Work",
    items: [
      {
        to: "/tasks",
        label: "Tasks",
        icon: ListChecks,
        status: "ready",
      },
      {
        to: "/projects",
        label: "Projects",
        icon: FolderGit2,
        status: "soon",
        milestone: "Milestone 8",
        blurb: "Project ideas, milestones and work sessions.",
      },
      {
        to: "/habits",
        label: "Habits",
        icon: Repeat,
        status: "ready",
      },
    ],
  },
  {
    heading: "Learn",
    items: [
      {
        to: "/courses",
        label: "Courses",
        icon: GraduationCap,
        status: "ready",
      },
      {
        to: "/videos",
        label: "Videos",
        icon: CirclePlay,
        status: "ready",
      },
      {
        to: "/roadmap",
        label: "AI roadmap",
        icon: MapIcon,
        status: "ready",
      },
    ],
  },
  {
    heading: "Assistant",
    items: [
      {
        to: "/assistant",
        label: "AI assistant",
        icon: Bot,
        status: "soon",
        milestone: "Milestone 12 and Phase 6",
        blurb: "The assistant needs real tools to call first. The provider layer comes in Milestone 12; the live Claude connection comes in Phase 6.",
      },
    ],
  },
];

export const SETTINGS_ITEM: NavItem = { to: "/settings", label: "Settings", icon: Settings, status: "ready" };

export const ALL_NAV_ITEMS: NavItem[] = [...NAV_GROUPS.flatMap((g) => g.items), SETTINGS_ITEM];
