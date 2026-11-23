export const PRIORITIES = [
  { value: 1, label: "Urgent" },
  { value: 2, label: "High" },
  { value: 3, label: "Normal" },
  { value: 4, label: "Low" },
] as const;

export const priorityLabel = (p: number) => PRIORITIES.find((x) => x.value === p)?.label ?? String(p);

export const FREQUENCIES = [
  { value: "daily", label: "Every day" },
  { value: "weekdays", label: "Weekdays (Mon–Fri)" },
  { value: "weekly", label: "Weekly, on chosen days" },
  { value: "monthly", label: "Monthly, on a day of the month" },
] as const;
