from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import or_

from models import db, User
from extended_models import (
    Conversation,
    ConversationParticipant,
    Message,
)

messaging = Blueprint("messaging", __name__, url_prefix="/api")


def utc_now():
    return datetime.now(timezone.utc)


def serialize_message(message):
    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "sender_id": message.sender_id,
        "body": message.body,
        "edited_at": (
            message.edited_at.isoformat()
            if message.edited_at else None
        ),
        "deleted_at": (
            message.deleted_at.isoformat()
            if message.deleted_at else None
        ),
    }


def serialize_conversation(conversation, participant):
    return {
        "id": conversation.id,
        "type": conversation.conversation_type,
        "title": conversation.title,
        "created_by_id": conversation.created_by_id,
        "is_archived": conversation.is_archived,
        "is_muted": participant.is_muted,
        "last_read_at": (
            participant.last_read_at.isoformat()
            if participant.last_read_at else None
        ),
    }


def is_participant(conversation_id, user_id):
    return ConversationParticipant.query.filter_by(
        conversation_id=conversation_id,
        user_id=user_id,
    ).first()


def error(message, status=400):
    return jsonify({"error": message}), status


@messaging.route("/conversations", methods=["GET", "POST"])
@login_required
def conversations():
    if request.method == "GET":
        memberships = ConversationParticipant.query.filter_by(
            user_id=current_user.id
        ).all()

        result = []

        for participant in memberships:
            conversation = db.session.get(
                Conversation, participant.conversation_id
            )

            if conversation and not conversation.is_archived:
                result.append(
                    serialize_conversation(conversation, participant)
                )

        return jsonify({"conversations": result})

    data = request.get_json(silent=True) or {}
    raw_ids = data.get("participant_ids", [])

    if not isinstance(raw_ids, list):
        return error("participant_ids must be a list")

    if len(raw_ids) > 49:
        return error("A conversation can have at most 50 participants")

    participant_ids = {current_user.id}

    for value in raw_ids:
        try:
            participant_ids.add(int(value))
        except (TypeError, ValueError):
            return error("Every participant ID must be an integer")

    users = User.query.filter(
        User.id.in_(participant_ids)
    ).all()

    if len(users) != len(participant_ids):
        return error("One or more users do not exist", 404)

    title = str(data.get("title", "")).strip()[:120] or None
    conversation_type = (
        "group" if len(participant_ids) > 2 else "direct"
    )

    conversation = Conversation(
        conversation_type=conversation_type,
        title=title,
        created_by_id=current_user.id,
        is_archived=False,
    )

    db.session.add(conversation)
    db.session.flush()

    for user_id in participant_ids:
        db.session.add(
            ConversationParticipant(
                conversation_id=conversation.id,
                user_id=user_id,
                is_muted=False,
            )
        )

    db.session.commit()

    return jsonify({
        "message": "Conversation created",
        "conversation_id": conversation.id,
        "type": conversation.conversation_type,
        "participant_ids": sorted(participant_ids),
    }), 201


@messaging.route(
    "/conversations/<int:conversation_id>/messages",
    methods=["GET", "POST"],
)
@login_required
def conversation_messages(conversation_id):
    participant = is_participant(
        conversation_id, current_user.id
    )

    if not participant:
        return error("Conversation not found", 404)

    conversation = db.session.get(Conversation, conversation_id)

    if not conversation or conversation.is_archived:
        return error("Conversation not found", 404)

    if request.method == "GET":
        limit = request.args.get("limit", 50, type=int)
        limit = max(1, min(limit or 50, 100))

        query = Message.query.filter_by(
            conversation_id=conversation_id
        ).order_by(Message.id.desc())

        messages = query.limit(limit).all()
        messages.reverse()

        participant.last_read_at = utc_now()
        db.session.commit()

        return jsonify({
            "conversation_id": conversation_id,
            "messages": [
                serialize_message(message)
                for message in messages
            ],
        })

    data = request.get_json(silent=True) or {}
    body = str(data.get("body", "")).strip()

    if not body:
        return error("Message body is required")

    if len(body) > 5000:
        return error("Message cannot exceed 5000 characters")

    message = Message(
        conversation_id=conversation_id,
        sender_id=current_user.id,
        body=body,
    )

    db.session.add(message)
    db.session.commit()

    return jsonify({
        "message": "Message sent",
        "data": serialize_message(message),
    }), 201


@messaging.route(
    "/messages/<int:message_id>",
    methods=["PATCH", "DELETE"],
)
@login_required
def update_message(message_id):
    message = db.session.get(Message, message_id)

    if not message or message.deleted_at:
        return error("Message not found", 404)

    if not is_participant(
        message.conversation_id, current_user.id
    ):
        return error("Message not found", 404)

    if message.sender_id != current_user.id:
        return error("You can only edit or delete your own messages", 403)

    if request.method == "DELETE":
        message.deleted_at = utc_now()
        message.body = ""
        db.session.commit()

        return jsonify({"message": "Message deleted"})

    data = request.get_json(silent=True) or {}
    body = str(data.get("body", "")).strip()

    if not body:
        return error("Message body is required")

    if len(body) > 5000:
        return error("Message cannot exceed 5000 characters")

    message.body = body
    message.edited_at = utc_now()
    db.session.commit()

    return jsonify({
        "message": "Message updated",
        "data": serialize_message(message),
    })


@messaging.route(
    "/conversations/<int:conversation_id>/settings",
    methods=["PATCH"],
)
@login_required
def conversation_settings(conversation_id):
    participant = is_participant(
        conversation_id, current_user.id
    )

    if not participant:
        return error("Conversation not found", 404)

    data = request.get_json(silent=True) or {}

    if "is_muted" in data:
        if not isinstance(data["is_muted"], bool):
            return error("is_muted must be true or false")

        participant.is_muted = data["is_muted"]

    if "last_read_at" in data:
        participant.last_read_at = utc_now()

    db.session.commit()

    return jsonify({
        "message": "Conversation settings updated",
        "is_muted": participant.is_muted,
        "last_read_at": (
            participant.last_read_at.isoformat()
            if participant.last_read_at else None
        ),
    })
