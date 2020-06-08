from flask import Flask, render_template, jsonify, request, redirect
from vfzsync import app
import vfzsync.vfz_flask as vfz_flask

@app.route('/')
@app.route('/sync')
def sync():
    return render_template('sync.html')


@app.route('/api/<resource>/<verb>')
def action_run(resource, verb):
    run_async = request.args.get('async')
    run_mode = request.args.get('mode')
    run_args = request.args
    result = vfz_flask.run_action(resource, verb, run_mode, run_async, run_args)
    if resource == 'report' and verb == 'run':
        return result
    else:
        return jsonify(result)
