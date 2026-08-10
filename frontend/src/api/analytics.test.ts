import { beforeEach, describe, expect, it, vi } from "vitest";
import { saveAs } from "file-saver";
import apiClient from "./client";
import {
  downloadAdminReportExcel,
  downloadSessionsExcel,
  getDimensionTrends,
  getOrgAnalytics,
  getRecommendedScenarios,
  getScoreTrends,
  getUserDashboardStats,
} from "./analytics";

vi.mock("./client", () => ({ default: { get: vi.fn() } }));
vi.mock("file-saver", () => ({ saveAs: vi.fn() }));

const mockGet = apiClient.get as ReturnType<typeof vi.fn>;

describe("Analytics API client", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(Date, "now").mockReturnValue(1234);
  });

  it("fetches dashboard and organization summaries", async () => {
    mockGet
      .mockResolvedValueOnce({ data: { total_sessions: 3 } })
      .mockResolvedValueOnce({ data: { active_users: 2 } });

    await expect(getUserDashboardStats()).resolves.toEqual({ total_sessions: 3 });
    await expect(getOrgAnalytics()).resolves.toEqual({ active_users: 2 });
    expect(mockGet).toHaveBeenNthCalledWith(1, "/analytics/dashboard");
    expect(mockGet).toHaveBeenNthCalledWith(2, "/analytics/admin/overview");
  });

  it.each([
    ["dimension trends", getDimensionTrends, "/analytics/trends", "limit"],
    ["recommendations", getRecommendedScenarios, "/analytics/recommendations", "limit"],
    ["score trends", getScoreTrends, "/analytics/admin/score-trends", "months"],
  ] as const)("fetches %s with and without a limit", async (_label, request, url, key) => {
    mockGet.mockResolvedValue({ data: [] });

    await expect(request()).resolves.toEqual([]);
    expect(mockGet).toHaveBeenLastCalledWith(url, { params: undefined });

    await expect(request(6)).resolves.toEqual([]);
    expect(mockGet).toHaveBeenLastCalledWith(url, { params: { [key]: 6 } });
  });

  it("downloads both report exports with timestamped names", async () => {
    const sessionsBlob = new Blob(["sessions"]);
    const adminBlob = new Blob(["admin"]);
    mockGet
      .mockResolvedValueOnce({ data: sessionsBlob })
      .mockResolvedValueOnce({ data: adminBlob });

    await downloadSessionsExcel();
    await downloadAdminReportExcel();

    expect(mockGet).toHaveBeenNthCalledWith(1, "/analytics/export/sessions", {
      responseType: "blob",
    });
    expect(mockGet).toHaveBeenNthCalledWith(2, "/analytics/export/admin-report", {
      responseType: "blob",
    });
    expect(saveAs).toHaveBeenNthCalledWith(1, sessionsBlob, "sessions-report-1234.xlsx");
    expect(saveAs).toHaveBeenNthCalledWith(2, adminBlob, "admin-report-1234.xlsx");
  });
});
