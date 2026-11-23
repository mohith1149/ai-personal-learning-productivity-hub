import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme, type Theme } from "../theme";
import { cx } from "./ui";

const OPTIONS: { value: Theme; label: string; icon: typeof Sun }[] = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Monitor },
];

/** Segmented control. `showLabels` is used on the Settings page; the header uses icons only. */
export function ThemeSwitcher({ showLabels = false }: { showLabels?: boolean }) {
  const { theme, setTheme } = useTheme();
  return (
    <div
      role="radiogroup"
      aria-label="Colour theme"
      className="inline-flex rounded-lg border border-slate-200 bg-slate-100 p-0.5 dark:border-slate-700 dark:bg-slate-800"
    >
      {OPTIONS.map(({ value, label, icon: Icon }) => {
        const active = theme === value;
        return (
          <button
            key={value}
            role="radio"
            aria-checked={active}
            aria-label={label}
            title={label}
            onClick={() => setTheme(value)}
            className={cx(
              "flex items-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-medium transition",
              active
                ? "bg-white text-brand-700 shadow-sm dark:bg-slate-950 dark:text-brand-400"
                : "text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200",
            )}
          >
            <Icon className="h-4 w-4" aria-hidden />
            {showLabels && label}
          </button>
        );
      })}
    </div>
  );
}
