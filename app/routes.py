from flask import Blueprint, jsonify

from app import data

bp = Blueprint("inventory", __name__)


@bp.get("/health")
def health():
    return jsonify({"status": "ok", "items": len(data.inventory)}), 200