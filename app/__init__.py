"""Application factory for the inventory API."""

from flask import Flask, jsonify


def create_app():
    app = Flask(__name__)
    app.json.sort_keys = False  # keep "id" first in responses

    from app.routes import bp
    app.register_blueprint(bp)

    # Return JSON errors instead of Flask's default HTML pages.
    @app.errorhandler(404)
    def not_found(_err):
        return jsonify({"error": "Resource not found."}), 404

    @app.errorhandler(405)
    def method_not_allowed(_err):
        return jsonify({"error": "Method not allowed."}), 405

    return app