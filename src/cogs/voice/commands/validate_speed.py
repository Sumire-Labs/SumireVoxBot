# src/cogs/voice/commands/validate_speed.py
def validate_speed(speed: float) -> bool:
    return 0.5 <= speed <= 2.0
