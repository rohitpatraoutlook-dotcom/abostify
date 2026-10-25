import os
import uuid
import hashlib

from flask import (
    Blueprint, request, jsonify, current_app, send_from_directory
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from sqlalchemy.exc import IntegrityError

from models import db
from company_portal import Company, CompanyEmployee, can_manage_company
from phase2_documents_models import CompanyDocument
from phase2_events import record_activity

documents_api = Blueprint(
    "documents_api", __name__, url_prefix="/api/v2"
)

ALLOWED_EXTENSIONS = {
    "pdf", "doc", "docx", "xls", "xlsx", "csv",
    "txt", "png", "jpg", "jpeg", "ppt", "pptx"
}


def doc_error(message, status=400):
    return jsonify({"ok": False, "error": message}), status


def is_member(company_id, user_id):
    return CompanyEmployee.query.filter_by(
        company_id=company_id,
        user_id=user_id,
        status="active"
    ).first()


def document_json(item):
    return {
        "id": item.id,
        "company_id": item.company_id,
        "filename": item.original_filename,
        "mime_type": item.mime_type,
        "size_bytes": item.size_bytes,
        "uploaded_by": item.uploader.username,
        "created_at": item.created_at.isoformat()
    }


def storage_dir():
    path = os.path.join(
        current_app.instance_path, "company_documents"
    )
    os.makedirs(path, exist_ok=True)
    return path


@documents_api.post("/companies/<int:cid>/documents")
@login_required
def upload_document(cid):
    if not is_member(cid, current_user.id):
        return doc_error("Active company membership required", 403)

    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        return doc_error("Choose a file to upload")

    original = secure_filename(uploaded.filename)
    if not original:
        return doc_error("Invalid filename")

    if "." not in original:
        return doc_error("File extension is required")

    extension = original.rsplit(".", 1)[1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        return doc_error("This file type is not allowed")

    # Read at most 5 MB + 1 byte to enforce the upload limit.
    content = uploaded.stream.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        return doc_error("Maximum file size is 5 MB", 413)

    if not content:
        return doc_error("Empty files are not allowed")

    storage_name = uuid.uuid4().hex
    target = os.path.join(storage_dir(), storage_name)

    try:
        with open(target, "xb") as file_handle:
            file_handle.write(content)

        item = CompanyDocument(
            company_id=cid,
            uploaded_by_id=current_user.id,
            original_filename=original[:255],
            storage_filename=storage_name,
            mime_type=uploaded.mimetype or "application/octet-stream",
            size_bytes=len(content)
        )

        db.session.add(item)
        db.session.flush()

        company = Company.query.filter_by(id=cid).first()
        if company:
            record_activity(
                workspace_id=company.workspace_id,
                actor_id=current_user.id,
                action="document_uploaded",
                object_type="company_document",
                object_id=item.id,
                details={
                    "filename": item.original_filename,
                    "size_bytes": item.size_bytes,
                },
                ip_address=request.remote_addr,
            )

        db.session.commit()

    except (OSError, IntegrityError):
        db.session.rollback()
        if os.path.exists(target):
            os.remove(target)
        return doc_error("Could not save document", 500)

    return jsonify({
        "ok": True,
        "document": document_json(item)
    }), 201


@documents_api.get("/companies/<int:cid>/documents")
@login_required
def list_documents(cid):
    if not is_member(cid, current_user.id):
        return doc_error("Active company membership required", 403)

    items = CompanyDocument.query.filter_by(
        company_id=cid
    ).order_by(CompanyDocument.created_at.desc()).limit(300).all()

    return jsonify({
        "ok": True,
        "documents": [document_json(item) for item in items]
    })


@documents_api.get("/companies/<int:cid>/documents/<int:doc_id>/download")
@login_required
def download_document(cid, doc_id):
    if not is_member(cid, current_user.id):
        return doc_error("Active company membership required", 403)

    item = CompanyDocument.query.filter_by(
        id=doc_id, company_id=cid
    ).first_or_404()

    return send_from_directory(
        storage_dir(),
        item.storage_filename,
        as_attachment=True,
        download_name=item.original_filename,
        mimetype="application/octet-stream"
    )


@documents_api.delete("/companies/<int:cid>/documents/<int:doc_id>")
@login_required
def delete_document(cid, doc_id):
    if not is_member(cid, current_user.id):
        return doc_error("Active company membership required", 403)

    item = CompanyDocument.query.filter_by(
        id=doc_id, company_id=cid
    ).first_or_404()

    is_manager = can_manage_company(cid, current_user.id)
    is_uploader = item.uploaded_by_id == current_user.id

    if not (is_manager or is_uploader):
        return doc_error("Only the uploader or company HR/Admin can delete", 403)

    target = os.path.join(storage_dir(), item.storage_filename)

    try:
        company = Company.query.filter_by(id=cid).first()
        if company:
            record_activity(
                workspace_id=company.workspace_id,
                actor_id=current_user.id,
                action="document_deleted",
                object_type="company_document",
                object_id=item.id,
                details={"filename": item.original_filename},
                ip_address=request.remote_addr,
            )

        if os.path.isfile(target):
            os.remove(target)

        db.session.delete(item)
        db.session.commit()
    except OSError:
        db.session.rollback()
        return doc_error("Could not delete document file", 500)

    return jsonify({"ok": True, "message": "Document deleted"})
