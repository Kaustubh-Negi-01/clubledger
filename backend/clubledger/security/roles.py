"""Role hierarchy: administrators alone manage accounts and officer permissions."""

from clubledger.core.errors import DomainError


def require_administrator(conn, actor_id):
    """Check the live role, even if another role acquired a management permission."""
    if not conn.execute(
        "SELECT 1 FROM user_roles ur JOIN roles r ON r.id=ur.role_id "
        "JOIN users u ON u.id=ur.user_id WHERE ur.user_id=? "
        "AND r.code='admin' AND ur.revoked_at IS NULL AND u.is_active=1",
        (actor_id,),
    ).fetchone():
        raise DomainError("FORBIDDEN", 403, "Only an administrator can manage accounts and roles.")


def protect_self(actor_id, target_id, action, role=None):
    """Do not let administrators disable their own account or remove their admin role."""
    if actor_id == target_id and (action == "deactivate" or (action == "revoke" and role == "admin")):
        raise DomainError("FORBIDDEN", 403, "You cannot remove your own administrator access.")
