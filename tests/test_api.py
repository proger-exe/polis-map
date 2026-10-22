import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from backend.app.database import Base, SessionLocal, engine
from backend.app.main import AdminLoginIn, MapStateIn, PointIn, StateCapitalIn, TerritoryIn, admin_delete_state, admin_login, admin_map_state, admin_update_state_capital, app, create_territory, get_map, update_territory
from backend.app.models import AuditLog, State, Territory, User
from backend.app.services import bind_telegram, create_state_link_code, seed_database


def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    seed_database(db)
    return db


def test_public_map_seed_has_server_image_and_neutral_territories():
    db = fresh_db()
    try:
        data = get_map(db)
        assert data["image_url"].endswith("sample-world.svg")
        assert data["states"] == []
        assert len(data["territories"]) == 1
        assert data["territories"][0]["name"] == "Нейтральная долина"
        assert all(item["state_id"] is None for item in data["territories"])
    finally:
        db.close()


def test_admin_login_creates_token():
    db = fresh_db()
    try:
        response = admin_login(AdminLoginIn(username="admin", password="admin"), db)
        assert response["token"]
        assert response["expires_at"]
    finally:
        db.close()


def test_seed_removes_existing_north_bank_demo_territory():
    db = fresh_db()
    try:
        admin = db.get(User, 1)
        payload = TerritoryIn(
            name="Северный берег",
            points=[PointIn(x=0.18, y=0.24), PointIn(x=0.42, y=0.21), PointIn(x=0.47, y=0.42), PointIn(x=0.21, y=0.47)],
        )
        created = create_territory(payload, admin, db)

        seed_database(db)
        assert db.get(Territory, created["id"]) is None
        assert all(item["name"] != "Северный берег" for item in get_map(db)["territories"])
        assert any(item.action_type == "demo_territory_removed" for item in db.query(AuditLog).all())
    finally:
        db.close()


def test_admin_login_route_has_no_admin_auth_dependency():
    route = next(route for route in app.routes if getattr(route, "path", "") == "/api/admin/login")
    dependency_names = {dependency.call.__name__ for dependency in route.dependant.dependencies}
    assert "require_admin_token" not in dependency_names


def test_admin_creates_state_link_code_and_telegram_bind_preserves_state():
    db = fresh_db()
    try:
        admin = db.get(User, 1)
        result = create_state_link_code(db, admin, "shelby", "Южный Союз", "ЮС", {"x": 0.31, "y": 0.42}, "#D95D39")
        assert result["code"]
        assert result["state"]["status"] == "pending"
        assert result["state"]["capital_point"] == {"x": 0.31, "y": 0.42}

        user = bind_telegram(db, result["code"], "12345", "tg_user")
        state = db.query(State).filter(State.leader_id == user.id).one()
        assert user.telegram_id == "12345"
        assert state.name == "Южный Союз"
    finally:
        db.close()


def test_admin_creates_map_state_with_selectable_triangle_without_player():
    db = fresh_db()
    try:
        admin = db.get(User, 1)
        result = admin_map_state(
            MapStateIn(name="Картастан", color="#2E7DD7", capital_point=PointIn(x=0.4, y=0.5)),
            admin,
            db,
        )

        state = result["state"]
        territory = result["territory"]
        assert state["name"] == "Картастан"
        assert state["short_name"] == "КАР"
        assert state["leader_id"] == admin.id
        assert state["status"] == "unassigned"
        assert territory["name"] == "Картастан"
        assert territory["state_id"] == state["id"]
        assert territory["type"] == "state_core"
        assert territory["status"] == "active"
        assert len(territory["points"]) == 3
        assert all(0 <= point["x"] <= 1 and 0 <= point["y"] <= 1 for point in territory["points"])
        assert db.query(User).count() == 1
    finally:
        db.close()


def test_admin_moves_state_capital_point_and_writes_audit():
    db = fresh_db()
    try:
        admin = db.get(User, 1)
        result = admin_map_state(
            MapStateIn(name="Двигаемое", color="#2E7DD7", capital_point=PointIn(x=0.4, y=0.5)),
            admin,
            db,
        )

        moved = admin_update_state_capital(
            result["state"]["id"],
            StateCapitalIn(capital_point=PointIn(x=0.61, y=0.36)),
            admin,
            db,
        )

        assert moved["capital_point"] == {"x": 0.61, "y": 0.36}
        assert get_map(db)["states"][0]["capital_point"] == {"x": 0.61, "y": 0.36}
        assert any(item.action_type == "state_capital_updated" for item in db.query(AuditLog).all())
    finally:
        db.close()


def test_non_admin_cannot_create_territory():
    db = fresh_db()
    try:
        player = User(username="plain", role="player")
        db.add(player)
        db.commit()
        payload = TerritoryIn(
            name="Forbidden",
            points=[PointIn(x=0.1, y=0.1), PointIn(x=0.2, y=0.1), PointIn(x=0.2, y=0.2)],
        )
        try:
            create_territory(payload, player, db)
        except Exception as error:
            assert getattr(error, "status_code") == 403
        else:
            raise AssertionError("player created territory")
    finally:
        db.close()


def test_admin_assigns_state_to_territory_and_writes_audit():
    db = fresh_db()
    try:
        admin = db.get(User, 1)
        link = create_state_link_code(db, admin, "mapper_target", "Северная Артель", "СА", {"x": 0.25, "y": 0.3}, "#2E7DD7")
        payload = TerritoryIn(
            name="Нейтральная долина",
            state_id=link["state"]["id"],
            type="state_core",
            status="active",
            color="#2E7DD7",
            points=[PointIn(x=0.58, y=0.33), PointIn(x=0.79, y=0.36), PointIn(x=0.76, y=0.58), PointIn(x=0.55, y=0.55)],
        )
        territory = update_territory(1, payload, admin, db)
        assert territory["state_id"] == link["state"]["id"]
        assert territory["type"] == "state_core"

        rows = db.query(AuditLog).all()
        assert any(item.action_type == "territory_updated" for item in rows)
    finally:
        db.close()


def test_admin_deletes_state_with_territories_and_audit():
    db = fresh_db()
    try:
        admin = db.get(User, 1)
        link = create_state_link_code(db, admin, "delete_target", "Удаляемое", "УД", {"x": 0.22, "y": 0.33}, "#D95D39")
        first_payload = TerritoryIn(
            name="Delete Area",
            state_id=link["state"]["id"],
            type="state_core",
            status="active",
            color="#D95D39",
            points=[PointIn(x=0.1, y=0.1), PointIn(x=0.2, y=0.1), PointIn(x=0.2, y=0.2)],
        )
        second_payload = TerritoryIn(
            name="Delete Area 2",
            state_id=link["state"]["id"],
            type="colony",
            status="active",
            color="#D95D39",
            points=[PointIn(x=0.3, y=0.3), PointIn(x=0.4, y=0.3), PointIn(x=0.4, y=0.4)],
        )
        first = create_territory(first_payload, admin, db)
        second = create_territory(second_payload, admin, db)

        result = admin_delete_state(link["state"]["id"], admin, db)
        assert set(result["territory_ids"]) == {first["id"], second["id"]}
        assert db.get(State, link["state"]["id"]) is None
        assert db.get(Territory, first["id"]) is None
        assert db.get(Territory, second["id"]) is None
        map_territory_ids = {territory["id"] for territory in get_map(db)["territories"]}
        assert first["id"] not in map_territory_ids
        assert second["id"] not in map_territory_ids
        assert any(item.action_type == "state_deleted" for item in db.query(AuditLog).all())
    finally:
        db.close()


def test_admin_delete_missing_state_raises_404():
    db = fresh_db()
    try:
        admin = db.get(User, 1)
        try:
            admin_delete_state(999, admin, db)
        except Exception as error:
            assert getattr(error, "status_code") == 404
        else:
            raise AssertionError("missing state was deleted")
    finally:
        db.close()
