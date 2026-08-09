import { describe, expect, it } from "vitest";
import {
  createDefaultRubricDimension,
  toRubricDimensionFormValues,
  toRubricDimensions,
} from "./rubric-form";

describe("rubric form conversions", () => {
  it("creates an editable 100-point fallback for absent dimensions", () => {
    expect(createDefaultRubricDimension()).toEqual({
      name: "",
      weight: 100,
      criteria: "",
      max_score: 100,
    });
    expect(toRubricDimensionFormValues(undefined)).toEqual([
      createDefaultRubricDimension(),
    ]);
    expect(toRubricDimensionFormValues(null)).toEqual([
      createDefaultRubricDimension(),
    ]);
    expect(toRubricDimensionFormValues([])).toEqual([
      createDefaultRubricDimension(),
    ]);
  });

  it("normalizes incomplete and invalid persisted dimensions safely", () => {
    expect(
      toRubricDimensionFormValues([
        {},
        {
          name: "Knowledge",
          weight: Number.NaN,
          criteria: ["accurate", "complete"],
          max_score: Number.POSITIVE_INFINITY,
        },
        { name: "Listening", weight: 0, criteria: [], max_score: 0 },
      ]),
    ).toEqual([
      { name: "", weight: 0, criteria: "", max_score: 100 },
      {
        name: "Knowledge",
        weight: 0,
        criteria: "accurate, complete",
        max_score: 100,
      },
      { name: "Listening", weight: 0, criteria: "", max_score: 0 },
    ]);
  });

  it("converts editable criteria while dropping blank comma segments", () => {
    expect(
      toRubricDimensions([
        {
          name: "Knowledge",
          weight: 100,
          criteria: " accurate, , complete ,",
          max_score: 100,
        },
      ]),
    ).toEqual([
      {
        name: "Knowledge",
        weight: 100,
        criteria: ["accurate", "complete"],
        max_score: 100,
      },
    ]);
  });

  it("uses a valid fallback payload when editable dimensions are absent", () => {
    const expected = [
      { name: "", weight: 100, criteria: [], max_score: 100 },
    ];
    expect(toRubricDimensions(undefined)).toEqual(expected);
    expect(toRubricDimensions(null)).toEqual(expected);
    expect(toRubricDimensions([])).toEqual(expected);
  });
});
