"""Render web entry point. Participant CSVs stay entirely in the browser."""
import json
import os
from flask import Flask, Response, jsonify, redirect
from survey_automation import ROOT, questions_from_schema, draft_ratings, render_preview


def create_app():
    app = Flask(__name__, static_folder=None)

    @app.get('/')
    def index():
        schema = json.loads((ROOT / 'form_schema.json').read_text(encoding='utf-8'))
        questions = questions_from_schema(schema)
        draft_ratings(questions)
        # Never embed the server's local participant files in a public page.
        return Response(render_preview(schema, questions, participants=[]), mimetype='text/html')

    @app.get('/health')
    def health():
        return jsonify(status='ok')

    @app.get('/survey_preview.html')
    def preview():
        return redirect('/')

    @app.get('/favicon.ico')
    def favicon():
        return '', 204

    @app.after_request
    def headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    return app


app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '10000')), debug=False)
