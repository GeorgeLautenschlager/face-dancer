"""Resolution spine — propose → contest? → apply, for both directions.

World-acts-on-character and character-acts-on-world both resolve through this loop.
An intent adjudicates into a propose_delta and then follows the same path.
"""

from face_dancer.resolution.apply import ApplyError, apply
from face_dancer.resolution.roll import roll

__all__ = ["ApplyError", "apply", "roll"]
