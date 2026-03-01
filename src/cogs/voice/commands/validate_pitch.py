# src/cogs/voice/commands/validate_pitch.py
def validate_pitch(pitch: float) -> bool:
    return -0.15 <= pitch <= 0.15
