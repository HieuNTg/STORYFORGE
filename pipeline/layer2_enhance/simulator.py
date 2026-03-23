"""Mô phỏng tương tác nhân vật - Lấy cảm hứng từ MiroFish.

MiroFish tạo các agent tự trị trên mạng xã hội giả lập.
Ở đây ta mô phỏng nhân vật truyện tương tác tự do trong một
"không gian ảo" để phát hiện xung đột và tình huống kịch tính.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from models.schemas import (
    Character, Relationship, RelationType, SimulationEvent, AgentPost,
    SimulationResult,
)
from services.llm_client import LLMClient
from services import prompts
from config import ConfigManager
from pipeline.layer2_enhance._agent import CharacterAgent, TENSION_DELTAS

logger = logging.getLogger(__name__)


class DramaSimulator:
    """Mô phỏng tương tác nhân vật để tìm tình huống kịch tính.

    Lấy cảm hứng từ kiến trúc MiroFish:
    - Mỗi nhân vật là một agent tự trị với persona riêng
    - Agents tương tác tự do trong nhiều vòng
    - Hệ thống đánh giá và trích xuất sự kiện kịch tính
    - Mối quan hệ được cập nhật động sau mỗi vòng
    """

    def __init__(self):
        self.llm = LLMClient()
        self.agents: dict[str, CharacterAgent] = {}
        self.all_posts: list[AgentPost] = []
        self.relationships: list[Relationship] = []

    def setup_agents(
        self,
        characters: list[Character],
        relationships: list[Relationship],
    ):
        """Khởi tạo agent cho mỗi nhân vật."""
        self.agents = {c.name: CharacterAgent(c) for c in characters}
        self.relationships = list(relationships)
        logger.info(f"Đã tạo {len(self.agents)} agent nhân vật")

    def _get_recent_posts(self, exclude_agent: str, limit: int = 5) -> str:
        """Lấy các bài viết gần đây của nhân vật khác."""
        recent = [
            p for p in self.all_posts[-20:]
            if p.agent_name != exclude_agent
        ][-limit:]
        if not recent:
            return "Chưa có hoạt động nào."
        return "\n".join(
            f"[{p.agent_name}] ({p.action_type}): {p.content}"
            + (f" → {p.target}" if p.target else "")
            for p in recent
        )

    def _get_relationships_text(self, agent_name: str) -> str:
        """Lấy mối quan hệ liên quan đến một nhân vật."""
        related = [
            r for r in self.relationships
            if r.character_a == agent_name or r.character_b == agent_name
        ]
        if not related:
            return "Chưa có mối quan hệ rõ ràng."
        return "\n".join(
            f"- {r.character_a} ↔ {r.character_b}: {r.relation_type.value} "
            f"(cường độ: {r.intensity:.1f}, xung đột: {r.tension:.1f}) - {r.description}"
            for r in related
        )

    def _run_single_agent(self, name: str, round_number: int, context: str) -> AgentPost | None:
        """Chạy một agent trong vòng mô phỏng. Thread-safe (read-only shared state)."""
        agent = self.agents[name]
        recent_posts = self._get_recent_posts(name)
        rel_text = self._get_relationships_text(name)
        c = agent.character

        try:
            result = self.llm.generate_json(
                system_prompt=(
                    f"Bạn đang nhập vai {name} trong một mô phỏng tương tác. "
                    f"Hãy hành động theo tính cách nhân vật. Trả về JSON."
                ),
                user_prompt=prompts.AGENT_PERSONA.format(
                    character_name=name,
                    genre=context,
                    personality=c.personality,
                    background=c.background,
                    motivation=c.motivation,
                    relationships=rel_text,
                    current_context=(
                        f"Vòng mô phỏng {round_number}. "
                        f"Bạn đang trong thế giới truyện. "
                        f"Ký ức gần đây: {'; '.join(agent.memory[-3:]) if agent.memory else 'Không có.'}"
                    ),
                    recent_posts=recent_posts,
                ),
                temperature=0.95,
            )

            return AgentPost(
                agent_name=name,
                content=result.get("content", "..."),
                action_type=result.get("action_type", "post"),
                target=result.get("target", ""),
                sentiment=result.get("sentiment", "trung lập"),
                round_number=round_number,
            )
        except Exception as e:
            logger.warning(f"Agent {name} lỗi ở vòng {round_number}: {e}")
            return None

    def simulate_round(
        self, round_number: int, context: str,
    ) -> list[AgentPost]:
        """Chạy một vòng mô phỏng - tất cả agents hành động song song."""
        round_posts = []
        max_workers = ConfigManager().llm.max_parallel_workers

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self._run_single_agent, name, round_number, context): name
                for name in self.agents
            }
            for future in as_completed(futures):
                post = future.result()
                if post is not None:
                    round_posts.append(post)

        # Post-round updates (sequential, safe)
        for post in round_posts:
            agent = self.agents[post.agent_name]
            agent.posts.append(post)
            agent.add_memory(f"Vòng {round_number}: {post.content[:100]}")
            if post.target and post.target in self.agents:
                self.agents[post.target].add_memory(
                    f"Vòng {round_number}: {post.agent_name} đã {post.action_type} - {post.content[:80]}"
                )

        self.all_posts.extend(round_posts)
        return round_posts

    def evaluate_drama(self, round_posts: list[AgentPost]) -> dict:
        """Đánh giá mức kịch tính của vòng mô phỏng."""
        actions_text = "\n".join(
            f"- [{p.agent_name}] {p.action_type}: {p.content}"
            + (f" (nhắm đến {p.target})" if p.target else "")
            + f" [cảm xúc: {p.sentiment}]"
            for p in round_posts
        )
        rel_text = "\n".join(
            f"- {r.character_a} ↔ {r.character_b}: {r.relation_type.value} "
            f"(xung đột: {r.tension:.1f})"
            for r in self.relationships
        )

        return self.llm.generate_json(
            system_prompt="Bạn là đạo diễn kịch tính. Trả về JSON.",
            user_prompt=prompts.EVALUATE_DRAMA.format(
                actions=actions_text,
                relationships=rel_text,
            ),
        )

    def run_simulation(
        self,
        characters: list[Character],
        relationships: list[Relationship],
        genre: str,
        num_rounds: int = 5,
        progress_callback=None,
    ) -> SimulationResult:
        """Chạy toàn bộ mô phỏng và trả về kết quả."""

        def _log(msg):
            logger.info(msg)
            if progress_callback:
                progress_callback(msg)

        self.setup_agents(characters, relationships)
        all_events: list[SimulationEvent] = []
        all_drama_scores: list[float] = []

        for round_num in range(1, num_rounds + 1):
            _log(f"🔄 Vòng mô phỏng {round_num}/{num_rounds}...")

            # Chạy vòng mô phỏng
            round_posts = self.simulate_round(round_num, genre)

            # Đánh giá kịch tính
            evaluation = self.evaluate_drama(round_posts)

            # Trích xuất sự kiện
            for ev in evaluation.get("events", []):
                try:
                    event = SimulationEvent(
                        round_number=round_num,
                        event_type=ev.get("event_type", "xung_đột"),
                        characters_involved=ev.get("characters_involved", []),
                        description=ev.get("description", ""),
                        drama_score=ev.get("drama_score", 0.5),
                        suggested_insertion=ev.get("suggested_insertion", ""),
                    )
                    all_events.append(event)
                except Exception:
                    continue

            all_drama_scores.append(evaluation.get("overall_drama_score", 0.5))

            # Cập nhật mối quan hệ
            for change in evaluation.get("relationship_changes", []):
                self._update_relationship(change)

        # Tạo gợi ý kịch tính
        _log("💡 Đang tạo gợi ý tăng cường kịch tính...")
        suggestions_result = self._generate_suggestions(genre)

        result = SimulationResult(
            events=all_events,
            updated_relationships=self.relationships,
            drama_suggestions=suggestions_result.get("suggestions", []),
            character_arcs=suggestions_result.get("character_arcs", {}),
            tension_map=suggestions_result.get("tension_points", {}),
            agent_posts=self.all_posts,
        )

        avg_drama = sum(all_drama_scores) / len(all_drama_scores) if all_drama_scores else 0
        _log(f"✅ Mô phỏng hoàn tất! Điểm kịch tính trung bình: {avg_drama:.2f}")
        return result

    def _update_relationship(self, change: dict):
        """Cập nhật mối quan hệ dựa trên kết quả mô phỏng."""
        a, b = change.get("character_a", ""), change.get("character_b", "")
        new_type = change.get("new_relation", "")

        for rel in self.relationships:
            if (rel.character_a == a and rel.character_b == b) or \
               (rel.character_a == b and rel.character_b == a):
                try:
                    rel.relation_type = RelationType(new_type)
                    # Lấy delta tension theo loại quan hệ mới
                    delta = TENSION_DELTAS.get(new_type, 0.1)
                    rel.tension = max(0.0, min(1.0, rel.tension + delta))
                except ValueError:
                    pass
                return

    def _generate_suggestions(self, genre: str) -> dict:
        """Tạo gợi ý tăng kịch tính dựa trên kết quả mô phỏng."""
        sim_summary = "\n".join(
            f"- [{p.agent_name}→{p.target or 'all'}] {p.action_type}: {p.content[:100]}"
            for p in self.all_posts[-30:]
        )
        story_summary = "\n".join(
            f"- {r.character_a} ↔ {r.character_b}: {r.relation_type.value} "
            f"(xung đột: {r.tension:.1f})"
            for r in self.relationships
        )

        return self.llm.generate_json(
            system_prompt="Bạn là cố vấn kịch bản. Trả về JSON.",
            user_prompt=prompts.DRAMA_SUGGESTIONS.format(
                simulation_summary=sim_summary,
                story_summary=story_summary,
            ),
        )
