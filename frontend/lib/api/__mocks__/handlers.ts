/**
 * MSW handlers for /api/pipeline endpoints. Used by Vitest + Playwright suites.
 * Backend contract source: api/pipeline_routes.py.
 */

import { http, HttpResponse } from "msw";

export const handlers = [
  http.get("/api/pipeline/genres", () =>
    HttpResponse.json({
      genres: ["Tiên Hiệp", "Kiếm Hiệp", "Đô Thị"],
      styles: ["Miêu tả chi tiết", "Hành động"],
      drama_levels: ["thấp", "trung bình", "cao"],
      languages: [
        { code: "vi", label: "Tiếng Việt" },
        { code: "en", label: "English" },
      ],
    })
  ),

  http.get("/api/pipeline/stories", ({ request }) => {
    const url = new URL(request.url);
    const limit = Number(url.searchParams.get("limit") ?? "20");
    const offset = Number(url.searchParams.get("offset") ?? "0");
    const items = Array.from({ length: limit }, (_, i) => ({
      filename: `story_${offset + i}_layer2.json`,
      title: `Truyện ${offset + i + 1}`,
      genre: "Tiên Hiệp",
      chapter_count: 5,
      current_layer: 2,
      size_kb: 42,
      modified: new Date().toISOString(),
    }));
    return HttpResponse.json({ items, total: 40, limit, offset });
  }),

  http.get("/api/pipeline/checkpoints/:filename", ({ params }) =>
    HttpResponse.json({
      filename: params.filename,
      title: "Mock Story",
      chapters: [],
      source: "library",
    })
  ),

  // Note: /api/pipeline/run is a POST SSE stream — handled by the e2e harness
  // (Playwright shims it directly) rather than msw.
];
