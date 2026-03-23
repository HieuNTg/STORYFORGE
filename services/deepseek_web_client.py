"""DeepSeek web client — uses browser-captured credentials for free LLM access.

Makes HTTP requests to DeepSeek's internal web API using cookies and bearer
tokens captured by browser_auth.py. Handles PoW challenges, SSE streaming,
and session management.
"""

import hashlib
import json
import logging
import time
from typing import Generator, Optional

import requests

from services.browser_auth import BrowserAuth

logger = logging.getLogger(__name__)

# DeepSeek web API endpoints
BASE_URL = "https://chat.deepseek.com"
API_BASE = f"{BASE_URL}/api/v0"

# Available models on DeepSeek web
DEEPSEEK_WEB_MODELS = {
    "deepseek-chat": "deepseek_chat",
    "deepseek-reasoner": "deepseek_reasoner",
}


def _solve_pow(challenge: str, salt: str, difficulty: int, algorithm: str = "sha3_256") -> str:
    """Solve DeepSeek's proof-of-work challenge.

    Finds a nonce such that hash(challenge + nonce) has `difficulty` leading zeros.

    Args:
        challenge: Hex challenge string from server
        salt: Salt for hashing
        difficulty: Number of leading zero characters required
        algorithm: Hash algorithm (sha3_256 or sha256)

    Returns:
        Solution nonce as string
    """
    target_prefix = "0" * difficulty
    hash_fn = hashlib.sha3_256 if "sha3" in algorithm.lower() else hashlib.sha256
    nonce = 0

    while True:
        candidate = f"{challenge}{salt}{nonce}"
        digest = hash_fn(candidate.encode()).hexdigest()
        if digest.startswith(target_prefix):
            return str(nonce)
        nonce += 1
        # Safety: prevent infinite loops (max ~10M iterations)
        if nonce > 10_000_000:
            raise RuntimeError(
                f"PoW solver exceeded 10M iterations (difficulty={difficulty}). "
                "DeepSeek may have changed PoW algorithm."
            )


class DeepSeekWebClient:
    """HTTP client for DeepSeek's web API using browser-captured credentials.

    Usage:
        client = DeepSeekWebClient()
        # Streaming
        for chunk in client.chat_completion(messages, stream=True):
            print(chunk, end="")
        # Non-streaming
        response = client.chat_completion_sync(messages)
    """

    def __init__(self):
        self._session = requests.Session()
        self._chat_session_id: Optional[str] = None
        self._credentials: Optional[dict] = None
        self._load_credentials()

    def _load_credentials(self):
        """Load credentials from browser auth storage."""
        auth = BrowserAuth()
        self._credentials = auth.get_credentials("deepseek-web")
        if self._credentials:
            self._session.headers.update({
                "Cookie": self._credentials["cookies"],
                "User-Agent": self._credentials.get("user_agent", ""),
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
                "X-Client-Locale": "en_US",
            })
            if self._credentials.get("bearer"):
                self._session.headers["Authorization"] = f"Bearer {self._credentials['bearer']}"

    def is_ready(self) -> bool:
        """Check if client has valid credentials loaded."""
        return self._credentials is not None and bool(self._credentials.get("cookies"))

    def _create_chat_session(self) -> Optional[str]:
        """Create a new chat session on DeepSeek web.

        Returns:
            chat_session_id or None on failure
        """
        try:
            resp = self._session.post(
                f"{API_BASE}/chat_session/create",
                json={"agent": "chat"},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                session_id = data.get("data", {}).get("biz_data", {}).get("id")
                if not session_id:
                    # Try alternate response structure
                    session_id = data.get("data", {}).get("id")
                self._chat_session_id = session_id
                return session_id
            elif resp.status_code == 401:
                logger.warning("DeepSeek session expired (401). Re-auth needed.")
                return None
            else:
                logger.error(f"Create session failed: {resp.status_code} {resp.text[:200]}")
                return None
        except Exception as e:
            logger.error(f"Create session error: {e}")
            return None

    def _handle_pow(self, pow_data: dict) -> Optional[dict]:
        """Solve a proof-of-work challenge from the server.

        Args:
            pow_data: Challenge dict with algorithm, challenge, difficulty, salt

        Returns:
            Solution dict for inclusion in request, or None
        """
        if not pow_data:
            return None

        algorithm = pow_data.get("algorithm", "DeepSeekHashV1")
        challenge = pow_data.get("challenge", "")
        difficulty = pow_data.get("difficulty", 3)
        salt = pow_data.get("salt", "")

        logger.debug(f"Solving PoW: difficulty={difficulty}, algo={algorithm}")
        start = time.time()
        nonce = _solve_pow(challenge, salt, difficulty, algorithm)
        elapsed = time.time() - start
        logger.debug(f"PoW solved in {elapsed:.2f}s (nonce={nonce})")

        return {
            "algorithm": algorithm,
            "challenge": challenge,
            "salt": salt,
            "answer": nonce,
            "signature": pow_data.get("signature", ""),
            "target_path": pow_data.get("target_path", ""),
        }

    def _get_pow_challenge(self) -> Optional[dict]:
        """Fetch a PoW challenge from DeepSeek.

        Returns:
            Challenge dict or None if no PoW required
        """
        try:
            resp = self._session.post(
                f"{API_BASE}/chat/create_pow_challenge",
                json={"target_path": "/api/v0/chat/completion"},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("data", {}).get("biz_data", {}).get("challenge")
            return None
        except Exception:
            return None

    def chat_completion(
        self,
        messages: list[dict],
        model: str = "deepseek-chat",
        temperature: float = 0.8,
        stream: bool = True,
    ) -> Generator[str, None, None]:
        """Send chat completion request with SSE streaming.

        Args:
            messages: OpenAI-format messages list
            model: Model name (deepseek-chat or deepseek-reasoner)
            temperature: Sampling temperature
            stream: Whether to stream (always True for this method)

        Yields:
            Content text chunks
        """
        if not self.is_ready():
            raise RuntimeError("DeepSeek web credentials not loaded. Run browser auth first.")

        # Create chat session if needed
        if not self._chat_session_id:
            session_id = self._create_chat_session()
            if not session_id:
                raise RuntimeError("Failed to create DeepSeek chat session. Re-auth may be needed.")

        # Get and solve PoW challenge
        pow_challenge = self._get_pow_challenge()
        pow_solution = self._handle_pow(pow_challenge) if pow_challenge else None

        # Build request payload
        model_class = DEEPSEEK_WEB_MODELS.get(model, "deepseek_chat")

        # Convert messages to DeepSeek format (last user message as prompt)
        prompt = ""
        for msg in messages:
            if msg["role"] == "system":
                prompt += f"[System] {msg['content']}\n\n"
            elif msg["role"] == "user":
                prompt += msg["content"]

        payload = {
            "chat_session_id": self._chat_session_id,
            "parent_message_id": None,
            "prompt": prompt,
            "ref_file_ids": [],
            "thinking_enabled": model == "deepseek-reasoner",
            "search_enabled": False,
            "model_class": model_class,
            "temperature": temperature,
        }

        if pow_solution:
            payload["pow"] = pow_solution

        try:
            resp = self._session.post(
                f"{API_BASE}/chat/completion",
                json=payload,
                stream=True,
                timeout=120,
            )

            if resp.status_code == 401:
                self._credentials = None
                raise RuntimeError("DeepSeek session expired (401). Hay dang nhap lai.")

            if resp.status_code == 429:
                raise RuntimeError("DeepSeek rate limit. Thu lai sau vai giay.")

            if resp.status_code != 200:
                raise RuntimeError(f"DeepSeek API error: {resp.status_code} {resp.text[:200]}")

            # Parse SSE stream
            for line in resp.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:]  # Remove "data: " prefix
                if data_str == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    # Extract content from DeepSeek SSE format
                    choices = data.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                except json.JSONDecodeError:
                    continue

        except requests.exceptions.ConnectionError as e:
            raise RuntimeError(f"Khong the ket noi DeepSeek: {e}")

    def chat_completion_sync(
        self,
        messages: list[dict],
        model: str = "deepseek-chat",
        temperature: float = 0.8,
    ) -> str:
        """Non-streaming chat completion. Returns full response text."""
        chunks = []
        for chunk in self.chat_completion(messages, model, temperature, stream=True):
            chunks.append(chunk)
        return "".join(chunks)

    def check_connection(self) -> tuple[bool, str]:
        """Test if credentials are valid by calling a lightweight endpoint."""
        if not self.is_ready():
            return False, "Chua dang nhap. Hay dang nhap qua trinh duyet truoc."

        try:
            resp = self._session.get(f"{API_BASE}/users/current", timeout=10)
            if resp.status_code == 200:
                return True, "Ket noi DeepSeek Web thanh cong!"
            elif resp.status_code == 401:
                return False, "Session het han. Hay dang nhap lai."
            else:
                return False, f"Loi: HTTP {resp.status_code}"
        except Exception as e:
            return False, f"Loi ket noi: {e}"

    def refresh_credentials(self):
        """Reload credentials from storage (after re-auth)."""
        self._credentials = None
        self._chat_session_id = None
        self._session.headers.clear()
        self._load_credentials()
