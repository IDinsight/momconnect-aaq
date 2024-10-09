"""This module contains utility functions for the question-answering module."""

import math
import pickle
from pathlib import Path
from typing import Any, Optional

from .schemas import QuerySearchResult


def get_context_string_from_search_results(
    search_results: dict[int, QuerySearchResult]
) -> str:
    """Get the context string from the retrieved content.

    Parameters
    ----------
    search_results
        The search results to get the context string from.

    Returns
    -------
    str
        The context string.
    """

    context_list = []
    for key, result in search_results.items():
        if not isinstance(result, QuerySearchResult):
            result = QuerySearchResult(**result)
        context_list.append(f"{key}. {result.title}\n{result.text}")
    context_string = "\n\n".join(context_list)
    return context_string


def calculate_avg_transition_prob(
    *,
    accepted_chars: str,
    line: str,
    log_prob_mat: list[list[Any]],
    ngram: int,
    pos: dict[str, int],
) -> float:
    """Calculate the average transition probability from `line` using `log_prob_mat`.

    NB: The exponentiation translates from log probs to probs.

    Parameters
    ----------
    accepted_chars
        The characters that are accepted in the gibberish model.
    line
        The line to calculate the average transition probability for.
    log_prob_mat
        The log probability matrix.
    ngram
        The n-gram size.
    pos
        The position of the characters in the accepted characters.

    Returns
    -------
    float
        The average transition probability.
    """

    assert ngram in [2, 3], "Only 2- and 3-grams are allowed for inference!"
    log_prob, transition_ct = 0.0, 0
    for indices in extract_ngrams(accepted_chars=accepted_chars, n=ngram, line=line):
        match ngram:
            case 3:
                x, y, z = indices[0], indices[1], indices[2]
                old_log_prob = log_prob_mat[pos[x]][pos[y]][pos[z]]
            case _:
                x, y = indices[0], indices[1]
                old_log_prob = log_prob_mat[pos[x]][pos[y]]
        assert isinstance(old_log_prob, float)
        log_prob += old_log_prob
        transition_ct += 1
    return math.exp(log_prob / (transition_ct or 1))


def extract_ngrams(*, accepted_chars: str, n: int, line: str) -> list[str]:
    """Return all n-grams from `line` after normalizing.

    Parameters
    ----------
    accepted_chars
        The characters that are accepted in the gibberish model.
    n
        The n-gram size.
    line
        The line to extract n-grams from.

    Returns
    -------
    list[str]
        The extracted n-grams.
    """

    # `filtered` is only the subset of characters from `accepted_chars`. This helps
    # keep the model relatively small by ignoring punctuation, infrequent symbols, etc.
    filtered = [c.lower() for c in line if c.lower() in accepted_chars]
    ngrams = []
    for start in range(0, len(filtered) - n + 1):
        ngrams.append("".join(filtered[start : start + n]))
    return ngrams


def is_gibberish(*, model_fp: Optional[str | Path] = None, text: str) -> bool:
    """Detect if the given text is gibberish.

    Parameters
    ----------
    model_fp
        The filepath to the gibberish model. If not specified, the default model path
        is the `gibberish_model.pkl` file in the same directory as this module.
    text
        The text to detect gibberish for.

    Returns
    -------
    bool
        Specifies whether the text is gibberish or not.

    Raises
    ------
    FileNotFoundError
        If the gibberish model file is not found at the specified path.
    """

    if not text:  # Assume empty string is gibberish
        return True
    model_fp = Path(model_fp or Path(__file__).parent / "gibberish_model.pkl")
    if not Path.is_file(model_fp):
        raise FileNotFoundError(f"Gibberish model file not found at: {model_fp}")
    gibberish_model = pickle.load(open(model_fp, "rb"))
    transition_prob = calculate_avg_transition_prob(
        accepted_chars=gibberish_model["accepted_chars"],
        line=text,
        log_prob_mat=gibberish_model["mat"],
        ngram=gibberish_model["ngram"],
        pos=gibberish_model["pos"],
    )
    return transition_prob <= gibberish_model["thresh"]
