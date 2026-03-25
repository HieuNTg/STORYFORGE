"""Mô phỏng tương tác nhân vật - Lấy cảm hứng từ MiroFish.

MiroFish tạo các agent tự trị trên mạng xã hội giả lập.
Ở đây ta mô phỏng nhân vật truyện tương tác tự do trong một
"không gian ảo" để phát hiện xung đột và tình huống kịch tính.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError, as_completed

from models.schemas import (
    Character, Relationship, RelationType, SimulationEvent, AgentPost,
    SimulationResult, EscalationPattern,
)
from services.llm_client import LLMClient
from services import prompts
from config import ConfigManager
from pipeline.layer2_enhance._agent import CharacterAgent, TENSION_DELTAS
from pipeline.layer2_enhance.drama_patterns import get_genre_escalation_prompt

logger = logging.getLogger(__name__)

ESCALATION_PATTERNS = {
    "phản_bội": {"trigger_tension": 0.7, "intensity_multiplier": 2.0},
    "tiết_lộ": {"trigger_tension": 0.5, "intensity_multiplier": 1.5},
    "đối_đầu": {"trigger_tension": 0.6, "intensity_multiplier": 1.8},
    "hy_sinh": {"trigger_tension": 0.8, "intensity_multiplier": 2.5},
    "đảo_ngược": {"trigger_tension": 0.65, "intensity_multiplier": 1.7},
}

# Which relationship types are valid for each escalation pattern.
# None means the pattern can trigger for any relationship type.
ESCALATION_VALID_RELATIONS: dict[str, list[RelationType] | None] = {
    "phản_bội": [RelationType.ALLY, RelationType.LOVER, RelationType.FAMILY, RelationType.MENTOR],
    "tiết_lộ": None,
    "đối_đầu": [RelationType.RIVAL, RelationType.ENEMY, RelationType.UNKNOWN],
    "hy_sinh": [RelationType.ALLY, RelationType.LOVER, RelationType.FAMILY, RelationType.MENTOR],
    "đảo_ngược": None,
}

_CLOSE_RELATION_TYPES = {"đồng_minh", "tình_nhân", "gia_đình", "sư_phụ"}
_HOSTILE_RELATION_TYPES = {"kẻ_thù", "phản_bội", "đối_thủ"}


class TrustNetworkEdge:
    """Pairwise trust between two characters at simulator level."""

    def __init__(self, char_a: str, char_b: str, trust: float = 50.0):
        self.char_a = char_a
        self.char_b = char_b
        self.trust = trust  # 0-100
        self.history: list[str] = []

    def update_trust(self, delta: float, reason: str = ""):
        old = self.trust
        self.trust = max(0.0, min(100.0, self.trust + delta))
        if reason:
            self.history.append(f"{old:.0f}→{self.trust:.0f}: {reason}")
            if len(self.history) > 10:
                self.history = self.history[-10:]

    @property
    def is_betrayal_candidate(self) -> bool:
        """True if trust has dropped below 30."""
        return self.trust < 30


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
        self.trust_network: dict[str, TrustNetworkEdge] = {}

    def setup_agents(
        self,
        characters: list[Character],
        relationships: list[Relationship],
    ):
        """Khởi tạo agent cho mỗi nhân vật."""
        self.agents = {c.name: CharacterAgent(c) for c in characters}
        self.relationships = list(relationships)
        # Initialize trust network from relationships
        self.trust_network = {}
        for rel in self.relationships:
            key = f"{rel.character_a}|{rel.character_b}"
            initial_trust = 70.0 if rel.relation_type.value in _CLOSE_RELATION_TYPES else 40.0
            self.trust_network[key] = TrustNetworkEdge(rel.character_a, rel.character_b, initial_trust)
        logger.info(f"Đã tạo {len(self.agents)} agent nhân vật, {len(self.trust_network)} trust edges")

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

    def _infer_mood(self, sentiment: str) -> str:
        """Infer mood from sentiment text."""
        mapping = {
            "tích_cực": "quyết_tâm", "tiêu_cực": "đau_khổ",
            "tức_giận": "tức_giận", "sợ_hãi": "sợ_hãi",
            "vui": "bình_thường", "buồn": "đau_khổ",
            "hận": "hận_thù", "yêu": "yêu",
        }
        for key, mood in mapping.items():
            if key in sentiment.lower():
                return mood
        return "bình_thường"

    def _run_single_agent(self, name: str, round_number: int, context: str) -> tuple[AgentPost | None, dict]:
        """Chạy một agent trong vòng mô phỏng. Thread-safe (read-only shared state)."""
        agent = self.agents[name]
        recent_posts = self._get_recent_posts(name)
        rel_text = self._get_relationships_text(name)
        c = agent.character

        try:
            result = self.llm.generate_json(
                system_prompt=(
                    f"Bạn đang nhập vai {name} trong một mô phỏng tương tác. "
                    f"Hãy hành động theo tính cách và TÂM TRẠNG hiện tại. "
                    f"Trả về JSON với: content, action_type, target, sentiment, "
                    f"new_mood (tâm trạng mới), trust_change (số từ -30 đến +10 cho target)."
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
                        f"Trạng thái: {agent.get_emotional_context()}. "
                        f"Ký ức gần đây: {'; '.join(agent.memory[-3:]) if agent.memory else 'Không có.'}"
                    ),
                    recent_posts=recent_posts,
                ),
                temperature=0.95,
            )

            post = AgentPost(
                agent_name=name,
                content=result.get("content", "..."),
                action_type=result.get("action_type", "post"),
                target=result.get("target", ""),
                sentiment=result.get("sentiment", "trung lập"),
                round_number=round_number,
            )
            metadata = {
                "new_mood": result.get("new_mood", ""),
                "trust_change": result.get("trust_change", 0),
            }
            return post, metadata
        except Exception as e:
            logger.warning(f"Agent {name} lỗi ở vòng {round_number}: {e}")
            return None, {}

    def _generate_reactions(self, posts: list[AgentPost], round_num: int, context: str) -> list[AgentPost]:
        """Generate reactions from targeted characters (1 reaction layer)."""
        reactions = []
        targeted = {p.target: p for p in posts if p.target and p.target in self.agents}

        max_workers = min(ConfigManager().llm.max_parallel_workers, 10)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for target_name, triggering_post in targeted.items():
                if target_name == triggering_post.agent_name:
                    continue
                agent = self.agents[target_name]
                future = executor.submit(self._run_reaction, agent, triggering_post, round_num, context)
                futures[future] = target_name

            for future in as_completed(futures):
                try:
                    result = future.result(timeout=120)
                    if result:
                        reactions.append(result)
                except FutureTimeoutError:
                    target_name = futures[future]
                    logger.warning(f"Reaction from {target_name} timed out after 120s, skipping")
                except Exception as e:
                    target_name = futures[future]
                    logger.warning(f"Reaction from {target_name} raised unexpected error: {e}")
        return reactions

    def _run_reaction(self, agent: CharacterAgent, triggering_post: AgentPost, round_num: int, context: str) -> AgentPost | None:
        """Generate a reaction from agent to a triggering post."""
        try:
            result = self.llm.generate_json(
                system_prompt=(
                    f"Bạn là {agent.character.name}. Phản ứng với hành động của {triggering_post.agent_name}. "
                    f"Trạng thái: {agent.get_emotional_context()}. Trả về JSON."
                ),
                user_prompt=(
                    f"Hành động gây ra: [{triggering_post.agent_name}] {triggering_post.action_type}: "
                    f"{triggering_post.content}\n"
                    f"Tính cách bạn: {agent.character.personality}\n"
                    f"Động lực: {agent.character.motivation}\n"
                    f"Hãy phản ứng tự nhiên. JSON: content, action_type, sentiment, new_mood, trust_change"
                ),
                temperature=0.9,
            )
            new_mood = result.get("new_mood", "")
            if new_mood:
                agent.emotion.update(new_mood)
            trust_delta = result.get("trust_change", 0)
            if isinstance(trust_delta, (int, float)):
                agent.get_trust(triggering_post.agent_name).update(trust_delta)
            return AgentPost(
                agent_name=agent.character.name,
                content=result.get("content", "..."),
                action_type=f"phản_ứng_{result.get('action_type', 'post')}",
                target=triggering_post.agent_name,
                sentiment=result.get("sentiment", "trung lập"),
                round_number=round_num,
            )
        except Exception as e:
            logger.warning(f"Reaction from {agent.character.name} failed: {e}")
            return None

    def simulate_round(
        self, round_number: int, context: str, total_rounds: int = 5,
        progress_callback=None,
    ) -> list[AgentPost]:
        """Chạy một vòng mô phỏng - tất cả agents hành động song song."""
        round_posts = []
        max_workers = min(ConfigManager().llm.max_parallel_workers, 10)
        genre_hint = get_genre_escalation_prompt(context, round_number, total_rounds)
        round_context = f"{context} {genre_hint}".strip() if genre_hint else context
        agent_names = list(self.agents.keys())
        completed_count = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self._run_single_agent, name, round_number, round_context): name
                for name in self.agents
            }
            for future in as_completed(futures):
                name = futures[future]
                try:
                    post, metadata = future.result(timeout=120)
                except FutureTimeoutError:
                    logger.warning(f"Agent {name} timed out at round {round_number}, skipping")
                    continue
                except Exception as e:
                    logger.warning(f"Agent {name} raised unexpected error at round {round_number}: {e}")
                    continue
                completed_count += 1
                if progress_callback:
                    progress_callback(
                        f"[Agent {completed_count}/{len(agent_names)}] "
                        f"{name}: {post.action_type if post else 'skip'}"
                    )
                if post is not None:
                    round_posts.append(post)
                    # Apply emotional + trust updates immediately
                    agent = self.agents[post.agent_name]
                    new_mood = metadata.get("new_mood", "") or self._infer_mood(post.sentiment)
                    agent.emotion.update(new_mood)
                    trust_delta = metadata.get("trust_change", 0)
                    if isinstance(trust_delta, (int, float)) and post.target and post.target in self.agents:
                        agent.get_trust(post.target).update(trust_delta, post.content[:50])

        # Post-round updates (sequential, safe) + emotional state + trust network
        for post in round_posts:
            agent = self.agents[post.agent_name]
            agent.posts.append(post)
            agent.add_memory(f"Vòng {round_number}: {post.content[:100]}")
            agent.process_event(post.action_type)
            if post.target and post.target in self.agents:
                target_agent = self.agents[post.target]
                target_agent.add_memory(
                    f"Vòng {round_number}: {post.agent_name} đã {post.action_type} - {post.content[:80]}"
                )
                target_agent.process_event(post.action_type, is_target=True)
                # Update simulator-level trust network
                key = f"{post.agent_name}|{post.target}"
                rev_key = f"{post.target}|{post.agent_name}"
                edge = self.trust_network.get(key) or self.trust_network.get(rev_key)
                if edge:
                    trust_delta = -15.0 if post.sentiment in ("tiêu cực", "căng thẳng") else 5.0
                    edge.update_trust(trust_delta, f"R{round_number}: {post.action_type}")

        # Reaction chain: targeted characters respond (1 layer)
        reactions = self._generate_reactions(round_posts, round_number, context)
        for post in reactions:
            agent = self.agents[post.agent_name]
            agent.posts.append(post)
            agent.add_memory(f"Vòng {round_number} [phản ứng]: {post.content[:100]}")
        round_posts.extend(reactions)

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

    def _check_escalation(self, round_num: int) -> list[EscalationPattern]:
        """Check tension thresholds and return triggered escalation patterns."""
        triggered = []
        seen_types: set[str] = set()
        for rel in self.relationships:
            for ptype, cfg in ESCALATION_PATTERNS.items():
                if rel.tension < cfg["trigger_tension"] or ptype in seen_types:
                    continue
                valid_relations = ESCALATION_VALID_RELATIONS.get(ptype)
                if valid_relations is not None and rel.relation_type not in valid_relations:
                    continue
                seen_types.add(ptype)
                triggered.append(EscalationPattern(
                    pattern_type=ptype,
                    trigger_tension=cfg["trigger_tension"],
                    characters_required=2,
                    description=f"{rel.character_a} vs {rel.character_b}",
                    intensity_multiplier=cfg["intensity_multiplier"],
                ))
        return triggered

    def _apply_escalation(self, pattern: EscalationPattern, round_num: int, genre: str) -> SimulationEvent | None:
        """Generate escalation event via LLM."""
        chars = pattern.description.split(" vs ")
        try:
            result = self.llm.generate_json(
                system_prompt="Bạn là đạo diễn kịch tính. Trả về JSON.",
                user_prompt=prompts.ESCALATION_EVENT.format(
                    pattern_type=pattern.pattern_type,
                    characters=pattern.description,
                    relationship=f"Xung đột cấp {pattern.trigger_tension:.1f}",
                    genre=genre,
                    characters_list=", ".join(f'"{c.strip()}"' for c in chars),
                ),
                temperature=0.9,
            )
            raw_score = result.get("drama_score", 0.7)
            boosted = min(1.0, raw_score * pattern.intensity_multiplier)
            # Scale by average drama_multiplier of involved agents (bounded 0.5–3.0)
            chars_involved = result.get("characters_involved", chars)
            agent_multipliers = [
                self.agents[c.strip()].emotion.drama_multiplier
                for c in chars_involved
                if c.strip() in self.agents
            ]
            avg_multiplier = (
                sum(agent_multipliers) / len(agent_multipliers)
                if agent_multipliers else 1.0
            )
            avg_multiplier = min(3.0, max(0.5, avg_multiplier))
            boosted = min(1.0, boosted * avg_multiplier)
            return SimulationEvent(
                round_number=round_num,
                event_type=result.get("event_type", pattern.pattern_type),
                characters_involved=result.get("characters_involved", chars),
                description=result.get("description", ""),
                drama_score=boosted,
                suggested_insertion=result.get("suggested_insertion", ""),
            )
        except Exception as e:
            logger.warning(f"Escalation {pattern.pattern_type} failed: {e}")
            return None

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
            round_posts = self.simulate_round(
                round_num, genre, num_rounds, progress_callback=progress_callback,
            )

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
                except (KeyError, ValueError, TypeError) as e:
                    logger.debug(f"Skipping malformed simulation event at round {round_num}: {e}")
                    continue

            all_drama_scores.append(evaluation.get("overall_drama_score", 0.5))

            # Check and apply escalation patterns
            escalations = self._check_escalation(round_num)
            for pattern in escalations[:2]:  # Max 2 escalations per round
                esc_event = self._apply_escalation(pattern, round_num, genre)
                if esc_event:
                    all_events.append(esc_event)
                    _log(f"⚡ Escalation: {pattern.pattern_type} — {pattern.description}")

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
        """Cập nhật mối quan hệ dựa trên kết quả mô phỏng + trust network."""
        a, b = change.get("character_a", ""), change.get("character_b", "")
        new_type = change.get("new_relation", "")

        for rel in self.relationships:
            if (rel.character_a == a and rel.character_b == b) or \
               (rel.character_a == b and rel.character_b == a):
                try:
                    rel.relation_type = RelationType(new_type)
                    delta = TENSION_DELTAS.get(new_type, 0.1)
                    rel.tension = max(0.0, min(1.0, rel.tension + delta))
                    # Sync with trust network
                    key = f"{a}|{b}"
                    rev_key = f"{b}|{a}"
                    edge = self.trust_network.get(key) or self.trust_network.get(rev_key)
                    if edge:
                        trust_change = -20.0 if new_type in _HOSTILE_RELATION_TYPES else 10.0
                        edge.update_trust(trust_change, f"Relationship → {new_type}")
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
