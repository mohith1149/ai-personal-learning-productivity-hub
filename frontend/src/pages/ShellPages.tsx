import { Compass, Hammer } from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import { useAuthStatus } from "../api/auth";
import { ThemeSwitcher } from "../components/ThemeSwitcher";
import { Button, Card, EmptyState, PageHeader } from "../components/ui";
import { ALL_NAV_ITEMS } from "../nav";

function greeting(timeZone: string): string {
  // "Good morning" is based on the user's configured timezone, not the browser's.
  let hour: number;
  try {
    hour = Number(new Intl.DateTimeFormat("en-GB", { hour: "numeric", hour12: false, timeZone }).format(new Date()));
  } catch {
    hour = new Date().getHours();
  }
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

/**
 * Placeholder dashboard. Deliberately shows NO numbers: every metric on the real dashboard
 * (Milestone 11) will be computed from the database, and a fake figure here would break that rule.
 */
export function DashboardPage() {
  const user = useAuthStatus().data?.user;
  if (!user) return null;
  return (
    <>
      <PageHeader title={`${greeting(user.timezone)}, ${user.display_name}`} description="Here's where your day will come together." />
      <EmptyState icon={Compass} title="Nothing to show yet">
        Your dashboard fills in from real data as you add tasks, courses, habits and projects. Every number here will come
        straight from your database, so there is nothing to display until you start using the app.
      </EmptyState>
    </>
  );
}

/** Honest placeholder for routes whose feature has not been built yet. */
export function ComingSoonPage() {
  const { pathname } = useLocation();
  const item = ALL_NAV_ITEMS.find((i) => i.to === pathname);
  if (!item) return <NotFoundPage />;
  return (
    <>
      <PageHeader title={item.label} />
      <EmptyState icon={Hammer} title="Not built yet">
        {item.blurb}
        {item.milestone && <span className="mt-2 block font-medium text-slate-600 dark:text-slate-300">Planned: {item.milestone}</span>}
      </EmptyState>
    </>
  );
}

export function SettingsPage() {
  const user = useAuthStatus().data?.user;
  return (
    <>
      <PageHeader title="Settings" description="Your account and appearance." />
      <div className="grid max-w-2xl gap-5">
        <Card>
          <h2 className="mb-3 text-sm font-semibold text-slate-900 dark:text-white">Account</h2>
          <dl className="grid grid-cols-[7rem_1fr] gap-y-2 text-sm">
            <dt className="text-slate-500 dark:text-slate-400">Name</dt>
            <dd>{user?.display_name}</dd>
            <dt className="text-slate-500 dark:text-slate-400">Email</dt>
            <dd className="break-all">{user?.email}</dd>
            <dt className="text-slate-500 dark:text-slate-400">Timezone</dt>
            <dd>{user?.timezone}</dd>
          </dl>
          <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
            Editing your profile and timezone arrives with a later milestone.
          </p>
        </Card>
        <Card>
          <h2 className="mb-1 text-sm font-semibold text-slate-900 dark:text-white">Appearance</h2>
          <p className="mb-3 text-sm text-slate-500 dark:text-slate-400">
            "System" follows your device's light or dark setting. The choice is remembered in this browser.
          </p>
          <ThemeSwitcher showLabels />
        </Card>
      </div>
    </>
  );
}

export function NotFoundPage() {
  return (
    <EmptyState
      title="Page not found"
      action={
        <Link to="/">
          <Button variant="secondary">Back to dashboard</Button>
        </Link>
      }
    >
      That address doesn't match anything in the app.
    </EmptyState>
  );
}
