import { expect, test } from "vitest";
import { add } from "../src/math";

test("adds", () => {
  expect(add(1, 1)).toBe(2);
});
