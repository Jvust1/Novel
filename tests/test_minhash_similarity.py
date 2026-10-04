from novel_ai.minhash_similarity import minhash_jaccard, minhash_overlap, minhash_signature


def test_signature_is_deterministic_and_bounded():
    signature = minhash_signature(["a", "b", "c"])
    assert signature == minhash_signature(["c", "b", "a"])
    assert len(signature) == 64
    assert 0.0 <= minhash_jaccard(signature, signature) <= 1.0


def test_overlap_rewards_shared_shingles():
    close = minhash_overlap({"a", "b", "c"}, {"a", "b", "d"})
    distant = minhash_overlap({"a", "b", "c"}, {"x", "y", "z"})
    assert close > distant


def test_empty_sets_have_a_valid_zero_or_collision_safe_sketch():
    assert minhash_jaccard(minhash_signature([]), minhash_signature([])) == 1.0
