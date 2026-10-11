"""Result sentences: both common shapes are parsed, and unnamed methods are never extracted."""
from app.services.results import claims_from_text, dedupe, norm_method


def test_dataset_first_sentence_is_parsed():
    c = claims_from_text("On the Natural Questions test set, the RAG-Sequence model obtains 44.5 exact match.", 3)
    assert len(c) == 1
    assert (c[0].method, c[0].dataset, c[0].metric, c[0].value, c[0].page) == ("RAG-Sequence", "Natural Questions", "exact match", 44.5, 3)


def test_dataset_first_sentence_stops_before_trailing_clause():
    c = claims_from_text("On the Natural Questions test set, the RAG-Sequence model obtains 41.2 exact match under our replication.", 1)
    assert [(x.metric, x.value) for x in c] == [("exact match", 41.2)]


def test_method_first_sentence_still_parsed():
    c = claims_from_text("RAG-Sequence obtains 44.5 exact match on Natural Questions.", 1)
    assert [(x.method, x.dataset, x.value) for x in c] == [("RAG-Sequence", "Natural Questions", 44.5)]


def test_unnamed_methods_are_not_extracted():
    for s in (
        "The model achieves 44.5 exact match on Natural Questions.",
        "The replicated model reaches 41.2 exact match on Natural Questions.",
        "Our proposed method achieves 80.1 F1 on HotpotQA.",
    ):
        assert claims_from_text(s, 1) == [], s


def test_same_result_in_abstract_style_and_results_style_is_one_claim():
    a = claims_from_text("On the Natural Questions test set, the RAG-Sequence model obtains 44.5 exact match.", 3)
    b = claims_from_text("RAG-Sequence obtains 44.5 exact match on Natural Questions.", 1)
    assert len(dedupe(a + b)) == 1
    assert norm_method(a[0].method) == norm_method(b[0].method)
