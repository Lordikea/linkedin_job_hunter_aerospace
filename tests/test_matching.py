from job_hunter.matching import matches
from job_hunter.text import fold, tokenize


def test_fold_handles_turkish_casing():
    assert fold("İSTANBUL") == "istanbul"
    assert fold("Finansal Raporlama") == "finansal raporlama"


def test_tokenize_normalizes_punctuation():
    assert tokenize("FP&A") == tokenize("FP & A") == " fp a "


def test_any_mode_needs_one_keyword():
    assert matches("Kıdemli Finans Uzmanı", ["finans", "FP&A", "IFRS"]) == ["finans"]


def test_any_mode_reports_every_hit_in_config_order():
    assert matches("IFRS & FP&A Analisti", ["finans", "FP&A", "IFRS"]) == ["FP&A", "IFRS"]


def test_all_mode_requires_every_keyword():
    keywords = ["finans", "IFRS"]
    assert matches("Finans Müdürü", keywords, mode="all") == []
    assert matches("Finans / IFRS Raporlama", keywords, mode="all") == keywords


def test_exclude_vetoes_the_posting():
    assert matches("Finans Stajyeri", ["finans"], exclude=["stajyer"]) == []


def test_matching_is_case_and_accent_insensitive():
    assert matches("FİNANS UZMANI", ["finans"]) == ["finans"]


def test_keyword_matches_a_longer_word_it_starts():
    assert matches("Finansal Raporlama Uzmanı", ["finans"]) == ["finans"]


def test_partial_word_does_not_leak_across_tokens():
    assert matches("Difrsavunma Uzmanı", ["IFRS"]) == []


def test_short_keywords_must_match_a_whole_word():
    assert matches("IT Yöneticisi", ["IT"]) == ["IT"]
    assert matches("Kıdemli IT Uzmanı", ["IT"]) == ["IT"]
    assert matches("İthalat Uzmanı", ["IT"]) == []
    assert matches("İtfaiye Eri", ["IT"]) == []


def test_short_keyword_matches_inside_punctuation():
    assert matches("Bilgi İşlem (IT)", ["IT"]) == ["IT"]


def test_longer_keywords_still_allow_a_suffix():
    assert matches("Finansal Raporlama", ["finans"]) == ["finans"]
    assert matches("Sistemleri Uzmanı", ["sistem"]) == ["sistem"]


def test_multi_word_keyword_matches_the_whole_phrase_only():
    keyword = ["Bilgi Sistemleri Yöneticisi"]
    assert matches("Kıdemli Bilgi Sistemleri Yöneticisi", keyword) == keyword
    assert matches("Bilgi Sistemleri Uzmanı", keyword) == []
    assert matches("Bilgi Teknolojileri Yöneticisi", keyword) == []


def test_french_avionics_titles_match_english_search_keywords():
    keywords = ["Avionics", "Avionics Systems", "Aircraft Systems Engineer"]
    assert matches("Ingénieur système avionique H/F", keywords) == ["Avionics", "Aircraft Systems Engineer"]
    assert matches("Ingénieur Études Systèmes Avioniques F/H", keywords) == [
        "Avionics", "Avionics Systems", "Aircraft Systems Engineer"
    ]


def test_french_flight_controls_title_matches():
    assert matches("Ingénieur spécialiste systèmes de commandes de vol", ["Flight Controls"]) == ["Flight Controls"]


def test_french_customer_support_title_matches():
    assert matches("Ingénieur support aéronautique", ["Aircraft Support Engineer"]) == ["Aircraft Support Engineer"]


def test_exclusion_still_applies_to_french_alias_matches():
    assert matches("Ingénieur système avionique - stage", ["Avionics"], exclude=["stage"]) == []
