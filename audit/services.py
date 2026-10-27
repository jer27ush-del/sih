from .models import AuditLog


def record_audit(*, action, entity, entity_id, actor=None, old=None, new=None, request=None):
    """Write one audit entry. Call it inside the same transaction as the change it describes,
    so a status change and its audit entry are either both saved or both rolled back."""
    if actor is None:
        label = "System"
    else:
        label = f"{actor.name} ({actor.role})"
    ip = request.META.get("REMOTE_ADDR") if request is not None else None
    return AuditLog.objects.create(
        actor=actor if actor is not None and actor.pk else None,
        actor_label=label[:255],
        action=action,
        entity=entity,
        entity_id=str(entity_id),
        old_value=old,
        new_value=new,
        ip_address=ip or None,
    )
