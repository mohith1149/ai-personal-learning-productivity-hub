import { describe, expect, it } from "vitest";
import { parseLessonLines } from "../lib/lessons";

describe("parseLessonLines", () => {
  it("splits on lines, trims, and drops blanks", () => {
    expect(parseLessonLines("  Intro \n\n   \nReflection\r\nTools  ")).toEqual(["Intro", "Reflection", "Tools"]);
  });

  it("strips common list markers so pasting from a syllabus works", () => {
    expect(parseLessonLines("1. Welcome\n2) What is agentic AI?\n- Degrees of autonomy\n* Task decomposition\n• Evals")).toEqual([
      "Welcome", "What is agentic AI?", "Degrees of autonomy", "Task decomposition", "Evals",
    ]);
  });

  it("keeps numbers that are part of the title", () => {
    expect(parseLessonLines("2024 trends\n3D vision\n10. Ten things")).toEqual(["2024 trends", "3D vision", "Ten things"]);
  });

  it("returns nothing for empty input", () => {
    expect(parseLessonLines("")).toEqual([]);
    expect(parseLessonLines(" \n \n")).toEqual([]);
  });
});
