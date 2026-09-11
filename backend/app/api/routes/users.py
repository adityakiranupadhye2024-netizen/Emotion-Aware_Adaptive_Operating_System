"""
Minimal user/profile endpoints — enough for Module 1 to be a runnable,
testable slice of the system. Emotion/state/action/decision endpoints land
in Modules 2-4 alongside the AI code that powers them.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User, UserBaseline

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/", summary="Create a user profile")
def create_user(display_name: str = "Default User", db: Session = Depends(get_db)):
    user = User(display_name=display_name)
    db.add(user)
    db.flush()

    baseline = UserBaseline(user_id=user.id)
    db.add(baseline)

    db.commit()
    db.refresh(user)
    return {"id": user.id, "display_name": user.display_name}


@router.get("/{user_id}", summary="Get a user profile")
def get_user(user_id: str, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "id": user.id,
        "display_name": user.display_name,
        "created_at": user.created_at,
        "privacy": {
            "camera_sensing_enabled": user.camera_sensing_enabled == "true",
            "keyboard_dynamics_enabled": user.keyboard_dynamics_enabled == "true",
            "mouse_dynamics_enabled": user.mouse_dynamics_enabled == "true",
            "app_context_enabled": user.app_context_enabled == "true",
        },
    }


@router.patch("/{user_id}/privacy", summary="Update privacy toggles")
def update_privacy(
    user_id: str,
    camera_sensing_enabled: bool | None = None,
    keyboard_dynamics_enabled: bool | None = None,
    mouse_dynamics_enabled: bool | None = None,
    app_context_enabled: bool | None = None,
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if camera_sensing_enabled is not None:
        user.camera_sensing_enabled = "true" if camera_sensing_enabled else "false"
    if keyboard_dynamics_enabled is not None:
        user.keyboard_dynamics_enabled = "true" if keyboard_dynamics_enabled else "false"
    if mouse_dynamics_enabled is not None:
        user.mouse_dynamics_enabled = "true" if mouse_dynamics_enabled else "false"
    if app_context_enabled is not None:
        user.app_context_enabled = "true" if app_context_enabled else "false"

    db.commit()
    return {"status": "updated"}
