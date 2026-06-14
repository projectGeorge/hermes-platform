import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BrandLogo } from "./BrandLogo";

describe("BrandLogo", () => {
  it("renders the Hermes mark and wordmark", () => {
    render(<BrandLogo />);

    expect(screen.getByLabelText(/hermes logo/i)).toBeInTheDocument();
    expect(screen.getByText("Hermes")).toBeInTheDocument();
  });
});
