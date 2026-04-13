"""Mô phỏng tương tác nhân vật - Lấy cảm hứng từ MiroFish.

MiroFish tạo các agent tự trị trên mạng xã hội giả lập.
Ở đây ta mô phỏng nhân vật truyện tương tác tự do trong một
"không gian ảo" để phát hiện xung đột và tình huống kịch tính.
"""

import asyncio
import logging

from models.schemas import (
    Character, Relationship, RelationType, SimulationEvent, AgentPost,
    SimulationResult, EscalationPattern,
)
from services.llm_client import LLMClient
from services import prompts
from pipeline.layer2_enhance._agent import CharacterAgent, TENSION_DELTAS
from pipeline.layer2_enhance.drama_patterns import get_genre_escalation_prompt, get_tension_modifier

try:
    from pipeline.layer2_enhance.psychology_engine import PsychologyEngine
    _PSYCHOLOGY_AVAILABLE = True
except Exception:  # pragma: no cover
    _PSYCHOLOGY_AVAILABLE = False

try:
    from pipeline.layer2_enhance.knowledge_system import KnowledgeRegistry
    _KNOWLEDGE_AVAILABLE = True
except Exception:  # pragma: no cover
    _KNOWLEDGE_AVAILABLE = False

try:
    from pipeline.layer2_enhance.causal_chain import CausalGraph
    _CAUSAL_AVAILABLE = True
except Exception:  # pragma: no cover
    _CAUSAL_AVAILABLE = False

try:
    from pipeline.layer2_enhance.adaptive_intensity import AdaptiveController
    _ADAPTIVE_AVAILABLE = True
except Exception:  # pragma: no cover
    _ADAPTIVE_AVAILABLE = False

logger = logging.getLogger(__name__)

# Cấu hình cường độ kịch tính — ảnh hưởng đến nhiệt độ, ngưỡng leo thang, độ sâu phản ứng
INTENSITY_CONFIG = {
    "thấp": {"temperature": 0.7, "escalation_scale": 0.7, "max_escalations": 1, "reaction_depth": 1},
    "trung bình": {"temperature": 0.85, "escalation_scale": 1.0, "max_escalations": 2, "reaction_depth": 2},
    "cao": {"temperature": 0.95, "escalation_scale": 1.3, "max_escalations": 2, "reaction_depth": 3},
}


def _get_intensity_config(drama_intensity: str) -> dict:
    return INTENSITY_CONFIG.get(drama_intensity, INTENSITY_CONFIG["cao"])


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
        self.threads: list = []
        self.trust_network: dict[str, TrustNetworkEdge] = {}
        self._intensity: dict = _get_intensity_config("cao")
        self._psychology_engine = PsychologyEngine() if _PSYCHOLOGY_AVAILABLE else None
        self.knowledge: "KnowledgeRegistry | None" = None
        self.causal_graph: "CausalGraph | None" = None
        self.adaptive: "AdaptiveController | None" = None

    def setup_agents(
        self,
        characters: list[Character],
        relationships: list[Relationship],
        arc_waypoints: list[dict] | None = None,
        threads: list | None = None,
        current_chapter: int = 1,
    ):
        """Khởi tạo agent cho mỗi nhân vật."""
        self.agents = {c.name: CharacterAgent(c) for c in characters}
        self.relationships = list(relationships)
        self.threads = list(threads) if threads else []
        self._apply_arc_waypoints(arc_waypoints, current_chapter)
        # Initialize trust network from relationships
        self.trust_network = {}
        for rel in self.relationships:
            key = f"{rel.character_a}|{rel.character_b}"
            initial_trust = 70.0 if rel.relation_type.value in _CLOSE_RELATION_TYPES else 40.0
            self.trust_network[key] = TrustNetworkEdge(rel.character_a, rel.character_b, initial_trust)
        logger.info(f"Đã tạo {len(self.agents)} agent nhân vật, {len(self.trust_network)} trust edges")

        # Khởi tạo hệ thống tri thức (non-fatal)
        if _KNOWLEDGE_AVAILABLE:
            try:
                self.knowledge = KnowledgeRegistry()
                for c in characters:
                    self.knowledge.register_secret(c)
                self.knowledge.register_initial_knowledge(characters, relationships)
                logger.info("Đã khởi tạo KnowledgeRegistry")
            except Exception as e:
                logger.warning(f"KnowledgeRegistry thất bại, tiếp tục không có: {e}")
                self.knowledge = None

        # Khởi tạo đồ thị nhân quả (non-fatal)
        if _CAUSAL_AVAILABLE:
            try:
                self.causal_graph = CausalGraph()
                logger.info("Đã khởi tạo CausalGraph")
            except Exception as e:
                logger.warning(f"CausalGraph thất bại: {e}")
                self.causal_graph = None

        # Extract psychology for each agent in parallel (non-fatal)
        if self._psychology_engine:
            try:
                self._extract_all_psychology(characters)
            except Exception as e:
                logger.warning(f"Psychology extraction thất bại, tiếp tục không có tâm lý: {e}")

        # Phase C: thread-urgency → psychology pressure (pure-python, non-fatal)
        if self._psychology_engine and self.threads:
            try:
                _thread_pressure_on = True
                try:
                    from config import ConfigManager as _CM
                    _thread_pressure_on = bool(getattr(_CM().load().pipeline, "l2_thread_pressure", True))
                except Exception:
                    pass
                if _thread_pressure_on:
                    for agent in self.agents.values():
                        psych = getattr(agent, "psychology", None)
                        if psych is None:
                            continue
                        self._psychology_engine.apply_thread_pressure(
                            psych, self.threads, current_chapter
                        )
            except Exception as e:
                logger.debug(f"apply_thread_pressure failed (non-fatal): {e}")

    def _extract_all_psychology(self, characters: list[Character]) -> None:
        """Trích xuất tâm lý cho tất cả nhân vật song song."""
        import asyncio as _asyncio

        engine = self._psychology_engine
        if engine is None:
            return

        async def _gather():
            loop = _asyncio.get_running_loop()

            async def _one(character: Character):
                try:
                    return character.name, await _asyncio.wait_for(
                        loop.run_in_executor(
                            None, engine.extract_psychology, character, characters
                        ),
                        timeout=60,
                    )
                except Exception as e:
                    logger.warning(f"Psychology timeout/lỗi cho '{character.name}': {e}")
                    return character.name, None

            results = await _asyncio.gather(*[_one(c) for c in characters])
            return results

        gathered = asyncio.run(_gather())
        for name, psychology in gathered:
            if psychology is not None and name in self.agents:
                self.agents[name].psychology = psychology
        logger.info("Đã trích xuất tâm lý cho tất cả nhân vật")

    def _apply_arc_waypoints(self, waypoints_list, current_chapter: int):
        if not waypoints_list:
            return
        applied = 0
        for entry in waypoints_list:
            try:
                if hasattr(entry, "model_dump"):
                    entry = entry.model_dump()
                if not isinstance(entry, dict):
                    continue
                char_name = entry.get("character") or entry.get("character_name") or entry.get("name")
                if not char_name or char_name not in self.agents:
                    continue
                ch_range = entry.get("chapter_range") or entry.get("range") or ""
                if ch_range and not self._chapter_in_range(current_chapter, ch_range):
                    continue
                agent = self.agents[char_name]
                agent.set_waypoint(
                    stage=entry.get("stage_name") or entry.get("stage") or "",
                    progress_pct=float(entry.get("progress_pct", 0.0)),
                )
                applied += 1
            except Exception as e:
                logger.debug(f"waypoint apply skipped: {e}")
        if applied:
            logger.info(f"[L2] Waypoint floor applied to {applied}/{len(self.agents)} characters")

    @staticmethod
    def _chapter_in_range(chapter: int, rng: str) -> bool:
        try:
            parts = str(rng).replace(" ", "").split("-")
            start = int(parts[0])
            end = int(parts[-1])
            return start <= chapter <= end
        except (ValueError, IndexError):
            return True

    def _is_event_thread_valid(self, event) -> bool:
        if not getattr(self, "threads", None):
            return True
        resolution_types = {"hy_sinh", "đảo_ngược", "giải_quyết"}
        if event.event_type not in resolution_types:
            return True
        involved = set(event.characters_involved or [])
        for th in self.threads:
            th_status = getattr(th, "status", "open")
            th_urgency = getattr(th, "urgency", 3)
            th_chars = set(
                getattr(th, "involved_characters", None)
                or getattr(th, "characters_involved", None)
                or []
            )
            if not (involved and th_chars and (involved & th_chars)):
                continue
            if th_status == "resolved":
                return False
            if th_status == "open" and th_urgency < 4:
                return False
        return True

    def _get_recent_posts(self, exclude_agent: str, limit: int = 5) -> str:
        """Lấy các bài viết gần đây của nhân vật khác, lọc theo tri thức nếu có."""
        try:
            if self.knowledge is not None:
                recent = self.knowledge.get_visible_posts(exclude_agent, self.all_posts, limit)
            else:
                recent = [
                    p for p in self.all_posts[-20:]
                    if p.agent_name != exclude_agent
                ][-limit:]
        except Exception as e:
            logger.debug(f"Knowledge filter lỗi, fallback: {e}")
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
                    f"LUÔN viết nội dung bằng tiếng Việt. "
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
                        + (f"\nTri thức: {self.knowledge.get_knowledge_context(name)}" if self.knowledge else "")
                    ),
                    recent_posts=recent_posts,
                ),
                temperature=self._intensity.get("temperature", 0.95),
            )

            post = AgentPost(
                agent_name=name,
                content=result.get("content") or "...",
                action_type=result.get("action_type") or "post",
                target=result.get("target") or "",
                sentiment=result.get("sentiment") or "trung lập",
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
        """Generate reactions from targeted characters (1 reaction layer).

        Migrated from ThreadPoolExecutor + as_completed to asyncio.gather +
        run_in_executor. _run_reaction() calls blocking LLM SDK; run_in_executor
        offloads each to the default thread pool concurrently.
        """
        targeted = {p.target: p for p in posts if p.target and p.target in self.agents}

        async def _gather() -> list[AgentPost]:
            loop = asyncio.get_running_loop()

            async def _one(target_name: str, triggering_post: AgentPost) -> AgentPost | None:
                if target_name == triggering_post.agent_name:
                    return None
                agent = self.agents[target_name]
                try:
                    return await asyncio.wait_for(
                        loop.run_in_executor(None, self._run_reaction, agent, triggering_post, round_num, context),
                        timeout=120,
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"Reaction from {target_name} timed out after 120s, skipping")
                    return None
                except Exception as e:
                    logger.warning(f"Reaction from {target_name} raised unexpected error: {e}")
                    return None

            results = await asyncio.gather(
                *[_one(name, post) for name, post in targeted.items()]
            )
            return [r for r in results if r is not None]

        return asyncio.run(_gather())

    def _run_reaction(self, agent: CharacterAgent, triggering_post: AgentPost, round_num: int, context: str) -> AgentPost | None:
        """Generate a reaction from agent to a triggering post."""
        try:
            result = self.llm.generate_json(
                system_prompt=(
                    f"Bạn là {agent.character.name}. Phản ứng với hành động của {triggering_post.agent_name}. "
                    f"Trạng thái: {agent.get_emotional_context()}. LUÔN viết bằng tiếng Việt. Trả về JSON."
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
                content=result.get("content") or "...",
                action_type=f"phản_ứng_{result.get('action_type') or 'post'}",
                target=triggering_post.agent_name,
                sentiment=result.get("sentiment") or "trung lập",
                round_number=round_num,
            )
        except Exception as e:
            logger.warning(f"Reaction from {agent.character.name} failed: {e}")
            return None

    def simulate_round(
        self, round_number: int, context: str, total_rounds: int = 5,
        progress_callback=None,
    ) -> list[AgentPost]:
        """Chạy một vòng mô phỏng - tất cả agents hành động song song.

        Migrated from ThreadPoolExecutor + as_completed to asyncio.gather +
        run_in_executor. _run_single_agent() calls a blocking LLM SDK; each
        coroutine is offloaded to the default thread pool via run_in_executor
        so the event loop is free between dispatches.

        NOTE: post-round state mutations (emotion, trust, memory) still happen
        sequentially after gather completes — they mutate shared agent state and
        must not be parallelised.
        """
        genre_hint = get_genre_escalation_prompt(context, round_number, total_rounds)
        round_context = f"{context} {genre_hint}".strip() if genre_hint else context
        agent_names = list(self.agents.keys())

        async def _run_round() -> list[tuple[str, AgentPost | None, dict]]:
            loop = asyncio.get_running_loop()

            async def _one(name: str) -> tuple[str, AgentPost | None, dict]:
                try:
                    post, metadata = await asyncio.wait_for(
                        loop.run_in_executor(
                            None, self._run_single_agent, name, round_number, round_context
                        ),
                        timeout=120,
                    )
                    return name, post, metadata
                except asyncio.TimeoutError:
                    logger.warning(f"Agent {name} timed out at round {round_number}, skipping")
                    return name, None, {}
                except Exception as e:
                    logger.warning(f"Agent {name} raised unexpected error at round {round_number}: {e}")
                    return name, None, {}

            return await asyncio.gather(*[_one(n) for n in self.agents])  # type: ignore[return-value]

        gathered = asyncio.run(_run_round())

        round_posts = []
        for idx, (name, post, metadata) in enumerate(gathered):
            if post is None:
                continue
            if progress_callback:
                progress_callback(
                    f"[Agent {idx + 1}/{len(agent_names)}] "
                    f"{name}: {post.action_type if post else 'skip'}"
                )
            round_posts.append(post)
            # Apply emotional + trust updates — sequential, safe (mutates agent state)
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
                # Update psychology pressure for the target (non-fatal)
                if self._psychology_engine and target_agent.psychology:
                    try:
                        self._psychology_engine.update_pressure(
                            target_agent.psychology,
                            post.action_type,
                            post.agent_name,
                        )
                    except Exception as e:
                        logger.debug(f"update_pressure lỗi: {e}")

        # Chuỗi phản ứng đa lớp: nhân vật bị nhắm đến phản ứng theo nhiều lớp
        import random
        all_reactions: list[AgentPost] = []
        reaction_input = round_posts
        for layer in range(self._intensity.get("reaction_depth", 1)):
            if layer > 0:
                skip_prob = 0.5 if layer == 1 else 0.7
                if random.random() < skip_prob:
                    break
            reactions = self._generate_reactions(reaction_input, round_number, context)
            if not reactions:
                break
            for post in reactions:
                agent = self.agents[post.agent_name]
                agent.posts.append(post)
                agent.add_memory(f"Vòng {round_number} [phản ứng L{layer + 1}]: {post.content[:100]}")
            all_reactions.extend(reactions)
            reaction_input = reactions  # lớp tiếp theo phản ứng với lớp này
        round_posts.extend(all_reactions)

        self.all_posts.extend(round_posts)

        # Kiểm tra tiết lộ bí mật sau vòng (non-fatal)
        if self.knowledge is not None:
            try:
                revelations = self.knowledge.check_revelation_triggers(
                    round_posts, round_number, all_posts=self.all_posts,
                )
                if revelations:
                    logger.info(f"Vòng {round_number}: {len(revelations)} bí mật được tiết lộ")
                    if self.causal_graph is not None:
                        try:
                            from pipeline.layer2_enhance.causal_chain import record_revelation_event
                            for rev in revelations:
                                new_id = record_revelation_event(
                                    self.causal_graph, self.knowledge,
                                    rev["fact_id"], rev["by"], rev["revealed_to"], round_number,
                                )
                                if new_id:
                                    try:
                                        fact = self.knowledge.items.get(rev["fact_id"])
                                        if fact and fact.reveal_log:
                                            fact.reveal_log[-1].event_id = new_id
                                    except Exception:
                                        pass
                        except Exception as e:
                            logger.debug(f"record_revelation_event wiring lỗi: {e}")
            except Exception as e:
                logger.debug(f"check_revelation_triggers lỗi: {e}")

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
            system_prompt="Bạn là đạo diễn kịch tính. LUÔN viết bằng tiếng Việt. Trả về JSON.",
            user_prompt=prompts.EVALUATE_DRAMA.format(
                actions=actions_text,
                relationships=rel_text,
            ),
        )

    def _check_escalation(self, round_num: int, total_rounds: int = 5, genre: str = "") -> list[EscalationPattern]:
        """Kiểm tra ngưỡng căng thẳng và trả về các mô hình leo thang được kích hoạt.

        Ngưỡng được điều chỉnh theo đường cong căng thẳng thể loại và cường độ kịch tính.
        """
        # Định hình đường cong căng thẳng: ưu tiên adaptive nếu có, fallback sang math curve
        try:
            if self.adaptive is not None:
                curve_modifier = self.adaptive.get_tension_modifier_actual(genre, round_num, total_rounds)
            else:
                position = round_num / max(1, total_rounds)
                curve_modifier = get_tension_modifier(genre, position)
        except Exception as e:
            logger.debug(f"Tension modifier lỗi, fallback: {e}")
            position = round_num / max(1, total_rounds)
            curve_modifier = get_tension_modifier(genre, position)

        triggered = []
        seen_types: set[str] = set()
        for rel in self.relationships:
            for ptype, cfg in ESCALATION_PATTERNS.items():
                if ptype in seen_types:
                    continue
                effective_trigger = (
                    cfg["trigger_tension"]
                    * curve_modifier
                    / self._intensity.get("escalation_scale", 1.0)
                )
                if rel.tension < effective_trigger:
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
                system_prompt="Bạn là đạo diễn kịch tính. LUÔN viết bằng tiếng Việt. Trả về JSON.",
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
                self.agents[c.strip()].get_drama_multiplier()
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
        drama_intensity: str = "cao",
        progress_callback=None,
        pacing_directive: str = "",
        arc_waypoints: list[dict] | None = None,
        threads: list | None = None,
        current_chapter: int = 1,
    ) -> SimulationResult:
        """Chạy toàn bộ mô phỏng và trả về kết quả."""

        def _log(msg):
            logger.info(msg)
            if progress_callback:
                progress_callback(msg)

        self._intensity = _get_intensity_config(drama_intensity)
        self.setup_agents(
            characters, relationships,
            arc_waypoints=arc_waypoints,
            threads=threads,
            current_chapter=current_chapter,
        )
        all_events: list[SimulationEvent] = []
        all_drama_scores: list[float] = []

        # Khởi tạo bộ điều khiển thích nghi (non-fatal)
        if _ADAPTIVE_AVAILABLE:
            try:
                self.adaptive = AdaptiveController(
                    self._intensity,
                    min_rounds=max(3, num_rounds - 2),
                    max_rounds=num_rounds + 3,
                    pacing_directive=pacing_directive,
                )
                logger.info("Đã khởi tạo AdaptiveController")
            except Exception as e:
                logger.warning(f"AdaptiveController thất bại: {e}")
                self.adaptive = None

        round_num = 0
        while True:
            round_num += 1
            # Kiểm tra nên tiếp tục không (adaptive hoặc fixed)
            if self.adaptive is not None:
                if round_num > 1 and not self.adaptive.should_continue(round_num):
                    _log(f"Drama đủ sau {round_num - 1} vòng, dừng sớm")
                    break
            else:
                if round_num > num_rounds:
                    break

            display_total = num_rounds if self.adaptive is None else (self.adaptive.max_rounds)
            _log(f"Vòng mô phỏng {round_num}/{display_total}...")

            # Cập nhật intensity từ adaptive nếu có
            if self.adaptive is not None:
                try:
                    self._intensity = self.adaptive.get_current_config()
                except Exception:
                    pass

            # Chạy vòng mô phỏng
            round_posts = self.simulate_round(
                round_num, genre, num_rounds, progress_callback=progress_callback,
            )

            # Đánh giá kịch tính
            evaluation = self.evaluate_drama(round_posts)
            round_drama = evaluation.get("overall_drama_score", 0.5)

            # Trích xuất sự kiện + liên kết nhân quả
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
                    if not self._is_event_thread_valid(event):
                        logger.debug(f"Event blocked by thread gate: {event.event_type} r{round_num}")
                        continue
                    all_events.append(event)
                    # Thêm vào đồ thị nhân quả (non-fatal)
                    if self.causal_graph is not None:
                        try:
                            self.causal_graph.add_event(event)
                        except Exception as e:
                            logger.debug(f"causal_graph.add_event lỗi: {e}")
                except (KeyError, ValueError, TypeError) as e:
                    logger.debug(f"Skipping malformed simulation event at round {round_num}: {e}")
                    continue

            all_drama_scores.append(round_drama)

            # Ghi lại vòng vào adaptive controller (non-fatal)
            if self.adaptive is not None:
                try:
                    self.adaptive.record_round(round_num, round_drama)
                except Exception as e:
                    logger.debug(f"adaptive.record_round lỗi: {e}")

            # Kiểm tra và áp dụng mô hình leo thang
            escalations = self._check_escalation(round_num, total_rounds=num_rounds, genre=genre)
            max_esc = self._intensity.get("max_escalations", 2)
            for pattern in escalations[:max_esc]:
                esc_event = self._apply_escalation(pattern, round_num, genre)
                if esc_event:
                    all_events.append(esc_event)
                    if self.causal_graph is not None:
                        try:
                            self.causal_graph.add_event(esc_event)
                        except Exception:
                            pass
                    _log(f"Escalation: {pattern.pattern_type} — {pattern.description}")

            # Cập nhật mối quan hệ
            for change in evaluation.get("relationship_changes", []):
                self._update_relationship(change)

            # Ghi lại arc cảm xúc sau mỗi vòng
            for agent in self.agents.values():
                agent.emotion.record_round(round_num)

        # Tạo gợi ý kịch tính
        _log("💡 Đang tạo gợi ý tăng cường kịch tính...")
        suggestions_result = self._generate_suggestions(genre)

        # Xây dựng dữ liệu quỹ đạo cảm xúc
        emotional_trajectories = {
            name: [m for _, m, _ in agent.emotion.arc_trajectory]
            for name, agent in self.agents.items()
        }

        # Xây dựng knowledge_state và causal_chains (non-fatal)
        knowledge_state: dict[str, list[str]] = {}
        causal_chains: list[list[str]] = []
        try:
            if self.knowledge is not None:
                for name in self.agents:
                    known = [
                        item.content for item in self.knowledge.items.values()
                        if name in item.known_by
                    ]
                    knowledge_state[name] = known
        except Exception as e:
            logger.debug(f"knowledge_state build lỗi: {e}")

        try:
            if self.causal_graph is not None:
                top_chains = self.causal_graph.get_top_chains(n=5)
                causal_chains = [[ev.event_id for ev in chain] for chain in top_chains]
        except Exception as e:
            logger.debug(f"causal_chains build lỗi: {e}")

        result = SimulationResult(
            events=all_events,
            updated_relationships=self.relationships,
            drama_suggestions=suggestions_result.get("suggestions", []),
            character_arcs=suggestions_result.get("character_arcs", {}),
            tension_map=suggestions_result.get("tension_points", {}),
            agent_posts=self.all_posts,
            emotional_trajectories=emotional_trajectories,
            knowledge_state=knowledge_state,
            causal_chains=causal_chains,
            actual_rounds=round_num,
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
            system_prompt="Bạn là cố vấn kịch bản. LUÔN viết bằng tiếng Việt. Trả về JSON.",
            user_prompt=prompts.DRAMA_SUGGESTIONS.format(
                simulation_summary=sim_summary,
                story_summary=story_summary,
            ),
        )
