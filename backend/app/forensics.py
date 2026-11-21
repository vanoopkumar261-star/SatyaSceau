"""OPTIONAL stretch: image risk signals.  Owner: Pile 2 (Vision).

Only after everything else is merged and green, and Anoop says go.
Adds a risk_score 0-1 plus reasons; it NEVER decides the verdict. No external AI APIs.
"""


def assess(image_bytes: bytes) -> tuple[float, list[str]]:
    """TODO(Pile 2, stretch): colour-uniformity patch detection, layout sanity."""
    return 0.0, []
