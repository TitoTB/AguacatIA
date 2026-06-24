import html

from app import database


def can_use_skill(telegram_id: str, skill_key: str) -> tuple[bool, str]:
    user = database.get_user_with_level(telegram_id)
    skill = database.get_skill(skill_key)
    if not skill:
        return False, "Skill no encontrada."
    if not skill["enabled"]:
        return False, "Esta skill esta desactivada."
    if not user:
        database.ensure_user(telegram_id)
        user = database.get_user_with_level(telegram_id)
    if not user:
        return False, "Usuario no registrado."
    if user["is_blocked"]:
        return False, "Tu usuario esta bloqueado."
    if user["is_owner"]:
        return True, ""
    if int(user["level_rank"]) < int(skill["required_level_rank"]):
        return False, f"Esta skill requiere el nivel {html.escape(str(skill['required_level_name']))}."
    return True, ""
