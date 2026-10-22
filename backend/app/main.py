import json
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.database import Base, SessionLocal, engine, get_db
from backend.app.models import AuditLog, ColonizationRequest, PoliticalAction, State, Territory, User, now_utc
from backend.app.security import admin_token_expiry, current_user, require_admin_token, require_roles
from backend.app.services import (
    action_to_dict,
    audit,
    create_state_link_code,
    create_map_state,
    create_link_code,
    json_loads,
    delete_state_with_territories,
    polygon_area,
    request_to_dict,
    save_map_upload,
    save_territory_version,
    seed_database,
    setting,
    set_setting,
    state_to_dict,
    territory_to_dict,
    user_to_dict,
    validate_points,
)


class PointIn(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class StateIn(BaseModel):
    name: str
    short_name: str
    description: str = ""
    color: str = "#4A90E2"
    leader_id: int
    capital_point: PointIn = PointIn(x=0.5, y=0.5)
    government_type: str = "republic"


class TerritoryIn(BaseModel):
    name: str
    state_id: int | None = None
    type: str = "neutral"
    status: str = "neutral"
    color: str = "#8A9A5B"
    points: list[PointIn]
    reason: str = "manual edit"


class ColonizationIn(BaseModel):
    state_id: int
    territory_id: int
    point: PointIn | None = None


class DecisionIn(BaseModel):
    reason: str = ""


class AdminLoginIn(BaseModel):
    username: str
    password: str


class StateLinkIn(BaseModel):
    username: str
    state_name: str
    short_name: str
    capital_point: PointIn
    color: str = "#4A90E2"
    description: str = ""


class MapStateIn(BaseModel):
    name: str
    short_name: str = ""
    color: str = "#4A90E2"
    capital_point: PointIn
    description: str = ""


class StateCapitalIn(BaseModel):
    capital_point: PointIn


def startup() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_sample_map()
    with SessionLocal() as db:
        seed_database(db)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    startup()
    yield


app = FastAPI(title="Polis Map", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173", settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

settings.map_dir.mkdir(parents=True, exist_ok=True)
settings.data_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static/maps", StaticFiles(directory=settings.map_dir), name="maps")


def ensure_sample_map() -> None:
    path = settings.map_dir / "sample-world.svg"
    if path.exists():
        return
    path.write_text(
        """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 1000">
<defs>
<linearGradient id="sea" x1="0" x2="1" y1="0" y2="1"><stop stop-color="#d7e7ee"/><stop offset="1" stop-color="#8fb4c5"/></linearGradient>
<filter id="grain"><feTurbulence type="fractalNoise" baseFrequency=".9" numOctaves="2" stitchTiles="stitch"/><feColorMatrix type="saturate" values=".15"/><feBlend mode="multiply" in2="SourceGraphic"/></filter>
</defs>
<rect width="1600" height="1000" fill="url(#sea)"/>
<path d="M135 225 C260 105 520 115 690 232 C810 315 765 510 625 602 C455 713 230 660 122 510 C55 415 48 310 135 225Z" fill="#d7d1a6" stroke="#5a675a" stroke-width="8"/>
<path d="M920 250 C1095 130 1375 182 1482 352 C1580 510 1460 750 1240 790 C1018 831 837 678 805 502 C785 390 830 314 920 250Z" fill="#c9d0a2" stroke="#5a675a" stroke-width="8"/>
<path d="M540 720 C690 650 865 675 940 795 C1004 900 890 972 705 952 C575 938 455 820 540 720Z" fill="#e0c794" stroke="#5a675a" stroke-width="7"/>
<path d="M0 870 C270 810 390 980 650 900 C900 820 1130 915 1600 840 L1600 1000 L0 1000Z" fill="#587f72" opacity=".18"/>
<g fill="none" stroke="#ffffff" stroke-opacity=".35" stroke-width="2">
<path d="M0 190 C320 250 525 130 800 210 C1070 290 1250 230 1600 310"/>
<path d="M0 430 C300 490 510 390 795 455 C1110 528 1320 465 1600 545"/>
<path d="M0 655 C370 715 520 620 810 690 C1125 767 1320 690 1600 760"/>
</g>
<text x="62" y="930" fill="#233035" font-family="Georgia,serif" font-size="34">Polis Map base map</text>
</svg>""",
        encoding="utf-8",
    )


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/bootstrap")
def bootstrap(db: Session = Depends(get_db)) -> dict[str, Any]:
    return {
        "settings": {
            "frontend_url": settings.frontend_url,
            "telegram_enabled": bool(settings.telegram_bot_token),
        },
    }


@app.post("/api/admin/login")
def admin_login(payload: AdminLoginIn, db: Session = Depends(get_db)) -> dict[str, str]:
    if payload.username != settings.admin_username or payload.password != settings.admin_password:
        raise HTTPException(status_code=401, detail="Invalid admin credentials")
    token = secrets.token_urlsafe(32)
    expires_at = admin_token_expiry()
    set_setting(db, f"admin_token:{token}", expires_at.isoformat())
    audit(db, 1, "admin_login", "user", 1, new={"expires_at": expires_at.isoformat()})
    db.commit()
    return {"token": token, "expires_at": expires_at.isoformat()}


@app.get("/api/admin/bootstrap")
def admin_bootstrap(
    _admin: User = Depends(require_admin_token),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return {
        "users": [user_to_dict(user) for user in db.scalars(select(User).order_by(User.id))],
        "states": [state_to_dict(state) for state in db.scalars(select(State).order_by(State.id))],
    }


@app.post("/api/admin/states/link-code")
def admin_state_link_code(
    payload: StateLinkIn,
    admin: User = Depends(require_admin_token),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return create_state_link_code(
        db,
        admin,
        payload.username,
        payload.state_name,
        payload.short_name,
        payload.capital_point.model_dump(),
        payload.color,
        payload.description,
    )


@app.post("/api/admin/states/map-state")
def admin_map_state(
    payload: MapStateIn,
    admin: User = Depends(require_admin_token),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    short_name = payload.short_name.strip() or payload.name.strip()[:3].upper()
    return create_map_state(
        db,
        admin,
        payload.name,
        short_name,
        payload.color,
        payload.capital_point.model_dump(),
        payload.description,
    )


@app.patch("/api/admin/states/{state_id}/capital")
def admin_update_state_capital(
    state_id: int,
    payload: StateCapitalIn,
    admin: User = Depends(require_admin_token),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    state = db.get(State, state_id)
    if not state:
        raise HTTPException(status_code=404, detail="State not found")
    old = state_to_dict(state)
    state.capital_x = payload.capital_point.x
    state.capital_y = payload.capital_point.y
    state.updated_at = now_utc()
    new = state_to_dict(state)
    audit(db, admin.id, "state_capital_updated", "state", state.id, old=old, new=new, reason="admin move state point")
    db.commit()
    return new


@app.delete("/api/admin/states/{state_id}")
def admin_delete_state(
    state_id: int,
    admin: User = Depends(require_admin_token),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return delete_state_with_territories(db, admin, state_id)


@app.get("/api/me")
def me(user: User = Depends(current_user)) -> dict[str, Any]:
    return user_to_dict(user)


@app.post("/api/link-code")
def link_code(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, str]:
    return {"code": create_link_code(db, user)}


@app.get("/api/map")
def get_map(db: Session = Depends(get_db)) -> dict[str, Any]:
    territories = [territory_to_dict(row) for row in db.scalars(select(Territory).order_by(Territory.id))]
    states = [state_to_dict(row) for row in db.scalars(select(State).order_by(State.id))]
    return {
        "image_url": setting(db, "map_image_url", "/static/maps/sample-world.svg"),
        "width": int(setting(db, "map_width", "1600")),
        "height": int(setting(db, "map_height", "1000")),
        "states": states,
        "territories": territories,
        "objects": [],
    }


@app.post("/api/map/upload")
async def upload_map(
    file: UploadFile = File(...),
    user: User = Depends(require_admin_token),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    require_roles(user, {"mapper"})
    return await save_map_upload(db, user, file)


@app.get("/api/states")
def list_states(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [state_to_dict(row) for row in db.scalars(select(State).order_by(State.id))]


@app.post("/api/states")
def create_state(payload: StateIn, user: User = Depends(require_admin_token), db: Session = Depends(get_db)) -> dict[str, Any]:
    require_roles(user, {"leader", "moderator"})
    leader = db.get(User, payload.leader_id)
    if not leader:
        raise HTTPException(status_code=404, detail="Leader not found")
    state = State(
        name=payload.name,
        short_name=payload.short_name,
        description=payload.description,
        color=payload.color,
        leader_id=payload.leader_id,
        capital_x=payload.capital_point.x,
        capital_y=payload.capital_point.y,
        government_type=payload.government_type,
        status="active" if user.role in {"admin", "moderator"} else "pending",
    )
    db.add(state)
    db.flush()
    audit(db, user.id, "state_created", "state", state.id, new=state_to_dict(state))
    db.commit()
    db.refresh(state)
    return state_to_dict(state)


@app.get("/api/territories")
def list_territories(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [territory_to_dict(row) for row in db.scalars(select(Territory).order_by(Territory.id))]


@app.post("/api/territories")
def create_territory(
    payload: TerritoryIn,
    user: User = Depends(require_admin_token),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    require_roles(user, {"mapper"})
    points = [point.model_dump() for point in payload.points]
    validate_points(points)
    territory = Territory(
        name=payload.name,
        state_id=payload.state_id,
        type=payload.type,
        status=payload.status,
        color=payload.color,
        points_json=json.dumps(points),
        area_size=polygon_area(points),
    )
    db.add(territory)
    db.flush()
    save_territory_version(db, territory, user, payload.reason)
    audit(db, user.id, "territory_created", "territory", territory.id, new=territory_to_dict(territory), reason=payload.reason)
    db.commit()
    db.refresh(territory)
    return territory_to_dict(territory)


@app.put("/api/territories/{territory_id}")
def update_territory(
    territory_id: int,
    payload: TerritoryIn,
    user: User = Depends(require_admin_token),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    require_roles(user, {"mapper"})
    territory = db.get(Territory, territory_id)
    if not territory:
        raise HTTPException(status_code=404, detail="Territory not found")
    old = territory_to_dict(territory)
    points = [point.model_dump() for point in payload.points]
    validate_points(points)
    territory.name = payload.name
    territory.state_id = payload.state_id
    territory.type = payload.type
    territory.status = payload.status
    territory.color = payload.color
    territory.points_json = json.dumps(points)
    territory.area_size = polygon_area(points)
    territory.version += 1
    territory.updated_at = now_utc()
    save_territory_version(db, territory, user, payload.reason)
    audit(db, user.id, "territory_updated", "territory", territory.id, old=old, new=territory_to_dict(territory), reason=payload.reason)
    db.commit()
    db.refresh(territory)
    return territory_to_dict(territory)


@app.post("/api/colonization")
def create_colonization(
    payload: ColonizationIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    state = db.get(State, payload.state_id)
    territory = db.get(Territory, payload.territory_id)
    if not state or not territory:
        raise HTTPException(status_code=404, detail="State or territory not found")
    if user.role != "admin" and state.leader_id != user.id:
        raise HTTPException(status_code=403, detail="Only the state leader can request colonization")
    if state.status != "active":
        raise HTTPException(status_code=409, detail="State is not active")
    if territory.type not in {"neutral", "disputed"} or territory.status in {"protected", "locked"}:
        raise HTTPException(status_code=409, detail="Territory cannot be colonized")
    active = db.scalar(
        select(ColonizationRequest).where(
            ColonizationRequest.state_id == state.id,
            ColonizationRequest.status.in_(["requested", "approved", "in_progress", "contested"]),
        )
    )
    if active:
        raise HTTPException(status_code=409, detail="State already has an active colonization")
    point = payload.point.model_dump() if payload.point else None
    action = PoliticalAction(
        type="colonization_request",
        actor_state_id=state.id,
        territory_id=territory.id,
        created_by=user.id,
        status="pending",
        payload_json=json.dumps({"point": point}, ensure_ascii=False),
    )
    db.add(action)
    db.flush()
    request = ColonizationRequest(
        state_id=state.id,
        territory_id=territory.id,
        requested_by=user.id,
        action_id=action.id,
        status="requested",
        cost=round(5 + territory.area_size * 100, 2),
    )
    db.add(request)
    db.flush()
    audit(db, user.id, "colonization_requested", "colonization_request", request.id, new=request_to_dict(request))
    db.commit()
    db.refresh(request)
    return request_to_dict(request)


@app.get("/api/actions")
def list_actions(_admin: User = Depends(require_admin_token), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [action_to_dict(row) for row in db.scalars(select(PoliticalAction).order_by(PoliticalAction.id.desc()))]


@app.post("/api/actions/{action_id}/approve")
def approve_action(
    action_id: int,
    payload: DecisionIn,
    user: User = Depends(require_admin_token),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    require_roles(user, {"moderator", "mapper"})
    action = db.get(PoliticalAction, action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    if action.status not in {"pending", "draft"}:
        raise HTTPException(status_code=409, detail="Action is already decided")
    old = action_to_dict(action)
    action.status = "approved"
    action.updated_at = now_utc()
    if action.type == "colonization_request" and action.territory_id and action.actor_state_id:
        territory = db.get(Territory, action.territory_id)
        request = db.scalar(select(ColonizationRequest).where(ColonizationRequest.action_id == action.id))
        if territory:
            territory.state_id = action.actor_state_id
            territory.type = "colony"
            territory.status = "active"
            territory.version += 1
            territory.updated_at = now_utc()
            save_territory_version(db, territory, user, payload.reason or "colonization approved")
        if request:
            request.status = "completed"
            request.completed_at = now_utc()
    audit(db, user.id, "action_approved", "political_action", action.id, old=old, new=action_to_dict(action), reason=payload.reason)
    db.commit()
    return action_to_dict(action)


@app.post("/api/actions/{action_id}/reject")
def reject_action(
    action_id: int,
    payload: DecisionIn,
    user: User = Depends(require_admin_token),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    require_roles(user, {"moderator", "mapper"})
    action = db.get(PoliticalAction, action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    if action.status not in {"pending", "draft"}:
        raise HTTPException(status_code=409, detail="Action is already decided")
    old = action_to_dict(action)
    action.status = "rejected"
    action.updated_at = now_utc()
    request = db.scalar(select(ColonizationRequest).where(ColonizationRequest.action_id == action.id))
    if request:
        request.status = "rejected"
    audit(db, user.id, "action_rejected", "political_action", action.id, old=old, new=action_to_dict(action), reason=payload.reason)
    db.commit()
    return action_to_dict(action)


@app.get("/api/audit-log")
def audit_log(_admin: User = Depends(require_admin_token), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(100))
    return [
        {
            "id": row.id,
            "user_id": row.user_id,
            "action_type": row.action_type,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "old_data": json_loads(row.old_data_json, {}),
            "new_data": json_loads(row.new_data_json, {}),
            "reason": row.reason,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


# Serve the built frontend from the same process so one container is enough for a demo.
_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _dist.is_dir():
    @app.get("/admin", include_in_schema=False)
    @app.get("/admin/{_path:path}", include_in_schema=False)
    def admin_spa(_path: str = "") -> FileResponse:
        return FileResponse(_dist / "index.html")

    app.mount("/", StaticFiles(directory=_dist, html=True), name="web")
