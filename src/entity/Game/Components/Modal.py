from dataclasses import dataclass

import numpy as np

from src.entity.Game.Components import Button


@dataclass
class Modal:
    modal_title: str
    modal_body: np.ndarray
    modal_body_text: str | None = None
    confirm_button: Button = None
    cancel_button: Button = None