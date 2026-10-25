import uuid

import pytest

from app.retrieval.service import reciprocal_rank_fusion

A, B, C, D = (uuid.uuid4() for _ in range(4))


def test_item_ranked_well_by_both_lists_wins():
    fused = reciprocal_rank_fusion([[A, B, C], [B, A, D]], k=60)

    # A and B both appear twice (ranks 1+2), so they tie and lead; C and D appear once.
    assert {fused[0][0], fused[1][0]} == {A, B}
    assert fused[0][1] == pytest.approx(1 / 61 + 1 / 62)
    assert {item for item, _ in fused[2:]} == {C, D}


def test_item_found_by_only_one_list_still_counts():
    fused = dict(reciprocal_rank_fusion([[A], [B]], k=60))

    assert fused[A] == pytest.approx(1 / 61)
    assert fused[B] == pytest.approx(1 / 61)


def test_consistent_middle_ranks_can_beat_a_single_first_place():
    # C is 2nd in both lists; A is 1st in one list only.
    fused = reciprocal_rank_fusion([[A, C], [D, C]], k=60)

    assert fused[0][0] == C


def test_empty_rankings():
    assert reciprocal_rank_fusion([[], []]) == []
