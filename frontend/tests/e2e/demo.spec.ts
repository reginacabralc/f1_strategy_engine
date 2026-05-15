import { test, expect } from "@playwright/test";

const MOCK_SESSIONS = [
  {
    session_id: "bahrain_2024_R",
    circuit_id: "bahrain",
    season: 2024,
    round_number: 1,
    date: "2024-03-02",
    total_laps: 57,
  },
  {
    session_id: "monaco_2024_R",
    circuit_id: "monaco",
    season: 2024,
    round_number: 8,
    date: "2024-05-26",
    total_laps: 78,
  },
];

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/sessions", (route) =>
    route.fulfill({ status: 200, json: MOCK_SESSIONS }),
  );
  await page.route("**/api/v1/degradation**", (route) =>
    route.fulfill({ status: 404, json: { detail: "No data available" } }),
  );
  await page.route("**/api/v1/backtest/**", (route) =>
    route.fulfill({ status: 404, json: { detail: "No data available" } }),
  );
});

test("happy path: branding, session selection, and dashboard shell", async ({
  page,
}) => {
  await page.goto("/");

  // Branding is visible
  await expect(page.getByText("PITWALL")).toBeVisible();
  await expect(page.locator("text=🏎")).toBeVisible();

  // Session picker is present and loaded with mock sessions
  const picker = page.getByRole("combobox");
  await expect(picker).toBeVisible();
  await expect(picker.locator("option", { hasText: "bahrain" })).toHaveCount(1);
  await expect(picker.locator("option", { hasText: "monaco" })).toHaveCount(1);

  // No-session hint is visible before selection
  await expect(page.getByTestId("no-session-hint")).toBeVisible();

  // Select the Monaco session
  await picker.selectOption("monaco_2024_R");

  // No-session hint disappears once a session is selected
  await expect(page.getByTestId("no-session-hint")).not.toBeVisible();

  // Race table columns are rendered
  await expect(page.getByRole("table")).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Driver" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Compound" })).toBeVisible();

  // Alert panel section is present (empty state is fine — no replay running)
  await expect(
    page.getByRole("region", { name: "Strategy alerts" }),
  ).toBeVisible();

  // Degradation chart section is present
  await expect(
    page.getByRole("region", { name: "Tyre degradation chart" }),
  ).toBeVisible();

  // Replay controls footer is visible
  await expect(
    page.getByRole("contentinfo", { name: "Replay controls" }),
  ).toBeVisible();
});
