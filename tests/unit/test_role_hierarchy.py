import pytest
from clubledger.core.errors import DomainError
from clubledger.security.roles import require_administrator, protect_self
from clubledger.seed import repair_demo_roles


def test_officers_cannot_manage_admin_even_with_extra_permission(db, make_user):
    officer = make_user(email="hierarchy@college.edu", roles=["treasurer"])
    with pytest.raises(DomainError) as error:
        require_administrator(db, officer["id"])
    assert error.value.http_status == 403
    admin = make_user(email="hierarchy-admin@college.edu", roles=["admin"])
    require_administrator(db, admin["id"])
    for action, role in [("deactivate", None), ("revoke", "admin")]:
        with pytest.raises(DomainError):
            protect_self(admin["id"], admin["id"], action, role)


def test_demo_roles_repair_is_idempotent_and_preserves_real_users(db, make_user):
    treasurer = make_user(email="treasurer@skyline.edu", roles=["admin"])
    student = make_user(email="student@skyline.edu", roles=["admin"])
    real = make_user(email="real-admin@college.edu", roles=["admin"])
    repair_demo_roles(db)
    repair_demo_roles(db)
    def roles(user):
        return [r[0] for r in db.execute("SELECT r.code FROM user_roles ur JOIN roles r ON r.id=ur.role_id WHERE ur.user_id=? AND ur.revoked_at IS NULL", (user["id"],))]
    assert roles(treasurer) == ["treasurer"]
    assert roles(student) == []
    assert roles(real) == ["admin"]
