import struct


SC_CONTROL_MSG_TYPE_INJECT_TOUCH_EVENT = 2

AMOTION_EVENT_ACTION_DOWN = 0
AMOTION_EVENT_ACTION_UP = 1
AMOTION_EVENT_ACTION_MOVE = 2

SC_POINTER_ID_GENERIC_FINGER = (1 << 64) - 2


def _float_to_u16fp(value: float) -> int:
    value = max(0.0, min(1.0, float(value)))
    return int(round(value * 0xFFFF))


def serialize_touch_event(
    x: int,
    y: int,
    width: int,
    height: int,
    action: int,
    pointer_id: int = SC_POINTER_ID_GENERIC_FINGER,
    pressure: float = 1.0,
    action_button: int = 0,
    buttons: int = 0,
) -> bytes:
    return struct.pack(
        ">BBQIIHHHII",
        SC_CONTROL_MSG_TYPE_INJECT_TOUCH_EVENT,
        int(action),
        int(pointer_id),
        int(x),
        int(y),
        int(width),
        int(height),
        _float_to_u16fp(pressure),
        int(action_button),
        int(buttons),
    )
