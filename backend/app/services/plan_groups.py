"""Display organization only: never regenerate bills or reminder records."""
import hashlib
import json

from sqlalchemy import select

from app.errors import AppError
from app.models import BillPlan, BillPlanGroup, User


def lock_layout_user(db, user_id, *, shared=False):
    user = db.scalar(select(User).where(User.id == user_id).with_for_update(read=shared)
                     .execution_options(populate_existing=True))
    if user is None or not user.is_active:
        raise AppError("AUTH_SESSION_INVALID", "登录会话已失效", 401)


def resolve_group(db, user_id, group_id):
    if group_id is None:
        return None
    group = db.scalar(select(BillPlanGroup).where(
        BillPlanGroup.id == group_id, BillPlanGroup.user_id == user_id,
    ).with_for_update(read=True).execution_options(populate_existing=True))
    if group is None:
        raise AppError("BILL_GROUP_NOT_FOUND", "分组不存在，请重新加载后选择", 404)
    return None if group.is_default else group.id


def next_plan_position(db, user_id, group_id):
    position = db.scalar(select(BillPlan.sort_order).where(
        BillPlan.user_id == user_id, BillPlan.group_id == group_id,
        BillPlan.deleted_at.is_(None),
    ).order_by(BillPlan.sort_order.desc(), BillPlan.id.desc()).limit(1).with_for_update())
    return position + 1 if position is not None else 0


def layout_snapshot(db, user_id):
    # Caller holds the User lock. Current reads also bypass authentication's
    # older REPEATABLE READ snapshot and refresh SQLAlchemy's identity map.
    from app.services.billing import plan_response

    db.flush()
    groups = list(db.scalars(select(BillPlanGroup).where(BillPlanGroup.user_id == user_id)
                            .order_by(BillPlanGroup.sort_order, BillPlanGroup.id)
                            .with_for_update(read=True).execution_options(populate_existing=True)))
    plans = list(db.scalars(select(BillPlan).where(
        BillPlan.user_id == user_id, BillPlan.deleted_at.is_(None),
    ).order_by(BillPlan.id).with_for_update(read=True).execution_options(populate_existing=True)))
    order = {None if group.is_default else group.id: index for index, group in enumerate(groups)}
    plans.sort(key=lambda plan: (order.get(plan.group_id, len(groups)), plan.sort_order, -plan.id))
    state = [
        [(g.id, g.name, g.sort_order, g.is_default) for g in groups],
        [(p.id, p.group_id, p.sort_order) for p in plans],
    ]
    version = hashlib.sha256(json.dumps(state, separators=(",", ":")).encode()).hexdigest()
    return {"version": version, "groups": groups, "plans": [plan_response(p) for p in plans]}


def check_version(snapshot, version):
    if snapshot["version"] != version:
        raise AppError("BILL_LAYOUT_CHANGED", "规则或分组已发生变化，请重新加载后再调整", 409)


def save_layout(db, user_id, payload):
    lock_layout_user(db, user_id)
    snapshot = layout_snapshot(db, user_id)
    check_version(snapshot, payload.version)
    groups = {g.id: g for g in snapshot["groups"]}
    group_ids = [group.id for group in payload.groups]
    plan_ids = [pid for group in payload.groups for pid in group.plan_ids]
    expected_plans = {plan["id"] for plan in snapshot["plans"]}
    if (len(group_ids) != len(set(group_ids)) or set(group_ids) != set(groups)
            or len(plan_ids) != len(set(plan_ids)) or set(plan_ids) != expected_plans):
        raise AppError("BILL_LAYOUT_INVALID", "排序必须完整包含当前用户的分组和规则，且不能重复", 400)
    # Retain current-read ORM objects while applying changes. A db.get() here
    # could reload an older RR snapshot once layout_snapshot's weak references
    # have been released, causing dirty checking to silently miss a move.
    plans = {plan.id: plan for plan in db.scalars(select(BillPlan).where(
        BillPlan.user_id == user_id, BillPlan.deleted_at.is_(None),
    ).with_for_update().execution_options(populate_existing=True))}
    for group_position, item in enumerate(payload.groups):
        group = groups[item.id]
        group.sort_order = group_position
        for plan_position, plan_id in enumerate(item.plan_ids):
            plan = plans[plan_id]
            plan.group_id = None if group.is_default else group.id
            plan.sort_order = plan_position
    return layout_snapshot(db, user_id)


def edit_group(db, user_id, version, *, group_id=None, name=None, remove=False):
    lock_layout_user(db, user_id)
    snapshot = layout_snapshot(db, user_id)
    check_version(snapshot, version)
    groups = snapshot["groups"]
    group = next((g for g in groups if g.id == group_id), None)
    if group_id is not None:
        if group is None:
            raise AppError("BILL_GROUP_NOT_FOUND", "分组不存在", 404)
        if group.is_default:
            raise AppError("BILL_DEFAULT_GROUP", "未分组可以排序，但不能重命名或删除", 400)
    if remove:
        position = next_plan_position(db, user_id, None)
        # Include soft-deleted rules to avoid leaving dangling group references.
        members = db.scalars(select(BillPlan).where(
            BillPlan.user_id == user_id, BillPlan.group_id == group.id,
        ).order_by(BillPlan.sort_order, BillPlan.id.desc()).with_for_update()
          .execution_options(populate_existing=True))
        for plan in members:
            plan.group_id = None
            plan.sort_order = position
            position += 1
        db.flush()
        db.delete(group)
    else:
        if any(g.id != group_id and g.name.casefold() == name.casefold() for g in groups):
            raise AppError("BILL_GROUP_NAME_CONFLICT", "分组名称已存在", 409)
        if group is None:
            db.add(BillPlanGroup(user_id=user_id, name=name,
                                sort_order=max((g.sort_order for g in groups), default=-1) + 1))
        else:
            group.name = name
    return layout_snapshot(db, user_id)
