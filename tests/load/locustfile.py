"""StoryForge Load Testing — Locust scenarios. Q3+Q7.

Usage:
  locust -f tests/load/locustfile.py --headless -u 50 -r 5 -t 2m \
      --host http://localhost:7860
Tags: smoke, read, config, pipeline, export, mixed, write, heavy
"""

import random
from locust import HttpUser, between, events, tag, task

SAMPLE_GENRES = ["Tiên Hiệp", "Ngôn Tình", "Kiếm Hiệp", "Đô Thị", "Khoa Huyễn"]
SAMPLE_IDEAS = [
    "Một thanh niên bình thường bỗng phát hiện mình có khả năng đặc biệt.",
    "Câu chuyện về một nữ chính mạnh mẽ vượt qua nghịch cảnh.",
    "Hành trình tu luyện của một võ sĩ trẻ để đạt đỉnh cao.",
    "Thám tử thiên tài giải vụ án bí ẩn nhất lịch sử.",
    "Chuyện tình giữa hai người từ hai thế giới khác nhau.",
]


class HealthCheckUser(HttpUser):
    """High-frequency smoke test on /api/health."""
    wait_time = between(0.5, 1.5)
    weight = 3

    @tag("smoke", "read")
    @task
    def health_check(self):
        with self.client.get("/api/health", catch_response=True) as resp:
            if resp.status_code == 200:
                if resp.json().get("status") != "ok":
                    resp.failure("Unexpected status body")
            else:
                resp.failure(f"Status {resp.status_code}")


class ConfigUser(HttpUser):
    """Read-heavy GET/PUT /api/config operations."""
    wait_time = between(1, 3)
    weight = 4

    @tag("config", "read")
    @task(5)
    def get_config(self):
        self.client.get("/api/config")

    @tag("config", "read")
    @task(3)
    def get_presets(self):
        self.client.get("/api/config/presets")

    @tag("config", "read")
    @task(2)
    def get_model_presets(self):
        self.client.get("/api/config/model-presets")

    @tag("config", "read")
    @task(2)
    def get_languages(self):
        self.client.get("/api/config/languages")

    @tag("config", "write")
    @task(1)
    def update_temperature(self):
        self.client.put("/api/config", json={"temperature": round(random.uniform(0.6, 1.0), 1)})


class PipelineUser(HttpUser):
    """Heavy pipeline operations — throttled with long wait times."""
    wait_time = between(10, 30)
    weight = 1

    @tag("pipeline", "read")
    @task(3)
    def list_genres(self):
        self.client.get("/api/pipeline/genres")

    @tag("pipeline", "read")
    @task(2)
    def list_checkpoints(self):
        self.client.get("/api/pipeline/checkpoints")

    @tag("pipeline", "heavy")
    @task(1)
    def start_pipeline(self):
        """POST /api/pipeline/run — verify SSE stream starts (not full completion)."""
        payload = {
            "title": f"Load Test {random.randint(1000, 9999)}",
            "genre": random.choice(SAMPLE_GENRES),
            "idea": random.choice(SAMPLE_IDEAS),
            "num_chapters": 1, "num_characters": 2, "word_count": 500,
            "num_sim_rounds": 1, "enable_agents": False,
            "enable_scoring": False, "enable_media": False,
        }
        with self.client.post(
            "/api/pipeline/run", json=payload,
            headers={"Accept": "text/event-stream"},
            stream=True, catch_response=True, timeout=15,
        ) as resp:
            if resp.status_code not in (200, 202):
                resp.failure(f"Pipeline start returned {resp.status_code}")
            else:
                for line in resp.iter_lines():
                    if line:
                        resp.success()
                        break


class ExportUser(HttpUser):
    """Export endpoint reachability — 404 expected without active session."""
    wait_time = between(5, 15)
    weight = 2

    @tag("export")
    @task
    def export_pdf_no_session(self):
        fake_session = f"load-test-{random.randint(10000, 99999)}"
        with self.client.post(f"/api/export/pdf/{fake_session}", catch_response=True) as resp:
            if resp.status_code in (404, 200):
                resp.success()
            else:
                resp.failure(f"Unexpected status: {resp.status_code}")


class MixedUser(HttpUser):
    """Realistic 70% reads, 20% config writes, 10% pipeline reads."""
    wait_time = between(1, 4)
    weight = 5

    @tag("mixed", "read", "smoke")
    @task(7)
    def read_health(self):
        self.client.get("/api/health")

    @tag("mixed", "read", "config")
    @task(7)
    def read_config(self):
        self.client.get("/api/config")

    @tag("mixed", "read", "config")
    @task(7)
    def read_presets(self):
        self.client.get("/api/config/presets")

    @tag("mixed", "config", "write")
    @task(2)
    def write_config(self):
        self.client.put("/api/config", json={"temperature": round(random.uniform(0.5, 0.9), 1)})

    @tag("mixed", "config")
    @task(2)
    def apply_preset(self):
        key = random.choice(["quick", "standard", "quality"])
        with self.client.post(f"/api/config/presets/{key}", catch_response=True) as resp:
            if resp.status_code in (200, 404):
                resp.success()

    @tag("mixed", "pipeline", "read")
    @task(1)
    def read_genres(self):
        self.client.get("/api/pipeline/genres")

    @tag("mixed", "pipeline", "read")
    @task(1)
    def read_checkpoints(self):
        self.client.get("/api/pipeline/checkpoints")


@events.quitting.add_listener
def on_quitting(environment, **kwargs):
    """Print pass/fail summary when test ends."""
    s = environment.stats.total
    rate = s.num_failures / max(s.num_requests, 1)
    print(
        f"\n{'='*50}\nStoryForge Load Test Summary\n"
        f"  Requests: {s.num_requests}  Failures: {s.num_failures}\n"
        f"  p50: {s.median_response_time}ms  "
        f"p95: {s.get_response_time_percentile(0.95)}ms  "
        f"RPS: {s.current_rps:.1f}\n"
        f"  {'OK' if rate <= 0.01 else 'WARN'}: failure rate {rate:.1%}\n"
        f"{'='*50}\n"
    )
