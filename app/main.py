from contextlib import asynccontextmanager
import ipaddress

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import bdevices_taxonomies
from app import database
from app.bot import TelegramBotService
from app.config import APP_NAME, APP_VERSION
from app.security import hash_password, new_secret, sign_session, verify_password, verify_session


bot_service = TelegramBotService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio

    database.init_db()
    bot_service.sync_skills()
    app.state.bot_supervisor = asyncio.create_task(bot_service.supervise())
    app.state.bdevices_taxonomies_syncer = asyncio.create_task(bdevices_taxonomies.periodic_sync())
    yield
    await bot_service.stop()
    app.state.bot_supervisor.cancel()
    app.state.bdevices_taxonomies_syncer.cancel()


app = FastAPI(title=APP_NAME, version=APP_VERSION, lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
templates.env.globals["app_name"] = APP_NAME
templates.env.globals["app_version"] = APP_VERSION


@app.middleware("http")
async def local_admin_only(request: Request, call_next):
    host = request.client.host if request.client else ""
    if host and not _is_local_network(host):
        return PlainTextResponse("Panel disponible solo en red local.", status_code=403)
    return await call_next(request)


def _is_local_network(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return host in {"localhost", "testclient"} or host.endswith(".local")
    return ip.is_loopback or ip.is_private or ip.is_link_local


def require_admin(request: Request) -> None:
    if not database.admin_is_configured():
        raise HTTPException(status_code=307, headers={"Location": "/setup"})
    secret = database.get_setting("admin_session_secret")
    token = request.cookies.get("aguacatia_session", "")
    if not secret or not verify_session(secret, token):
        raise HTTPException(status_code=307, headers={"Location": "/login"})


def redirect(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=303)


@app.get("/setup")
def setup_form(request: Request):
    if database.admin_is_configured():
        return redirect("/login")
    return templates.TemplateResponse("setup.html", {"request": request, "error": ""})


@app.post("/setup")
def setup(request: Request, password: str = Form(""), confirm_password: str = Form("")):
    if database.admin_is_configured():
        return redirect("/login")
    if len(password) < 8:
        return templates.TemplateResponse(
            "setup.html",
            {"request": request, "error": "La contrasena debe tener al menos 8 caracteres."},
            status_code=400,
        )
    if password != confirm_password:
        return templates.TemplateResponse(
            "setup.html",
            {"request": request, "error": "Las contrasenas no coinciden."},
            status_code=400,
        )
    database.save_setting("admin_password_hash", hash_password(password), is_secret=True)
    database.save_setting("admin_session_secret", new_secret(), is_secret=True)
    return redirect("/login")


@app.get("/login")
def login_form(request: Request):
    if not database.admin_is_configured():
        return redirect("/setup")
    return templates.TemplateResponse("login.html", {"request": request, "error": ""})


@app.post("/login")
def login(request: Request, password: str = Form("")):
    expected = database.get_setting("admin_password_hash", "")
    if not verify_password(password, expected):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Contrasena incorrecta."}, status_code=401)
    secret = database.get_setting("admin_session_secret")
    if not secret:
        secret = new_secret()
        database.save_setting("admin_session_secret", secret, is_secret=True)
    response = redirect("/")
    response.set_cookie("aguacatia_session", sign_session(secret), httponly=True, samesite="lax", max_age=60 * 60 * 24 * 14)
    return response


@app.post("/logout")
def logout():
    response = redirect("/login")
    response.delete_cookie("aguacatia_session")
    return response


@app.get("/")
def dashboard(request: Request, _: None = Depends(require_admin)):
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "bot_running": bot_service.is_running,
            "settings": database.settings_map(include_secrets=False),
            "user_count": len(database.list_users()),
            "skill_count": len(database.list_skills()),
            "logs": database.recent_logs(20),
        },
    )


@app.get("/settings")
def settings_page(request: Request, _: None = Depends(require_admin)):
    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "settings": database.settings_map(include_secrets=False),
            "bot_running": bot_service.is_running,
            "bdevices_taxonomies_summary": database.bdevices_taxonomies_summary(),
        },
    )


@app.get("/skills")
def skills_page(request: Request, _: None = Depends(require_admin)):
    return templates.TemplateResponse(
        "skills.html",
        {
            "request": request,
            "skills": database.list_skills(),
        },
    )


@app.get("/skills/{skill_key}")
def skill_detail_page(skill_key: str, request: Request, _: None = Depends(require_admin)):
    skill = database.get_skill(skill_key)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill no encontrada")
    return templates.TemplateResponse(
        "skill_detail.html",
        {
            "request": request,
            "skill": skill,
            "levels": database.list_levels(),
            "messages": database.list_skill_messages().get(skill_key, []),
            "triggers_text": database.skill_triggers_text(skill_key),
            "variables": bot_service.registry.get(skill_key).definition.variables if bot_service.registry.get(skill_key) else {},
        },
    )


@app.get("/users")
def users_page(request: Request, _: None = Depends(require_admin)):
    return templates.TemplateResponse(
        "users.html",
        {
            "request": request,
            "users": database.list_users(),
            "levels": database.list_levels(),
        },
    )


@app.get("/levels")
def levels_page(request: Request, _: None = Depends(require_admin)):
    return templates.TemplateResponse("levels.html", {"request": request, "levels": database.list_levels()})


@app.get("/logs")
def logs_page(request: Request, _: None = Depends(require_admin)):
    return templates.TemplateResponse("logs.html", {"request": request, "logs": database.recent_logs(100)})


@app.get("/improvement")
def improvement_page(
    request: Request,
    _: None = Depends(require_admin),
    status: str = "pending",
    skill_key: str = "",
):
    return templates.TemplateResponse(
        "improvement.html",
        {
            "request": request,
            "events": database.list_improvement_events(status=status, skill_key=skill_key),
            "summary": database.improvement_event_summary(),
            "status": status,
            "skill_key": skill_key,
            "skills": database.list_skills(),
        },
    )


@app.post("/improvement/{event_id}/status")
def update_improvement_status(
    event_id: int,
    _: None = Depends(require_admin),
    status: str = Form("pending"),
    notes: str = Form(""),
    current_status: str = Form("pending"),
    current_skill_key: str = Form(""),
):
    database.update_improvement_event(event_id, status, notes)
    suffix = f"?status={current_status}"
    if current_skill_key:
        suffix += f"&skill_key={current_skill_key}"
    return redirect(f"/improvement{suffix}")


@app.post("/settings")
def save_settings(
    _: None = Depends(require_admin),
    bot_enabled: str | None = Form(None),
    telegram_bot_token: str = Form(""),
    owner_telegram_id: str = Form(""),
    bdevices_search_url: str = Form(""),
    bdevices_taxonomies_url: str = Form(""),
    bdevices_device_url_template: str = Form(""),
    bdevices_agent_token: str = Form(""),
    bdevices_ai_query_enabled: str | None = Form(None),
    ai_provider: str = Form("ollama"),
    ollama_base_url: str = Form(""),
    ollama_model: str = Form(""),
    openai_api_key: str = Form(""),
    gemini_api_key: str = Form(""),
):
    database.save_setting("bot_enabled", "1" if bot_enabled else "0")
    database.save_setting("owner_telegram_id", owner_telegram_id.strip())
    database.save_setting("bdevices_search_url", bdevices_search_url.strip())
    database.save_setting("bdevices_taxonomies_url", bdevices_taxonomies_url.strip())
    database.save_setting("bdevices_device_url_template", bdevices_device_url_template.strip())
    database.save_setting("bdevices_ai_query_enabled", "1" if bdevices_ai_query_enabled else "0")
    database.save_setting("ai_provider", ai_provider.strip() or "ollama")
    database.save_setting("ollama_base_url", ollama_base_url.strip())
    database.save_setting("ollama_model", ollama_model.strip())
    for key, value in {
        "telegram_bot_token": telegram_bot_token,
        "bdevices_agent_token": bdevices_agent_token,
        "openai_api_key": openai_api_key,
        "gemini_api_key": gemini_api_key,
    }.items():
        if value.strip():
            database.save_setting(key, value.strip(), is_secret=True)
    if owner_telegram_id.strip():
        database.upsert_user(owner_telegram_id.strip(), "Owner", is_owner=True)
    return redirect("/settings")


@app.post("/settings/bdevices-taxonomies/sync")
async def sync_bdevices_taxonomies_now(_: None = Depends(require_admin)):
    await bdevices_taxonomies.sync_once()
    return redirect("/settings")


@app.post("/users")
def save_user(
    _: None = Depends(require_admin),
    telegram_id: str = Form(""),
    display_name: str = Form(""),
    level_id: int = Form(...),
    is_owner: str | None = Form(None),
    is_blocked: str | None = Form(None),
):
    if telegram_id.strip():
        database.upsert_user(telegram_id.strip(), display_name, level_id, bool(is_owner), bool(is_blocked))
        if is_owner:
            database.save_setting("owner_telegram_id", telegram_id.strip())
    return redirect("/users")


@app.post("/levels")
def create_level(_: None = Depends(require_admin), name: str = Form(""), slug: str = Form(""), rank: int = Form(...)):
    if name.strip() and slug.strip():
        database.create_level(name, slug, rank)
    return redirect("/levels")


@app.post("/skills/save")
async def save_skills(request: Request, _: None = Depends(require_admin)):
    form = await request.form()
    for skill in database.list_skills():
        key = skill["key"]
        enabled = form.get(f"enabled_{key}") == "on"
        command = _clean_command(str(form.get(f"command_{key}", skill["command"]))) if skill["command"] else ""
        required_level_id = int(form.get(f"level_{key}", skill["required_level_id"]))
        database.update_skill_config(key, command, enabled, required_level_id)
        for message in database.list_skill_messages().get(key, []):
            database.update_skill_message(key, message["message_key"], str(form.get(f"message_{key}_{message['message_key']}", "")))
    return redirect("/skills")


@app.post("/skills/{skill_key}/save")
async def save_skill_detail(skill_key: str, request: Request, _: None = Depends(require_admin)):
    skill = database.get_skill(skill_key)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill no encontrada")
    form = await request.form()
    enabled = form.get("enabled") == "on"
    command = _clean_command(str(form.get("command", skill["command"]))) if skill["command"] else ""
    required_level_id = int(form.get("required_level_id", skill["required_level_id"]))
    database.update_skill_config(skill_key, command, enabled, required_level_id)
    database.replace_skill_triggers(skill_key, str(form.get("triggers", "")))
    for message in database.list_skill_messages().get(skill_key, []):
        database.update_skill_message(skill_key, message["message_key"], str(form.get(f"message_{message['message_key']}", "")))
    return redirect(f"/skills/{skill_key}")


def _clean_command(value: str) -> str:
    cleaned = "".join(char for char in value.strip().lower().lstrip("/") if char.isalnum() or char == "_")
    return (cleaned or "comando")[:32]


@app.get("/health")
def health():
    return {"ok": True, "app": APP_NAME, "version": APP_VERSION, "bot_running": bot_service.is_running}
