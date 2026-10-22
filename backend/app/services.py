import json
import secrets
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.models import (
    AppSetting,
    AuditLog,
    ColonizationRequest,
    MapVersion,
    PoliticalAction,
    State,
    TelegramAccount,
    Territory,
    User,
    now_utc,
)


def json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def setting(db: Session, key: str, default: str = "") -> str:
    row = db.get(AppSetting, key)
    return row.value if row else default


def set_setting(db: Session, key: str, value: str) -> None:
    row = db.get(AppSetting, key)
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))


def audit(
    db: Session,
    user_id: int | None,
    action_type: str,
    entity_type: str,
    entity_id: int | None,
    old: Any = None,
    new: Any = None,
    reason: str = "",
) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            action_type=action_type,
            entity_type=entity_type,
            entity_id=entity_id,
            old_data_json=json.dumps(old or {}, ensure_ascii=False),
            new_data_json=json.dumps(new or {}, ensure_ascii=False),
            reason=reason,
        )
    )


def validate_points(points: list[dict[str, float]]) -> None:
    if len(points) < 3:
        raise HTTPException(status_code=422, detail="Territory polygon needs at least 3 points")
    for point in points:
        x = point.get("x")
        y = point.get("y")
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            raise HTTPException(status_code=422, detail="Point coordinates must be numbers")
        if x < 0 or x > 1 or y < 0 or y > 1:
            raise HTTPException(status_code=422, detail="Point coordinates must be normalized from 0 to 1")


def polygon_area(points: list[dict[str, float]]) -> float:
    area = 0.0
    for index, point in enumerate(points):
        next_point = points[(index + 1) % len(points)]
        area += point["x"] * next_point["y"] - next_point["x"] * point["y"]
    return abs(area) / 2


def user_to_dict(user: User) -> dict[str, Any]:
    return {"id": user.id, "username": user.username, "role": user.role, "telegram_id": user.telegram_id}


def state_to_dict(state: State) -> dict[str, Any]:
    return {
        "id": state.id,
        "name": state.name,
        "short_name": state.short_name,
        "description": state.description,
        "color": state.color,
        "leader_id": state.leader_id,
        "capital_point": {"x": state.capital_x, "y": state.capital_y},
        "government_type": state.government_type,
        "status": state.status,
    }


def territory_to_dict(territory: Territory) -> dict[str, Any]:
    return {
        "id": territory.id,
        "name": territory.name,
        "state_id": territory.state_id,
        "type": territory.type,
        "status": territory.status,
        "color": territory.color,
        "points": json_loads(territory.points_json, []),
        "area_size": territory.area_size,
        "version": territory.version,
    }


def action_to_dict(action: PoliticalAction) -> dict[str, Any]:
    return {
        "id": action.id,
        "type": action.type,
        "actor_state_id": action.actor_state_id,
        "target_state_id": action.target_state_id,
        "territory_id": action.territory_id,
        "created_by": action.created_by,
        "status": action.status,
        "payload": json_loads(action.payload_json, {}),
        "created_at": action.created_at.isoformat(),
    }


def request_to_dict(request: ColonizationRequest) -> dict[str, Any]:
    return {
        "id": request.id,
        "state_id": request.state_id,
        "territory_id": request.territory_id,
        "requested_by": request.requested_by,
        "action_id": request.action_id,
        "status": request.status,
        "cost": request.cost,
        "created_at": request.created_at.isoformat(),
    }


def seed_database(db: Session) -> None:
    if db.scalar(select(User).limit(1)):
        migrate_legacy_demo_seed(db)
        remove_demo_territory(db, "Северный берег")
        return

    db.add(User(id=1, username="admin", role="admin"))
    db.flush()

    colony_target = Territory(
        id=1,
        name="Нейтральная долина",
        state_id=None,
        type="neutral",
        status="neutral",
        color="#9AA36B",
        points_json=json.dumps(
            [{"x": 0.58, "y": 0.33}, {"x": 0.79, "y": 0.36}, {"x": 0.76, "y": 0.58}, {"x": 0.55, "y": 0.55}]
        ),
        area_size=0.043,
    )
    db.add(colony_target)
    set_setting(db, "map_image_url", "/static/maps/sample-world.svg")
    set_setting(db, "map_width", "1600")
    set_setting(db, "map_height", "1000")
    audit(db, 1, "bootstrap", "system", None, new={"users": 1, "states": 0, "territories": 1})
    db.commit()


def remove_demo_territory(db: Session, name: str) -> None:
    territory = db.scalar(select(Territory).where(Territory.name == name))
    if not territory:
        return
    old = territory_to_dict(territory)
    db.query(ColonizationRequest).filter(ColonizationRequest.territory_id == territory.id).delete(synchronize_session=False)
    db.query(PoliticalAction).filter(PoliticalAction.territory_id == territory.id).delete(synchronize_session=False)
    db.query(MapVersion).filter(MapVersion.territory_id == territory.id).delete(synchronize_session=False)
    db.delete(territory)
    audit(db, 1, "demo_territory_removed", "territory", old["id"], old=old, reason="remove seeded Северный берег")
    db.commit()


def migrate_legacy_demo_seed(db: Session) -> None:
    users = db.scalars(select(User).order_by(User.id)).all()
    usernames = {user.username for user in users}
    if usernames != {"admin", "mapper", "leader", "player"}:
        return
    state = db.scalar(select(State).where(State.name == "Северная Республика"))
    if not state:
        return

    db.query(ColonizationRequest).delete()
    db.query(PoliticalAction).delete()
    db.query(MapVersion).delete()
    db.query(TelegramAccount).delete()
    for territory in db.scalars(select(Territory).where(Territory.state_id == state.id)):
        territory.state_id = None
        territory.type = "neutral"
        territory.status = "neutral"
        territory.color = "#9AA36B"
        territory.version += 1
    for extra_user in users:
        if extra_user.username != "admin":
            db.delete(extra_user)
    db.delete(state)
    audit(db, 1, "legacy_seed_migrated", "system", None, new={"users": 1, "states": 0})
    db.commit()


async def save_map_upload(db: Session, user: User, upload: UploadFile) -> dict[str, Any]:
    if not upload.content_type or not upload.content_type.startswith("image/"):
        raise HTTPException(status_code=422, detail="Upload must be an image")

    settings.map_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(upload.filename or "map.png").suffix.lower() or ".png"
    path = settings.map_dir / f"main{suffix}"
    data = await upload.read()
    path.write_bytes(data)

    with Image.open(path) as image:
        width, height = image.size

    url = f"/static/maps/{path.name}"
    set_setting(db, "map_image_url", url)
    set_setting(db, "map_width", str(width))
    set_setting(db, "map_height", str(height))
    audit(db, user.id, "map_uploaded", "map", None, new={"image_url": url, "width": width, "height": height})
    db.commit()
    return {"image_url": url, "width": width, "height": height}


def create_link_code(db: Session, user: User) -> str:
    code = secrets.token_hex(3).upper()
    set_setting(db, f"link_code:{code}", str(user.id))
    audit(db, user.id, "link_code_created", "user", user.id, new={"code": code})
    db.commit()
    return code


def create_state_link_code(
    db: Session,
    admin: User,
    username: str,
    state_name: str,
    short_name: str,
    capital_point: dict[str, float],
    color: str,
    description: str = "",
) -> dict[str, Any]:
    existing_user = db.scalar(select(User).where(User.username == username))
    if existing_user:
        raise HTTPException(status_code=409, detail="Username already exists")
    existing_state = db.scalar(select(State).where(State.name == state_name))
    if existing_state:
        raise HTTPException(status_code=409, detail="State already exists")

    user = User(username=username, role="leader")
    db.add(user)
    db.flush()
    state = State(
        name=state_name,
        short_name=short_name,
        description=description,
        color=color,
        leader_id=user.id,
        capital_x=capital_point["x"],
        capital_y=capital_point["y"],
        status="pending",
    )
    db.add(state)
    db.flush()
    code = create_link_code(db, user)
    audit(
        db,
        admin.id,
        "state_link_code_created",
        "state",
        state.id,
        new={"user": user_to_dict(user), "state": state_to_dict(state), "code": code},
    )
    db.commit()
    return {"code": code, "user": user_to_dict(user), "state": state_to_dict(state)}


def starter_triangle(center: dict[str, float], radius: float = 0.018) -> list[dict[str, float]]:
    x = center["x"]
    y = center["y"]
    return [
        {"x": max(0, min(1, x)), "y": max(0, min(1, y - radius))},
        {"x": max(0, min(1, x + radius)), "y": max(0, min(1, y + radius))},
        {"x": max(0, min(1, x - radius)), "y": max(0, min(1, y + radius))},
    ]


def create_map_state(
    db: Session,
    admin: User,
    name: str,
    short_name: str,
    color: str,
    capital_point: dict[str, float],
    description: str = "",
) -> dict[str, Any]:
    existing_state = db.scalar(select(State).where(State.name == name))
    if existing_state:
        raise HTTPException(status_code=409, detail="State already exists")

    state = State(
        name=name,
        short_name=short_name,
        description=description,
        color=color,
        leader_id=admin.id,
        capital_x=capital_point["x"],
        capital_y=capital_point["y"],
        status="unassigned",
    )
    db.add(state)
    db.flush()

    points = starter_triangle(capital_point)
    territory = Territory(
        name=name,
        state_id=state.id,
        type="state_core",
        status="active",
        color=color,
        points_json=json.dumps(points),
        area_size=polygon_area(points),
    )
    db.add(territory)
    db.flush()
    save_territory_version(db, territory, admin, "map state created")
    result = {"state": state_to_dict(state), "territory": territory_to_dict(territory)}
    audit(db, admin.id, "map_state_created", "state", state.id, new=result)
    db.commit()
    return result


def delete_state_with_territories(db: Session, admin: User, state_id: int) -> dict[str, Any]:
    state = db.get(State, state_id)
    if not state:
        raise HTTPException(status_code=404, detail="State not found")

    old_state = state_to_dict(state)
    territories = db.scalars(select(Territory).where(Territory.state_id == state.id)).all()
    territory_ids = [territory.id for territory in territories]
    leader_id = state.leader_id

    db.query(ColonizationRequest).filter(ColonizationRequest.state_id == state.id).delete(synchronize_session=False)
    action_filter = (PoliticalAction.actor_state_id == state.id) | (PoliticalAction.target_state_id == state.id)
    if territory_ids:
        action_filter = action_filter | PoliticalAction.territory_id.in_(territory_ids)
    db.query(PoliticalAction).filter(action_filter).delete(synchronize_session=False)
    if territory_ids:
        db.query(MapVersion).filter(MapVersion.territory_id.in_(territory_ids)).delete(synchronize_session=False)
    for territory in territories:
        db.delete(territory)
    db.delete(state)

    leader = db.get(User, leader_id)
    if leader and leader.role != "admin":
        other_state = db.scalar(select(State).where(State.leader_id == leader.id, State.id != state_id))
        if not other_state:
            db.query(TelegramAccount).filter(TelegramAccount.user_id == leader.id).delete(synchronize_session=False)
            db.delete(leader)

    result = {"state": old_state, "territory_ids": territory_ids}
    audit(db, admin.id, "state_deleted", "state", state_id, old=result, reason="admin delete")
    db.commit()
    return result


def bind_telegram(db: Session, code: str, telegram_id: str, username: str | None) -> User:
    user_id = setting(db, f"link_code:{code}")
    if not user_id:
        raise ValueError("Invalid link code")
    user = db.get(User, int(user_id))
    if not user:
        raise ValueError("User not found")
    user.telegram_id = telegram_id
    existing = db.scalar(select(TelegramAccount).where(TelegramAccount.telegram_id == telegram_id))
    if existing:
        existing.user_id = user.id
        existing.username = username
    else:
        db.add(TelegramAccount(user_id=user.id, telegram_id=telegram_id, username=username))
    set_setting(db, f"link_code:{code}", "")
    audit(db, user.id, "telegram_linked", "user", user.id, new={"telegram_id": telegram_id, "username": username})
    db.commit()
    return user


def state_for_user(db: Session, user: User) -> State | None:
    return db.scalar(select(State).where(State.leader_id == user.id).order_by(State.id))


def save_territory_version(db: Session, territory: Territory, user: User, reason: str) -> None:
    db.add(
        MapVersion(
            territory_id=territory.id,
            version=territory.version,
            changed_by=user.id,
            reason=reason,
            snapshot_json=json.dumps(territory_to_dict(territory), ensure_ascii=False),
        )
    )
