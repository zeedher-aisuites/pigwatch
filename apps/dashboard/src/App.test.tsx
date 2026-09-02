import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { App } from "./App";

describe("App", () => {
  it("states the M0 boundary and veterinary safety guardrail", () => {
    const markup = renderToStaticMarkup(<App />);

    expect(markup).toContain("Engineering foundation ready");
    expect(markup).toContain("does not independently diagnose veterinary disease");
  });
});
