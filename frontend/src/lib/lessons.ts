/** Turn a pasted list into lesson titles: one per line, blank lines dropped, and list markers such as
 *  "- ", "* ", "• ", "1. " or "2) " removed so pasting from a syllabus just works. */
export function parseLessonLines(text: string): string[] {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim().replace(/^([-*•]|\d+[.)])\s+/, "").trim())
    .filter((line) => line.length > 0);
}
