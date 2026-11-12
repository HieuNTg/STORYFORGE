"""EmbeddingService on the real sentence-transformers / transformers / torch stack.

`tests/test_embedding_service.py` mocks SentenceTransformer. This file builds a
tiny randomly initialised BERT on disk and loads it through the same
`SentenceTransformer(model_id, device="cpu")` call the service makes, so a
breaking change in the sentence-transformers or transformers API (encode
kwargs, model loading, normalisation) fails here. Offline: nothing is
downloaded.
"""

from __future__ import annotations

import numpy as np
import pytest

st = pytest.importorskip("sentence_transformers")
transformers = pytest.importorskip("transformers")
torch = pytest.importorskip("torch")

from services.embedding_service import EmbeddingService, bytes_to_vec  # noqa: E402

try:  # sentence-transformers >= 5.7 moved the module classes
    from sentence_transformers.sentence_transformer.modules import Pooling, Transformer
except ImportError:  # pragma: no cover - older 5.x
    from sentence_transformers.models import Pooling, Transformer

WORDS = ["rồng", "lâu", "đài", "dòng", "sông", "làng", "chợ", "lụa", "the", "dragon", "castle", "river"]
HIDDEN = 32


@pytest.fixture(scope="module")
def tiny_model_dir(tmp_path_factory):
    root = tmp_path_factory.mktemp("tiny_st")
    bert_dir = root / "bert"
    bert_dir.mkdir()
    vocab = ["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]", *WORDS]
    (bert_dir / "vocab.txt").write_text("\n".join(vocab) + "\n", encoding="utf-8")

    torch.manual_seed(0)
    config = transformers.BertConfig(
        vocab_size=len(vocab),
        hidden_size=HIDDEN,
        num_hidden_layers=1,
        num_attention_heads=2,
        intermediate_size=64,
        max_position_embeddings=64,
    )
    transformers.BertModel(config).save_pretrained(bert_dir)
    transformers.BertTokenizerFast(vocab_file=str(bert_dir / "vocab.txt")).save_pretrained(bert_dir)

    word = Transformer(str(bert_dir), max_seq_length=32)
    dim_of = getattr(word, "get_embedding_dimension", None) or word.get_word_embedding_dimension
    pooling = Pooling(dim_of(), pooling_mode="mean")
    model_dir = root / "st"
    st.SentenceTransformer(modules=[word, pooling], device="cpu").save(
        str(model_dir), create_model_card=False  # the model card queries the Hub
    )
    return str(model_dir)


@pytest.fixture
def service(tiny_model_dir, monkeypatch):
    # conftest blocks real model loads by default; this test loads a local one.
    monkeypatch.delenv("STORYFORGE_DISABLE_REAL_EMBEDDINGS", raising=False)
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    return EmbeddingService(model_id=tiny_model_dir)


def test_loads_and_returns_normalised_float32(service):
    assert service.is_available()

    vecs = service.embed_texts(["the dragon castle", "dòng sông làng", "chợ lụa"])

    assert vecs.shape == (3, HIDDEN)
    assert vecs.dtype == np.float32
    assert vecs.flags["C_CONTIGUOUS"]
    np.testing.assert_allclose(np.linalg.norm(vecs, axis=1), 1.0, rtol=1e-5)


def test_bytes_api_round_trips_and_self_similarity_is_one(service):
    a = service.embed("the dragon castle")
    batch = service.embed_batch(["the dragon castle", "river"])

    assert len(a) == HIDDEN * 4
    np.testing.assert_allclose(bytes_to_vec(a), bytes_to_vec(batch[0]), rtol=1e-5, atol=1e-6)
    assert service.similarity(a, batch[0]) == pytest.approx(1.0, abs=1e-5)
    assert service.similarity(a, batch[1]) < 0.9999
